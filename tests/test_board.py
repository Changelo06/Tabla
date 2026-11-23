import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy
import json
import tempfile
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QDate
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit
from PySide6.QtTest import QTest
from unittest.mock import patch
import sqlite3
from tabla.storage import Store
from tabla.board_model import BoardModel
from tabla.task_card import TaskCardDialog
from tabla.pickers import DateField


class BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'tabla.sqlite3')
        self.board = BoardModel(self.store)

    def tearDown(self):
        self.app.processEvents()
        self.store.close()
        self.temp.cleanup()

    def task(self, title, **fields):
        return self.store.save(dict(kind='task', title=title, status='To do', **fields))

    def test_legacy_tasks_map_without_rewriting_or_losing_fields(self):
        for status, expected in [('To do', 'todo'), ('In progress', 'doing'), ('Done', 'done')]:
            task = self.store.save({'kind': 'task', 'title': status, 'status': status, 'body': 'Legacy [[reference]]'})
            self.assertEqual(self.board.column_for(task), expected)
            self.board.cards(expected)
            self.assertEqual(self.store.get(task['id']), task)

    def test_move_reorders_same_list_and_changes_canonical_status(self):
        a, b, c = [self.task(name, board_position=index * 1024) for index, name in enumerate(('Alpha', 'Bravo', 'Charlie'))]
        self.board.move_card(c['id'], 'todo', a['id'])
        self.assertEqual([x['id'] for x in self.board.cards('todo')], [c['id'], a['id'], b['id']])
        self.board.move_card(a['id'], 'doing')
        self.assertEqual(self.store.get(a['id'])['status'], 'In progress')
        self.board.move_card(a['id'], 'done')
        self.assertEqual(self.store.get(a['id'])['status'], 'Done')
        original = self.store.get(a['id'])
        self.board.move_card(a['id'], 'done', a['id'])
        self.assertEqual(self.store.get(a['id']), original)

    def test_custom_list_order_archive_restore_retains_manual_archives(self):
        custom = self.board.add_list('Review')
        self.board.rename(custom, 'Ready for review')
        self.board.move_list(custom, 'doing')
        self.assertEqual([c['id'] for c in self.board.lists()], ['todo', custom, 'doing', 'done'])
        a, b = self.task('A'), self.task('B')
        self.board.move_card(a['id'], custom)
        self.board.move_card(b['id'], custom)
        manual = self.store.get(b['id']); manual['archived'] = True; self.store.save(manual)
        self.board.archive_list(custom)
        self.assertTrue(self.store.get(a['id'])['archived'])
        self.assertNotIn(custom, [c['id'] for c in self.board.lists()])
        self.board.archive_list(custom, False)
        self.assertFalse(self.store.get(a['id'])['archived'])
        self.assertTrue(self.store.get(b['id'])['archived'])

    def test_external_status_change_moves_card_into_matching_standard_list(self):
        custom = self.board.add_list('Review')
        task = self.task('A')
        self.board.move_card(task['id'], custom)
        task = self.store.get(task['id']); task['status'] = 'Done'; self.store.save(task)
        self.assertEqual(self.board.column_for(self.store.get(task['id'])), 'done')

    def test_card_details_and_attachment_roundtrip_in_portable_export(self):
        custom = self.board.add_list('Review')
        source = self.root / 'spec.txt'; source.write_text('Original bytes')
        dialog = TaskCardDialog(self.store, list_id=custom)
        dialog.title.setText('A complete card')
        dialog.body.setPlainText('Description with [[source]]')
        dialog.label_name.setText('Design'); dialog.add_label()
        dialog.add_checklist()
        dialog.checklists[0]['items'].append({'id': 'one', 'text': 'Sketch', 'checked': True})
        dialog.comment.setText('Ready to review'); dialog.add_comment()
        dialog.attachments.add_paths([source])
        dialog.dated.setChecked(True); dialog.day.setDate(QDate(2026, 11, 15))
        dialog.cover = 'rose'
        self.assertTrue(dialog.save())
        saved = dialog.result_record
        dialog.deleteLater(); self.app.processEvents()
        output = self.root / 'workspace.json'; self.store.export_file(output)
        destination = Store(self.root / 'other' / 'tabla.sqlite3')
        try:
            destination.import_file(output)
            restored = destination.get(saved['id'])
            for key in ('body', 'board_list', 'task_labels', 'checklists', 'comments', 'attachments', 'date', 'cover'):
                self.assertEqual(restored[key], saved[key])
            self.assertIn(custom, [c['id'] for c in BoardModel(destination).lists()])
            self.assertEqual(destination.attachments.path_for(restored['attachments'][0]).read_text(), 'Original bytes')
        finally:
            destination.close()

    def test_cancel_does_not_mutate_saved_card(self):
        saved = self.task('Original')
        dialog = TaskCardDialog(self.store, saved)
        dialog.title.setText('Discard this')
        dialog.add_checklist()
        dialog.reject()
        self.assertEqual(self.store.get(saved['id']), saved)
        dialog.deleteLater()

    def test_invalid_card_import_is_rejected_before_writes(self):
        saved = self.task('Original')
        output = self.root / 'workspace.json'; self.store.export_file(output)
        payload = json.loads(output.read_text())
        payload['items'][0]['checklists'] = [{'id': 'x', 'title': 'Broken', 'items': [{'id': '1', 'text': 'A', 'checked': 'yes'}]}]
        output.write_text(json.dumps(payload))
        with self.assertRaises(ValueError):
            self.store.import_file(output)
        self.assertEqual(self.store.get(saved['id']), saved)

    def test_date_picker_today_updates_the_date_field(self):
        field = DateField()
        field.setDate(QDate(2020, 1, 1))
        field.calendarWidget().choose_today()
        self.assertEqual(field.date(), QDate.currentDate())
        field.deleteLater()

    def test_enter_adds_checklist_item_without_removing_or_saving_card(self):
        dialog = TaskCardDialog(self.store)
        dialog.show()
        dialog.title.setText('Still a draft')
        dialog.add_checklist()
        field = next(w for w in dialog.check_host.findChildren(QLineEdit) if w.accessibleName() == 'New checklist item')
        field.setText('First step')
        QTest.keyClick(field, Qt.Key.Key_Return)
        self.assertEqual(len(dialog.checklists), 1)
        self.assertEqual(dialog.checklists[0]['items'][0]['text'], 'First step')
        self.assertIsNone(dialog.result_record)
        dialog.reject(); dialog.deleteLater()

    def test_database_error_keeps_card_draft_and_original_record(self):
        saved = self.task('Original')
        dialog = TaskCardDialog(self.store, saved)
        dialog.title.setText('Keep this draft')
        with patch.object(self.store, 'save', side_effect=sqlite3.OperationalError('Database is locked')):
            self.assertFalse(dialog.save())
        self.assertIn('locked', dialog.error.text())
        self.assertEqual(dialog.title.text(), 'Keep this draft')
        self.assertEqual(self.store.get(saved['id']), saved)
        dialog.reject(); dialog.deleteLater()
