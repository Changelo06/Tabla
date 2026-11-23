import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from datetime import date, timedelta
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QWheelEvent
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.home import HomeLink
from tabla.theme import load_fonts


class HomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        load_fonts()
        cls.app.setFont(QFont("Inter", 10))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'tabla.sqlite3')
        self.window = TablaWindow(self.store)
        self.window.show()

    def tearDown(self):
        self.window.timer.pause()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.store.close()
        self.tmp.cleanup()

    def test_latest_four_active_notes_open_with_note_card_behavior(self):
        for i in range(6):
            self.store.save({'kind': 'note', 'title': 'Note ' + str(i), 'body': 'A preview\n' * 30})
        self.store.save({'kind': 'note', 'title': 'Archived', 'archived': True})
        self.window.navigate('Today')
        QTest.qWait(100)
        home = self.window.home
        self.assertEqual([n['id'] for n in home.notes], [n['id'] for n in self.store.records('note')[:4]])
        self.assertEqual(len(home.note_cards), 4)
        opened = []
        self.window.edit_note = lambda n: opened.append(n['id'])
        home.note_cards[0].clicked.emit()
        self.assertEqual(opened, [home.notes[0]['id']])
        self.assertIsNotNone(self.window._note_origin)

    def test_deadlines_exclude_completed_undated_archived_and_limit_to_four(self):
        today = date.today()
        for i in range(6):
            self.store.save({'kind': 'task', 'title': 'Due ' + str(i), 'date': (today + timedelta(days=i - 1)).isoformat(), 'status': 'To do'})
        for fields in ({'status': 'Done'}, {'archived': True}):
            self.store.save(dict(kind='task', title='Excluded', date=today.isoformat(), **fields))
        self.store.save({'kind': 'task', 'title': 'Undated'})
        self.window.navigate('Today')
        self.assertEqual([r['title'] for r in self.window.home.due_tasks], ['Due 0', 'Due 1', 'Due 2', 'Due 3'])

    def test_calendar_and_compact_board_links_route_to_original_pages(self):
        board = self.window.board_catalog.create('A separate board')
        self.window.navigate('Today')
        QTest.qWait(180)
        link = next(w for w in self.window.home.findChildren(HomeLink) if w.title == board['title'])
        self.assertLessEqual(link.width(), self.window.home.left.width())
        link.click()
        self.assertEqual(self.window.board_id, board['id'])
        self.assertEqual(self.window.page, 'My Tasks')
        self.window.navigate('Today')
        selected = date.today() + timedelta(days=3)
        self.window.home.calendar.open_day(selected)
        self.assertEqual(self.window.page, 'Calendar')
        self.assertEqual(self.window.selected_day, selected)
        self.assertEqual(self.window.calendar_view, 'Day')

    def test_compact_home_reflows_without_horizontal_page_scroll(self):
        for i in range(4):
            self.store.save({'kind': 'note', 'title': 'Note ' + str(i), 'body': 'Text ' * 100})
        self.window.resize(640, 600)
        self.window.navigate('Today')
        QTest.qWait(150)
        self.assertFalse(self.window.home.wide)
        area = self.window.home.parentWidget().parentWidget()
        self.assertEqual(area.horizontalScrollBar().maximum(), 0)
        self.assertGreater(self.window.home.note_cards[-1].y(), self.window.home.note_cards[0].y())

    def test_wide_dashboard_places_sections_in_independent_columns(self):
        self.window.resize(1500, 960)
        self.window.navigate('Today')
        QTest.qWait(120)
        home = self.window.home
        self.assertEqual(home.mode, 3)
        self.assertLess(home.left.x(), home.deadlines.x())
        self.assertLess(home.deadlines.x(), home.notes_section.x())
        self.assertEqual(home.notes_section.y(), home.deadlines.y())

    def test_tasks_remain_useful_when_no_deadlines_exist(self):
        task = self.store.save({'kind': 'task', 'title': 'An undated next step', 'status': 'To do'})
        self.window.navigate('Today')
        self.assertEqual(self.window.home.due_tasks, [])
        self.assertEqual([r['id'] for r in self.window.home.visible_tasks], [task['id']])

    def test_scrolling_notes_keeps_other_home_sections_and_heading_fixed(self):
        for i in range(4):
            self.store.save({'kind': 'note', 'title': 'A long title for note ' + str(i), 'body': 'Long preview text with several wrapped lines. ' * 100,
                             'labels': 'reference, planning, ideas'})
        self.window.resize(1500, 680)
        self.window.navigate('Today')
        QTest.qWait(180)
        home = self.window.home
        self.assertEqual(home.page_area.verticalScrollBar().maximum(), 0)
        self.assertGreater(home.notes_area.verticalScrollBar().maximum(), 0)
        watched = [home.calendar, home.board_section, home.deadlines, home.notes_section.layout().itemAt(0).widget()]
        positions = [w.mapToGlobal(QPoint()) for w in watched]
        viewport = home.notes_area.viewport()
        point = viewport.rect().center()
        event = QWheelEvent(QPointF(point), QPointF(viewport.mapToGlobal(point)), QPoint(), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, False)
        self.app.sendEvent(viewport, event)
        QTest.qWait(50)
        self.assertGreater(home.notes_area.verticalScrollBar().value(), 0)
        self.assertEqual(positions, [w.mapToGlobal(QPoint()) for w in watched])
        self.assertEqual(home.page_area.verticalScrollBar().value(), 0)
