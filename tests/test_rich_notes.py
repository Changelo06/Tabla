import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor, QImage
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.dialogs import NoteDialog
from tabla.rich_document import RichNoteEditor, validate_document
from tabla.note_preview import NotePreview


class RichNoteTests(unittest.TestCase):
    def checklist_editor(self):
        editor = self.dialog.editor
        editor.load_note({'body': 'Introduction\n\n- [ ] **First**\n- [x] Second\n- [ ] Third\n\nClosing paragraph'})
        return editor

    def test_checklist_reorder_preserves_formats_state_and_undo(self):
        editor = self.checklist_editor()
        blocks = []
        block = editor.document().begin()
        while block.isValid():
            if editor._is_check(block):
                blocks.append(block)
            block = block.next()
        before = editor.snapshot()
        editor.move_checklist_item(blocks[0].position(), blocks[2].position())
        checks = [n for n in editor.snapshot()['nodes'] if n.get('check')]
        self.assertEqual([''.join(r.get('text', '') for r in n['runs']) for n in checks], ['Second', 'Third', 'First'])
        self.assertEqual(checks[0]['check'], 2)
        self.assertTrue(checks[2]['runs'][0]['bold'])
        editor.undo()
        self.assertEqual(editor.snapshot(), before)

    def test_checklist_add_toggle_remove_and_reopen(self):
        editor = self.checklist_editor()
        block = editor.document().begin()
        while not editor._is_check(block):
            block = block.next()
        editor._check_action('toggle', block.position())
        editor._check_action('add', block.position())
        editor.insertPlainText('New row')
        self.assertIn('- [ ] New row', editor.plain_body())
        editor._check_action('remove', editor.textCursor().block().position())
        self.assertNotIn('New row', editor.plain_body())
        self.assertIn('Closing paragraph', editor.plain_body())
        self.assertTrue(self.dialog.save())
        reopened = RichNoteEditor(self.store)
        reopened.load_note(self.store.get(self.dialog.record['id']))
        self.assertEqual(reopened.snapshot(), editor.snapshot())

    def test_checklist_enter_continues_unchecked_and_empty_enter_exits(self):
        editor = self.checklist_editor()
        block = editor.document().begin()
        while not editor._is_check(block):
            block = block.next()
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        editor.setTextCursor(cursor)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.assertEqual(editor.textCursor().blockFormat().marker().value, 1)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.assertFalse(editor._is_check(editor.textCursor().block()))

    def test_removing_only_checklist_row_preserves_following_prose(self):
        editor = self.dialog.editor
        editor.load_note({'body': '- [ ] Only row\n\nPlain paragraph'})
        editor._check_action('remove', editor.document().begin().position())
        self.assertEqual(editor.plain_body().strip(), 'Plain paragraph')
        self.assertFalse(any(n.get('check') for n in editor.snapshot()['nodes']))
        editor.load_note({'body': '- [ ] Only row'})
        editor._check_action('remove', editor.document().begin().position())
        self.assertEqual(editor.plain_body(), '')
        self.assertFalse(editor._is_check(editor.document().begin()))
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'tabla.sqlite3')
        self.dialog = NoteDialog(self.store)

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()
        self.app.processEvents()
        self.store.close()
        self.temp.cleanup()

    def test_shortcuts_format_selection_and_survive_reopening(self):
        editor = self.dialog.editor
        editor.setPlainText('Keep this idea')
        editor.selectAll()
        for key in (Qt.Key.Key_B, Qt.Key.Key_I, Qt.Key.Key_U):
            QTest.keyClick(editor, key, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.dialog.save())
        saved = self.store.get(self.dialog.record['id'])
        new = RichNoteEditor(self.store)
        new.load_note(saved)
        new.selectAll()
        fmt = new.currentCharFormat()
        self.assertTrue(fmt.fontItalic())
        self.assertTrue(fmt.fontUnderline())
        self.assertGreaterEqual(fmt.fontWeight(), 700)
        self.assertEqual(new.toPlainText(), 'Keep this idea')
        new.deleteLater()

    def test_ten_column_limit_and_table_text_backup_roundtrip(self):
        editor = self.dialog.editor
        table = editor.insert_table(2, 10)
        table.cellAt(0, 0).firstCursorPosition().insertText('Name')
        table.cellAt(1, 9).firstCursorPosition().insertText('Last cell')
        self.assertFalse(editor.add_column())
        self.dialog.save()
        saved = self.dialog.record
        self.assertIn('Last cell', saved['body'])
        backup = self.root / 'rich-backup.json'
        self.store.export_file(backup)
        restored = Store(self.root / 'restore' / 'tabla.sqlite3')
        try:
            restored.import_file(backup)
            editor2 = RichNoteEditor(restored)
            editor2.load_note(restored.get(saved['id']))
            tables = [n for n in editor2.snapshot()['nodes'] if n['type'] == 'table']
            self.assertEqual(tables[0]['columns'], 10)
            self.assertIn('Last cell', editor2.plain_body())
            editor2.deleteLater()
        finally:
            restored.close()

    def test_invalid_table_import_validation_rejects_without_mutation(self):
        with self.assertRaises(ValueError):
            self.store.save({'kind': 'note', 'title': 'Bad table', 'document': {'version': 1, 'nodes': [
                {'type': 'table', 'columns': 11, 'cells': [[[]] * 11]}]}})
        self.assertEqual(self.store.records(), [])

    def test_backgrounds_and_open_only_do_not_touch_edited_time(self):
        note = self.store.save({'kind': 'note', 'title': 'Existing', 'body': '**Original** [[Other]]'})
        other = NoteDialog(self.store, note)
        other.show()
        QTest.qWait(30)
        other.close()
        self.assertEqual(self.store.get(note['id'])['updated_at'], note['updated_at'])
        self.assertEqual(self.store.get(note['id'])['body'], note['body'])
        other.deleteLater()
        for template in ('lines', 'dots', 'grid', 'paper', 'diamonds'):
            self.dialog.set_background(template)
            self.assertTrue(self.dialog.save())
            self.assertEqual(self.dialog.record['note_template'], template)
            self.assertFalse(self.dialog.editor.grab().isNull())

    def test_three_source_preview_does_not_truncate_saved_sources(self):
        paths = []
        for i in range(5):
            path = self.root / f'Reference {i}.txt'
            path.write_text(str(i))
            paths.append(path)
        self.dialog.attachments.add_paths(paths)
        self.assertEqual(self.dialog.source_rows.count(), 3)
        self.dialog.editor.setPlainText('Five sources')
        self.dialog.save()
        self.assertEqual(len(self.dialog.record['attachments']), 5)
        seen = []
        def inspect():
            panel = self.dialog.all_sources_dialog
            seen.extend(panel.findChildren(QPushButton))
            panel.accept()
        QTimer.singleShot(20, inspect)
        self.dialog.show_all_sources()
        self.assertEqual(len([b for b in seen if (b.accessibleName() or '').startswith('Open attachment')]), 5)

    def test_image_wrap_resize_and_managed_bytes_roundtrip(self):
        path = self.root / 'Image.png'
        image = QImage(200, 100, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.blue)
        image.save(str(path))
        editor = self.dialog.editor
        editor.insert_images([str(path)])
        cursor = QTextCursor(editor.document())
        cursor.setPosition(0)
        editor.setTextCursor(cursor)
        self.assertIsNotNone(editor.image_at_cursor())
        editor.resize_image(120)
        editor.wrap_image('left')
        editor.resize_image(100)
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.insertPlainText('Text alongside image')
        self.assertTrue(self.dialog.save())
        path.unlink()
        saved = self.dialog.record
        self.assertTrue(self.store.attachments.path_for(saved['attachments'][0]).is_file())
        editor2 = RichNoteEditor(self.store)
        editor2.load_note(saved)
        nodes = editor2.snapshot()['nodes']
        images = [r['image'] for n in nodes if n['type'] == 'paragraph' for r in n['runs'] if 'image' in r]
        self.assertEqual(images[0]['wrap'], 'left')
        self.assertIn('Text alongside image', editor2.toPlainText())
        validate_document(editor2.snapshot(), saved['attachments'])
        editor2.deleteLater()

    def test_previews_bound_wrapped_long_words_without_touching_content(self):
        original = 'UnbrokenNote' * 500
        preview = NotePreview(original, 6, 240)
        self.assertLessEqual(len(preview.text), 241)
        preview.resize(100, preview.heightForWidth(100))
        layout, height = preview.layout_text(100)
        self.assertLessEqual(layout.lineCount(), 6)
        self.assertLess(height, 160)
        self.assertEqual(len(original), 6000)
        preview.deleteLater()

    def test_first_legacy_edit_preserves_original_and_takes_recovery_snapshot(self):
        original = '# Original heading\n\n**Keep this text**\n\n[[Linked idea]]'
        note = self.store.save({'kind': 'note', 'title': 'Legacy', 'body': original})
        dialog = NoteDialog(self.store, note)
        dialog.title.setText('Legacy renamed')
        self.assertTrue(dialog.save())
        self.assertEqual(dialog.record['legacy_body'], original)
        self.assertTrue((self.root / 'before-rich-notes.sqlite3').exists())
        self.assertEqual(dialog.record['id'], note['id'])
        self.assertIn('[[Linked idea]]', dialog.record['body'])
        dialog.close()
        dialog.deleteLater()

    def test_plain_text_export_does_not_modify_last_edited_timestamp(self):
        from unittest.mock import patch
        self.dialog.title.setText('Export example')
        self.dialog.editor.setPlainText('All of the text')
        self.dialog.save()
        stamp = self.dialog.record['updated_at']
        output = self.root / 'Example.txt'
        with patch('tabla.note_dialog.QFileDialog.getSaveFileName', return_value=(str(output), 'Text')):
            self.dialog.export_text()
        self.assertIn('All of the text', output.read_text(encoding='utf-8'))
        self.assertEqual(self.store.get(self.dialog.record['id'])['updated_at'], stamp)


if __name__ == '__main__':
    unittest.main()
