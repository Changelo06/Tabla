import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tabla.storage import Store
from tabla.attachments import AttachmentVault, short_name


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'source' / 'tabla.sqlite3')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def source(self, name='A document with a long descriptive name.txt', data=b'Keep this document offline.'):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_copy_survives_original_deletion_and_deduplicates_bytes(self):
        source = self.source()
        first = self.store.attachments.import_files([source])[0]
        second = self.store.attachments.import_files([source])[0]
        source.unlink()
        self.assertEqual(first['key'], second['key'])
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(self.store.attachments.path_for(first).read_bytes(), b'Keep this document offline.')
        self.assertEqual(len(list(self.store.attachments.directory.iterdir())), 1)

    def test_backup_restores_attachment_to_independent_workspace(self):
        item = self.store.attachments.import_files([self.source()])[0]
        note = self.store.save({'kind': 'note', 'title': 'Document note', 'attachments': [item], 'attachment_display': 'compact'})
        self.store.save({'kind': 'task', 'title': 'Related task', 'body': '[[' + note['id'] + ']]'})
        backup = self.root / 'backup.json'
        self.store.export_file(backup)
        other = Store(self.root / 'restored' / 'tabla.sqlite3')
        try:
            other.import_file(backup)
            current = other.get(note['id'])
            self.assertEqual(current['attachment_display'], 'compact')
            self.assertEqual(other.attachments.path_for(current['attachments'][0]).read_bytes(), b'Keep this document offline.')
            self.assertEqual(len(other.backlinks(note['id'])), 1)
        finally:
            other.close()

    def test_tampered_attachment_backup_is_rejected_before_database_changes(self):
        item = self.store.attachments.import_files([self.source()])[0]
        self.store.save({'kind': 'note', 'title': 'Document note', 'attachments': [item]})
        backup = self.root / 'backup.json'
        self.store.export_file(backup)
        data = json.loads(backup.read_text(encoding='utf-8'))
        data['attachment_files'][0]['data'] = base64.b64encode(b'tampered').decode()
        backup.write_text(json.dumps(data), encoding='utf-8')
        other = Store(self.root / 'invalid' / 'tabla.sqlite3')
        try:
            with self.assertRaises(ValueError):
                other.import_file(backup)
            self.assertEqual(other.records(), [])
            self.assertFalse(other.attachments.directory.exists())
        finally:
            other.close()

    def test_unsupported_batch_and_path_traversal_are_rejected(self):
        valid = self.source('safe.txt')
        invalid = self.source('not-a-document.exe')
        with self.assertRaises(ValueError):
            self.store.attachments.import_files([valid, invalid])
        self.assertFalse(self.store.attachments.directory.exists())
        with self.assertRaises(ValueError):
            self.store.save({'kind': 'note', 'title': 'Bad path', 'attachments': [{'key': '../outside.pdf', 'name': 'outside.pdf', 'size': 4}]})
        self.assertEqual(self.store.records(), [])

    def test_filename_shortening_preserves_extension_and_size_limit(self):
        name = 'A very long project document name that needs shortening.pdf'
        short = short_name(name, 28)
        self.assertLessEqual(len(short), 28)
        self.assertTrue(short.endswith('.pdf'))
        with patch('tabla.attachments.FILE_LIMIT', 8):
            with self.assertRaises(ValueError):
                self.store.attachments.import_files([self.source('large.txt', b'123456789')])


if __name__ == '__main__':
    unittest.main()
