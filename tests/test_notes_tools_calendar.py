import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QTextCursor, QTextListFormat, QImage
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.dialogs import NoteDialog
from tabla.rich_document import RichNoteEditor


class NotesToolsCalendarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'tabla.sqlite3')
        self.window = TablaWindow(self.store)
        self.window.show()
        QTest.qWait(100)

    def tearDown(self):
        self.window.timer.pause()
        self.window.close()
        QTest.qWait(100)
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.store.close()
        self.tmp.cleanup()

    def test_toolbar_cycles_lists_and_preserves_rich_lists_on_reopen(self):
        dialog = NoteDialog(self.store, {'title': 'List test', 'body': 'First\nSecond'}, parent=self.window)
        editor = dialog.editor
        editor.setPlainText('First\nSecond')
        editor.selectAll()
        control = next(b for b in dialog.findChildren(QPushButton) if b.accessibleName() == 'Cycle list style')
        for style, prefix in ((QTextListFormat.Style.ListDisc, '• First'), (QTextListFormat.Style.ListDecimal, '1. First'), (QTextListFormat.Style.ListUpperAlpha, 'A. First')):
            control.click()
            self.assertEqual(editor.textCursor().currentList().format().style(), style)
            self.assertIn(prefix, editor.plain_body())
        editor.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        editor.insertPlainText('Third')
        self.assertIn('C. Third', editor.plain_body())
        self.assertTrue(dialog.save())
        saved = self.store.get(dialog.record['id'])
        restored = RichNoteEditor(self.store)
        restored.load_note(saved)
        self.assertEqual(restored.snapshot(), editor.snapshot())
        self.assertIn('C. Third', restored.plain_body())
        restored.deleteLater()
        dialog.deleteLater()

    def test_direct_image_buttons_insert_managed_images_in_capture_and_note(self):
        path = Path(self.tmp.name) / 'Example.png'
        image = QImage(80, 50, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.blue)
        image.save(str(path))
        self.window.navigate('Notes')
        capture = self.window.capture
        capture.expand()
        dialog = NoteDialog(self.store, {'title': 'Image test'}, parent=self.window)
        for host, editor, attachments in ((capture, capture.body, capture.attachments), (dialog, dialog.editor, dialog.attachments)):
            control = next(b for b in host.findChildren(QPushButton) if b.accessibleName() == 'Insert image')
            with patch('tabla.note_dialog.QFileDialog.getOpenFileNames', return_value=([str(path)], 'Images')):
                control.click()
            nodes = editor.snapshot()['nodes']
            inserted = [run['image'] for n in nodes if n['type'] == 'paragraph' for run in n['runs'] if 'image' in run]
            self.assertEqual(len(inserted), 1)
            self.assertTrue(any(a['key'] == inserted[0]['key'] for a in attachments.items))
            self.assertTrue(self.store.attachments.path_for(attachments.items[0]).exists())
        self.assertTrue(dialog.save())
        saved = self.store.get(dialog.record['id'])
        restored = RichNoteEditor(self.store)
        restored.load_note(saved)
        self.assertEqual(restored.snapshot(), dialog.editor.snapshot())
        restored.deleteLater()
        dialog.deleteLater()

    def test_home_calendar_keeps_day_highlights_and_event_colors(self):
        day = date.today().replace(day=15)
        key = day.isoformat()
        self.store.save({'kind': 'event', 'title': 'Blue event', 'date': key, 'color': 'blue'})
        self.store.save({'kind': 'block', 'title': 'Green work', 'date': key, 'color': 'green'})
        self.store.save({'kind': 'note', 'title': 'Day highlight', 'date': key, 'day_annotation': True, 'day_color': 'rose'})
        self.store.save({'kind': 'event', 'title': 'Archived', 'date': key, 'color': 'yellow', 'archived': True})
        project = self.store.save({'kind': 'project', 'title': 'Green project', 'color': 'green'})
        next_key = (day + timedelta(days=1)).isoformat()
        self.store.save({'kind': 'task', 'title': 'Default Calendar blue', 'date': next_key, 'project': project['id']})
        self.window.navigate('Today')
        QTest.qWait(120)
        mini = self.window.home.calendar
        self.assertEqual(mini.day_colors[key], ['rose', 'blue', 'green'])
        self.assertEqual(mini.day_buttons[key].colors, mini.day_colors[key])
        self.assertEqual(mini.day_colors[next_key], ['blue'])
        mini.day_buttons[key].click()
        self.assertEqual(self.window.selected_day, day)

    def test_window_controls_use_minimize_maximize_close_order(self):
        chrome = self.window.chrome
        self.assertLess(chrome.minimize.x(), chrome.maximize.x())
        self.assertLess(chrome.maximize.x(), chrome.close_button.x())
        self.assertEqual(chrome.minimize.color, '#febc2e')
        self.assertEqual(chrome.maximize.color, '#28c840')
