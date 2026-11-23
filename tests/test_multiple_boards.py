import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import QCoreApplication, QEvent
from tabla.storage import Store
from tabla.boards import BoardCatalog
from tabla.board_model import BoardModel
from tabla.task_card import TaskCardDialog
from tabla.workspace import TablaWindow
from tabla.task_board import ListPanel


class MultipleBoardsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'workspace.sqlite3')
        self.catalog = BoardCatalog(self.store)

    def tearDown(self):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.store.close()
        self.tmp.cleanup()

    def test_migration_preserves_ids_metadata_archives_and_trash(self):
        project = self.store.save({'kind': 'project', 'title': 'Work'})
        old = BoardModel(self.store)
        custom = old.add_list('Review')
        first = self.store.save({'kind': 'task', 'title': 'First', 'project': project['id'], 'board_list': custom, 'status': 'To do', 'board_position': 123})
        deleted = self.store.save({'kind': 'task', 'title': 'Recover me', 'deleted': True, 'status': 'Done', 'body': 'Keep this'})
        self.catalog.migrate()
        self.assertTrue(self.store.path.with_name('before-multiple-boards.sqlite3').exists())
        for original in (first, deleted):
            migrated = self.store.get(original['id'])
            self.assertEqual({k: migrated[k] for k in original}, original)
            self.assertTrue(migrated['board'])
        self.assertEqual(self.store.get(first['id'])['board_list'], custom)
        before = self.store.records('board')
        self.catalog.migrate()
        self.assertEqual(self.store.records('board'), before)

    def test_migration_failure_is_atomic(self):
        original = self.store.save({'kind': 'task', 'title': 'Original'})
        write = self.store._write
        def fail(record):
            if record['kind'] == 'task' and record.get('board'):
                raise RuntimeError('Interrupted migration')
            write(record)
        with patch.object(self.store, '_write', side_effect=fail):
            with self.assertRaises(RuntimeError):
                self.catalog.migrate()
        self.assertEqual(self.store.get(original['id']), original)
        self.assertEqual(self.store.records('board'), [])
        self.assertIsNone(self.store.setting('multi_board_schema'))

    def test_two_boards_under_one_project_are_independent(self):
        self.catalog.migrate()
        project = self.store.save({'kind': 'project', 'title': 'Website'})
        design = self.catalog.create('Design', project['id'])
        launch = self.catalog.create('Launch', project['id'])
        left, right = BoardModel(self.store, design['id']), BoardModel(self.store, launch['id'])
        left.rename('todo', 'Ideas')
        review = left.add_list('Review')
        card = self.store.save({'kind': 'task', 'title': 'Sketch', 'board': design['id'], 'board_list': review, 'status': 'To do'})
        self.assertEqual(right.lists()[0]['title'], 'To do')
        self.assertEqual(right.cards('todo'), [])
        self.assertEqual(left.cards(review)[0]['id'], card['id'])
        left.archive_list('todo')
        self.assertEqual(len(right.lists()), 3)

    def test_complete_and_uncomplete_keeps_custom_list_and_rank(self):
        self.catalog.migrate()
        board = self.catalog.boards()[0]
        model = BoardModel(self.store, board['id'])
        custom = model.add_list('Review')
        card = self.store.save({'kind': 'task', 'title': 'Review this', 'board': board['id'], 'board_list': custom, 'board_position': 400, 'status': 'To do'})
        for checked in (True, False):
            dialog = TaskCardDialog(self.store, card)
            dialog.completed.setChecked(checked)
            self.assertTrue(dialog.save())
            card = self.store.get(card['id'])
            self.assertEqual((card['board_list'], card['board_position']), (custom, 400))
            dialog.deleteLater()

    def test_completion_rule_moves_once_and_keeps_completion(self):
        self.catalog.migrate()
        board = self.catalog.boards()[0]
        model = BoardModel(self.store, board['id'])
        target = model.add_list('Finished work')
        model.set_completion_target('todo', target)
        model.set_completion_target(target, 'doing')  # No chained automation.
        existing = self.store.save({'kind': 'task', 'title': 'Already here', 'board': board['id'], 'board_list': target, 'board_position': 2048})
        card = self.store.save({'kind': 'task', 'title': 'Complete this', 'board': board['id'], 'board_list': 'todo', 'status': 'To do'})
        dialog = TaskCardDialog(self.store, card)
        dialog.completed.setChecked(True)
        self.assertTrue(dialog.save())
        card = self.store.get(card['id'])
        self.assertEqual((card['board_list'], card['status']), (target, 'Done'))
        self.assertGreater(card['board_position'], existing['board_position'])
        card['title'] = 'Edited after completion'
        self.assertEqual(self.store.save(card)['board_list'], target)
        card['status'] = 'To do'
        self.assertEqual(self.store.save(card)['board_list'], target)
        dialog.deleteLater()

    def test_completion_rule_validation_archiving_and_board_isolation(self):
        self.catalog.migrate()
        board = self.catalog.boards()[0]
        model = BoardModel(self.store, board['id'])
        target = model.add_list('Review')
        for invalid in ('todo', 'missing', 12):
            with self.assertRaises(ValueError):
                model.set_completion_target('todo', invalid)
        model.set_completion_target('todo', target)
        other = self.catalog.create('Other board')
        card = self.store.save({'kind': 'task', 'title': 'Other card', 'board': other['id'], 'board_list': 'todo', 'status': 'To do'})
        card['status'] = 'Done'
        self.assertEqual(self.store.save(card)['board_list'], 'todo')
        model.archive_list(target)
        self.assertIsNone(model.lists()[0].get('completion_target'))
        with self.assertRaises(ValueError):
            model.set_completion_target('todo', target)

    def test_explicit_list_move_does_not_trigger_completion_rule(self):
        self.catalog.migrate()
        board = self.catalog.boards()[0]
        model = BoardModel(self.store, board['id'])
        model.set_completion_target('done', 'doing')
        card = self.store.save({'kind': 'task', 'title': 'Move me', 'board': board['id'], 'board_list': 'todo', 'status': 'To do'})
        self.assertEqual(model.move_card(card['id'], 'done')['board_list'], 'done')

    def test_board_backup_conflicts_remap_tasks_and_projects_together(self):
        self.catalog.migrate()
        project = self.store.save({'kind': 'project', 'title': 'Project'})
        board = self.catalog.create('Research', project['id'])
        card = self.store.save({'kind': 'task', 'title': 'Read', 'board': board['id'], 'status': 'To do'})
        backup = Path(self.tmp.name) / 'backup.json'
        self.store.export_file(backup)
        other = Store(Path(self.tmp.name) / 'other' / 'workspace.sqlite3')
        try:
            other.save(dict(board, title='Different board'))
            other.import_file(backup)
            BoardCatalog(other).migrate()
            imported = other.get(card['id'])
            self.assertNotEqual(imported['board'], board['id'])
            self.assertEqual(other.get(imported['board'])['title'], 'Research (imported copy)')
            self.assertEqual(imported['project'], other.get(imported['board'])['project'])
        finally:
            other.close()

    def test_switching_retains_drafts_and_canvas_updates_keep_sidebar(self):
        self.catalog.migrate()
        a, b = self.catalog.boards()[0], self.catalog.create('Second board')
        window = TablaWindow(self.store)
        window.show()
        window.select_board(a['id'])
        QTest.qWait(500)
        panel = window.board.findChildren(ListPanel)[0]
        panel.open_composer()
        panel.input.setText('An unfinished card')
        window.select_board(b['id'])
        window.select_board(a['id'])
        QTest.qWait(500)
        panel = window.board.findChildren(ListPanel)[0]
        self.assertEqual(panel.input.text(), 'An unfinished card')
        canvas, sidebar = window.board, window.boards_sidebar
        panel.input.setText('Saved card')
        panel.add_card()
        card_id = panel.cards.item(0).data(__import__('PySide6.QtCore', fromlist=['Qt']).Qt.ItemDataRole.UserRole)['id']
        window.board.move_card(card_id, 'doing')
        self.assertIs(window.board, canvas)
        self.assertIs(window.boards_sidebar, sidebar)
        self.assertEqual(self.store.get(card_id)['board'], a['id'])
        window.timer.pause()
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_collapsed_sidebar_can_be_reopened_without_replacing_canvas(self):
        self.store.set_setting('boards_sidebar_hidden', True)
        window = TablaWindow(self.store)
        window.resize(1500, 900)
        window.show()
        window.navigate('Board')
        QTest.qWait(500)
        self.assertFalse(window.boards_sidebar.isVisible())
        self.assertEqual(window.boards_toggle.accessibleName(), 'Show boards sidebar')
        canvas = window.board
        window.boards_toggle.click()
        QTest.qWait(500)
        self.assertTrue(window.boards_sidebar.isVisible())
        self.assertFalse(self.store.setting('boards_sidebar_hidden'))
        self.assertIs(canvas, window.board)
        window.resize(640, 480)
        QTest.qWait(500)
        self.assertFalse(window.boards_sidebar.isVisible())
        self.assertEqual(window.boards_toggle.accessibleName(), 'Choose a board')
        window.resize(1500, 900)
        QTest.qWait(500)
        self.assertTrue(window.boards_sidebar.isVisible())
        window.timer.pause()
        window.close()
        window.deleteLater()
        self.app.processEvents()
        reopened = TablaWindow(self.store)
        reopened.show()
        reopened.navigate('Board')
        QTest.qWait(500)
        self.assertTrue(reopened.boards_sidebar.isVisible())
        reopened.timer.pause()
        reopened.close()
        reopened.deleteLater()
        self.app.processEvents()

    def test_short_list_fits_cards_and_long_list_still_scrolls(self):
        self.catalog.migrate()
        board = self.catalog.boards()[0]
        self.store.save({'kind': 'task', 'title': 'One card with details', 'body': 'Description',
                         'cover': 'green', 'board': board['id'], 'status': 'To do'})
        window = TablaWindow(self.store)
        window.resize(1500, 900)
        window.show()
        window.select_board(board['id'])
        QTest.qWait(500)
        panel = window.board.findChildren(ListPanel)[0]
        self.assertEqual(panel.cards.verticalScrollBar().maximum(), 0)
        panel.open_composer()
        QTest.qWait(500)
        self.assertEqual(panel.cards.verticalScrollBar().maximum(), 0)
        panel.close_composer()
        for i in range(30):
            self.store.save({'kind': 'task', 'title': 'Card ' + str(i), 'board': board['id'], 'status': 'To do'})
        window.board.reconcile()
        QTest.qWait(500)
        self.assertGreater(panel.cards.verticalScrollBar().maximum(), 0)
        window.timer.pause()
        window.close()
        window.deleteLater()
        self.app.processEvents()
