import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.surfaces import QuickCapture
from tabla.note_dialog import NoteDialog


class NotesQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'notes.sqlite3')
        self.window = TablaWindow(self.store)
        self.window.show()
        self.window.navigate('Notes')
        QTest.qWait(150)

    def tearDown(self):
        self.window.timer.pause()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.store.close()
        self.tmp.cleanup()

    def test_capture_coalesces_writes_and_recovers_rich_draft(self):
        capture = self.window.capture
        writes = []
        original = self.store.set_setting
        def traced(key, value):
            if key == capture.draft_key:
                writes.append(value)
            return original(key, value)
        self.store.set_setting = traced
        capture.body.setPlainText('A formatted thought')
        cursor = capture.body.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        capture.body.setTextCursor(cursor)
        capture.body.toggle_mark('bold')
        capture.title.setText('Draft')
        self.assertEqual(writes, [])
        QTest.qWait(440)
        self.assertEqual(len(writes), 1)
        restored = QuickCapture(self.store)
        self.assertTrue(restored.body.snapshot()['nodes'][0]['runs'][0]['bold'])
        record = capture.flush()
        self.assertEqual(record['body'], 'A formatted thought')
        self.assertEqual(record['document'], restored.body.snapshot())
        QTest.qWait(440)
        self.assertEqual(self.store.setting(capture.draft_key), {})
        restored.deleteLater()

    def test_gallery_sync_preserves_capture_scroll_and_unchanged_cards(self):
        note = self.store.save({'kind': 'note', 'title': 'First', 'body': 'Short'})
        other = self.store.save({'kind': 'note', 'title': 'Second', 'body': 'Keep this card'})
        self.window.render(preserve_capture=True)
        capture, scroll = self.window.capture, self.window.notes_scroll
        first, second = self.window._gallery_cards[note['id']], self.window._gallery_cards[other['id']]
        self.window.sync_note_gallery()
        self.assertIs(self.window._gallery_cards[note['id']], first)
        note['body'] = 'Changed content'
        self.store.save(note)
        self.window.sync_note_gallery()
        self.assertIs(self.window.capture, capture)
        self.assertIs(self.window.notes_scroll, scroll)
        self.assertIs(self.window._gallery_cards[other['id']], second)
        self.assertIsNot(self.window._gallery_cards[note['id']], first)

    def test_clearing_a_persisted_capture_does_not_restore_old_text(self):
        capture = self.window.capture
        capture.body.setPlainText('Discard this draft by clearing it')
        QTest.qWait(440)
        capture.body.clear()
        capture.commit()
        restored = QuickCapture(self.store)
        self.assertEqual(restored.body.toPlainText(), '')
        self.assertEqual(self.store.records('note'), [])
        restored.deleteLater()

    def test_rich_checklist_preview_changes_survive_opening(self):
        capture = self.window.capture
        capture.checklist()
        capture.body.insertPlainText('A checklist item')
        note = capture.flush()
        self.window.toggle_note_line(note['id'], 0, True)
        dialog = NoteDialog(self.store, self.store.get(note['id']), parent=self.window)
        self.assertIn('- [x] A checklist item', dialog.editor.plain_body())
        dialog.deleteLater()

    def test_note_toolbar_stays_outside_long_document_and_close_saves(self):
        dialog = NoteDialog(self.store, parent=self.window)
        dialog.show()
        dialog.editor.setPlainText('Long note\n' * 200)
        QTest.qWait(80)
        self.assertEqual(dialog.edited.text(), 'Saving…')
        self.assertGreater(dialog.editor.verticalScrollBar().maximum(), 0)
        dialog.accept()
        self.assertTrue(self.store.get(dialog.record['id'])['body'].startswith('Long note'))
        dialog.deleteLater()

    def test_focus_reveals_card_actions_without_changing_card_size(self):
        note = self.store.save({'kind': 'note', 'title': 'Keyboard access', 'body': 'Content'})
        self.window.render(preserve_capture=True)
        card = self.window._gallery_cards[note['id']]
        QTest.qWait(80)
        before = card.size()
        card.setFocus(Qt.FocusReason.TabFocusReason)
        self.app.processEvents()
        card.update_controls()
        self.assertFalse(card._quiet_actions.isHidden())
        self.assertEqual(card.size(), before)
        self.assertEqual(card._quiet_pin.toolTip(), 'Pin')


if __name__ == '__main__':
    unittest.main()
