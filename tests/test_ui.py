import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QDate
from tabla.storage import Store
from tabla.theme import STYLE, load_fonts
from tabla.workspace import TablaWindow as MainWindow
from tabla.dialogs import ItemDialog, NoteDialog


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        load_fonts()
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "ui.sqlite3")
        self.store.seed_demo()
        self.window = MainWindow(self.store)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.timer.pause()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.store.close()
        self.tmp.cleanup()

    def test_all_pages_and_calendar_views_render_at_laptop_size(self):
        self.window.resize(1100, 760)
        for page in ("Today", "Calendar", "My Tasks", "Notes", "Focus", "Settings"):
            self.window.navigate(page)
            self.app.processEvents()
            self.assertFalse(self.window.grab().isNull())
        for mode in ("Month", "Week", "Day"):
            self.window.navigate("Calendar")
            self.window.calendar_mode(mode)
            self.app.processEvents()
            self.assertGreater(self.window.content.count(), 3)
        self.window.navigate("My Tasks")
        self.window.set_task_layout("Board")
        self.app.processEvents()
        self.assertFalse(self.window.grab().isNull())

    def test_note_autosave_checklist_and_preview(self):
        dialog = NoteDialog(self.store, parent=self.window)
        dialog.show()
        dialog.title.setText("UI saved note")
        dialog.editor.setPlainText("- [ ] A small task\n\nRelated: [[Personal website]]")
        QTest.qWait(600)
        self.assertTrue(dialog.record.get("id"))
        saved = self.store.get(dialog.record["id"])
        self.assertIn("A small task", saved["body"])
        self.assertEqual(len(self.store.backlinks(self.store.resolve("Personal website")["id"])), 2)
        self.assertFalse(hasattr(dialog, 'tabs'))
        from PySide6.QtGui import QTextCursor, QTextBlockFormat
        dialog.editor.moveCursor(QTextCursor.MoveOperation.End)
        dialog.editor.add_checklist()
        dialog.editor.insertPlainText('Inline task')
        cursor = dialog.editor.textCursor()
        fmt = cursor.blockFormat()
        fmt.setMarker(QTextBlockFormat.MarkerType.Checked)
        cursor.setBlockFormat(fmt)
        dialog.save()
        self.assertIn('- [x] Inline task', self.store.get(dialog.record['id'])['body'])
        self.assertIn('[[Personal website]]', dialog.editor.toPlainText())
        dialog.accept()
        dialog.deleteLater()

    def test_task_and_event_editors_validate_and_save(self):
        task = ItemDialog(self.store, "task", parent=self.window)
        task.title.setText("An offline task")
        task.dated.setChecked(True)
        task.day.setDate(QDate(2026, 10, 21))
        task.save()
        self.assertEqual(task.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(task.result_record["date"], "2026-10-21")
        event = ItemDialog(self.store, "event", parent=self.window)
        event.title.setText("Appointment")
        event.end.setTime(event.time.time())
        event.save()
        self.assertIsNone(event.result_record)
        self.assertIn("end time", event.error.text())
        task.deleteLater()
        event.deleteLater()

    def test_target_picker_disambiguates_duplicate_titles(self):
        first = self.store.save({"kind": "note", "title": "Same title"})
        second = self.store.save({"kind": "task", "title": "Same title"})
        dialog = NoteDialog(self.store, parent=self.window)
        dialog.title.setText("Precise link")
        editor = dialog.editor
        editor.setPlainText("[[")
        editor.moveCursor(editor.textCursor().MoveOperation.End)
        editor._start = 2
        editor.candidates = {"Second target": second}
        editor.insert_link("Second target")
        dialog.save()
        self.assertEqual(self.store.resolve("Same title", dialog.record["id"])["id"], second["id"])
        dialog.accept()
        dialog.deleteLater()

    def test_task_checkbox_changes_database_and_focus_does_not_start_implicitly(self):
        task = self.store.records("task")[0]
        self.window.task_changed(task["id"], True)
        self.assertEqual(self.store.get(task["id"])["status"], "Done")
        self.window.focus_task(task["id"])
        self.assertEqual(self.window.timer.data["task"], task["id"])
        self.assertFalse(self.window.timer.data["running"])

    def test_closing_note_flushes_pending_autosave(self):
        dialog = NoteDialog(self.store, parent=self.window)
        dialog.show()
        dialog.title.setText("Saved before closing")
        dialog.editor.setPlainText("Do not lose these last keystrokes.")
        dialog.close()
        self.assertIsNotNone(dialog.record.get("id"))
        self.assertEqual(self.store.get(dialog.record["id"])["body"], "Do not lose these last keystrokes.")
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
