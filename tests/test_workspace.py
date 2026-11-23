import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date, timedelta
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton
from PySide6.QtCore import Qt, QPoint, QPointF, QMimeData
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.theme import load_fonts
from tabla.workspace import TablaWindow
from tabla.surfaces import QuickCapture, overlapping_columns, Timeline, CalendarCell, BoardColumn, RecordButton


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        load_fonts()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'test.sqlite3')
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append(str(value))
        self.window = TablaWindow(self.store)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.timer.pause()
        self.window.close()
        QTest.qWait(100)
        self.window.deleteLater()
        self.app.processEvents()
        self.store.close()
        self.tmp.cleanup()
        sys.excepthook = self.old_hook
        self.assertEqual(self.errors, [], 'Unhandled Qt callbacks: ' + str(self.errors))

    def test_quick_capture_saves_once_when_navigating_and_survives_reopen(self):
        self.window.navigate('Notes')
        capture = self.window.capture
        capture.title.setText('Meeting ideas')
        capture.body.setPlainText('Discuss roadmap\n- [ ] Bring sketches')
        capture.pin.setChecked(True)
        self.window.navigate('My Tasks')
        records = self.store.records('note')
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]['pinned'])
        self.assertIn('Bring sketches', records[0]['body'])
        self.window.navigate('Notes')
        self.window.navigate('Today')
        self.assertEqual(len(self.store.records('note')), 1)
        other = Store(self.store.path)
        self.assertEqual(other.get(records[0]['id'])['body'], records[0]['body'])
        other.close()

    def test_inline_checklist_is_current_when_note_opens(self):
        note = self.store.save({'kind': 'note', 'title': 'Shopping', 'body': '- [ ] Coffee\n- [ ] Bread'})
        card = self.window.note_card(note)
        check = card.findChildren(QCheckBox)[0]
        check.setChecked(True)
        self.assertIn('- [x] Coffee', self.store.get(note['id'])['body'])
        opened = []
        self.window.edit_note = lambda current: opened.append(current)
        self.window.open_note_card(note)
        self.assertIn('- [x] Coffee', opened[0]['body'])
        card.deleteLater()

    def test_inline_task_edit_keeps_identity_and_links(self):
        task = self.store.save({'kind': 'task', 'title': 'Draft', 'status': 'To do'})
        note = self.store.save({'kind': 'note', 'title': 'Context', 'body': '[[Draft]]'})
        self.window.update_task(task['id'], 'title', 'Final draft')
        self.window.update_task(task['id'], 'status', 'Done')
        self.app.processEvents()
        self.assertEqual(self.store.resolve('Draft', note['id'])['title'], 'Final draft')
        self.assertEqual(self.store.get(task['id'])['status'], 'Done')

    def test_day_highlight_and_day_note_are_portable_records(self):
        day = date.today()
        self.window.mark_day(day, 'yellow')
        record = self.window.day_annotation(day)
        record['body'] = 'A day worth remembering'
        self.store.save(record)
        self.window.mark_day(day, 'blue')
        self.assertEqual(self.window.day_annotation(day)['body'], record['body'])
        output = Path(self.tmp.name) / 'backup.json'
        self.store.export_file(output)
        exported = json.loads(output.read_text(encoding='utf-8'))
        matching = [r for r in exported['items'] if r.get('day_annotation')]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]['day_color'], 'blue')

    def test_calendar_moves_and_timeline_resize_preserve_meeting_notes(self):
        event = self.store.save({'kind': 'event', 'title': 'Design meeting', 'body': 'Agenda\n- [ ] Review',
            'date': date.today().isoformat(), 'time': '09:00', 'end_time': '10:00'})
        note = self.store.save({'kind': 'note', 'title': 'Meeting context', 'body': '[[Design meeting]]'})
        self.assertEqual(self.store.resolve('Design meeting', note['id'])['id'], event['id'])
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.window.move_record_date(event['id'], tomorrow)
        self.window.reschedule(event['id'], tomorrow, 630, 90)
        current = self.store.get(event['id'])
        self.assertEqual((current['date'], current['time'], current['end_time']), (tomorrow, '10:30', '12:00'))
        self.assertEqual(current['body'], event['body'])
        self.assertEqual(self.store.backlinks(event['id'])[0]['id'], note['id'])

    def test_timeline_overlap_lanes_are_separate_and_reset_after_cluster(self):
        events = [{'id': str(i), 'time': start, 'end_time': end} for i, (start, end) in enumerate(
            [('09:00', '10:00'), ('09:30', '10:30'), ('11:00', '12:00')])]
        layouts = overlapping_columns(events)
        self.assertEqual([item[4] for item in layouts], [2, 2, 1])
        self.assertNotEqual(layouts[0][3], layouts[1][3])

    def test_dark_mode_and_sidebar_preference_preserve_content(self):
        note = self.store.save({'kind': 'note', 'title': 'Keep me', 'body': '# Heading\n[[Task]]'})
        self.window.set_appearance('Dark')
        self.assertTrue(self.app.property('tablaDark'))
        for page in ('Notes', 'Calendar', 'My Tasks', 'Focus'):
            self.window.navigate(page)
            self.app.processEvents()
            self.assertFalse(self.window.grab().isNull())
        self.window.toggle_sidebar()
        self.assertEqual(self.window.sidebar.width(), 64)
        self.assertTrue(self.store.setting('sidebar_hidden'))
        self.assertTrue(self.window.sidebar.isHidden())
        self.assertEqual(self.store.get(note['id'])['body'], note['body'])
        self.window.set_appearance('Light')

    def test_closing_saves_capture_and_cancels_pending_render(self):
        self.window.navigate('Notes')
        self.window.capture.body.setPlainText('Capture before close')
        self.window.resize_debounce.start()
        self.window.close()
        QTest.qWait(100)
        self.assertEqual(self.store.records('note')[0]['body'], 'Capture before close')
        self.assertFalse(self.window.resize_debounce.isActive())

    def test_calendar_and_board_drop_payloads_update_the_same_task(self):
        task = self.store.save({'kind': 'task', 'title': 'Move me', 'status': 'To do'})
        day = date.today() + timedelta(days=2)
        cell = CalendarCell(day)
        cell.moved.connect(self.window.move_record_date)
        mime = QMimeData()
        mime.setData('application/x-tabla-record', task['id'].encode())
        event = QDropEvent(QPointF(20, 20), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        cell.dropEvent(event)
        self.assertEqual(self.store.get(task['id'])['date'], day.isoformat())
        column = BoardColumn('In progress')
        column.moved.connect(lambda rid, status: self.window.update_task(rid, 'status', status))
        column.dropEvent(QDropEvent(QPointF(20, 20), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.app.processEvents()
        self.assertEqual(self.store.get(task['id'])['status'], 'In progress')
        cell.deleteLater()
        column.deleteLater()

    def test_timeline_pointer_drag_reschedules_event(self):
        day = date.today()
        record = self.store.save({'kind': 'event', 'title': 'Drag meeting', 'date': day.isoformat(), 'time': '09:00', 'end_time': '10:00'})
        timeline = Timeline([day], [record])
        timeline.resize(700, timeline.minimumHeight())
        timeline.rescheduled.connect(self.window.reschedule)
        timeline.show()
        self.app.processEvents()
        rect = timeline.rects[0][0]
        point = rect.center().toPoint()
        QTest.mousePress(timeline, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(timeline, point + QPoint(0, Timeline.hour_height))
        QTest.mouseRelease(timeline, Qt.MouseButton.LeftButton, pos=point + QPoint(0, Timeline.hour_height))
        self.assertEqual(self.store.get(record['id'])['time'], '10:00')
        self.assertEqual(self.store.get(record['id'])['end_time'], '11:00')
        timeline.close()
        timeline.deleteLater()

    def test_entry_click_opens_its_record_id(self):
        record = self.store.save({'kind': 'event', 'title': 'Open this meeting'})
        opened = []
        entry = RecordButton(record, lambda rid=record['id']: opened.append(rid))
        entry.resize(220, 30)
        entry.show()
        QTest.mouseClick(entry, Qt.MouseButton.LeftButton)
        self.assertEqual(opened, [record['id']])
        entry.close()
        entry.deleteLater()

    def test_sidebar_trash_restores_archived_note_with_links_intact(self):
        note = self.store.save({'kind': 'note', 'title': 'Accidentally deleted', 'body': 'Keep this text', 'archived': True, 'deleted': True})
        source = self.store.save({'kind': 'task', 'title': 'Related work', 'body': '[[' + note['id'] + ']]'})
        self.window.navigate('Notes')
        QTest.mouseClick(self.window.nav_buttons['Trash'], Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.page, 'Trash')
        self.app.processEvents()
        restore = next(btn for btn in self.window.workspace.findChildren(QPushButton)
                       if btn.property('trashRecordId') == note['id'])
        QTest.mouseClick(restore, Qt.MouseButton.LeftButton)
        current = self.store.get(note['id'])
        self.assertFalse(current['deleted'])
        self.assertFalse(current['archived'])
        self.assertEqual(current['body'], 'Keep this text')
        self.assertEqual(self.store.resolve(note['id'], source['id'])['id'], note['id'])
        self.assertEqual(self.store.records(state='trash'), [])
        self.window.toggle_sidebar()
        self.app.processEvents()
        self.assertTrue(self.window.sidebar.isHidden())
        self.window.toggle_sidebar()
        self.app.processEvents()
        self.assertTrue(self.window.nav_buttons['Trash'].isVisible())
        self.assertEqual(self.window.nav_buttons['Trash'].accessibleName(), 'Trash')

    def test_trash_lists_tasks_and_searches_deleted_content(self):
        task = self.store.save({'kind': 'task', 'title': 'Recover task', 'body': 'Meeting action', 'deleted': True})
        self.store.save({'kind': 'note', 'title': 'Another note', 'body': 'Other text', 'deleted': True})
        self.window.recovery_dialog('trash')
        self.assertEqual(self.window.page, 'Trash')
        self.window.search_trash('Meeting')
        QTest.qWait(100)
        self.app.processEvents()
        buttons = [btn for btn in self.window.workspace.findChildren(QPushButton)
                   if btn.property('trashRecordId') and btn.isVisible()]
        self.assertEqual([btn.property('trashRecordId') for btn in buttons], [task['id']])

    def test_header_history_and_layout_actions(self):
        self.window.navigate('Notes')
        self.window.navigate('My Tasks')
        QTest.mouseClick(self.window.chrome.back, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.page, 'Notes')
        QTest.mouseClick(self.window.chrome.forward, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.page, 'My Tasks')
        self.window.show_calendar_layout('Week')
        self.assertEqual((self.window.page, self.window.calendar_view), ('Calendar', 'Week'))
        self.assertEqual(list(self.window.chrome.menus), ['File', 'Edit', 'View', 'Layout', 'Settings', 'Help'])
        for title, button in self.window.nav_buttons.items():
            self.assertEqual(button.text(), '')
            self.assertTrue(button.toolTip())

    def test_import_text_file_and_attach_only_capture_survive_save(self):
        source = Path(self.tmp.name) / 'A long document name for the project.md'
        source.write_text('# Imported heading\n\nKeep the original document.', encoding='utf-8')
        record = self.window.create_import_note([source])
        self.assertIn('Imported heading', record['body'])
        self.assertEqual(len(record['attachments']), 1)
        original_copy = self.store.attachments.path_for(record['attachments'][0])
        source.unlink()
        self.assertTrue(original_copy.exists())
        self.window.navigate('Notes')
        capture = self.window.capture
        capture.attachments.add_paths([original_copy])
        capture.pin.setChecked(True)
        capture.attachments.set_compact(True)
        saved = capture.flush()
        self.assertTrue(saved['pinned'])
        self.assertEqual(saved['attachment_display'], 'compact')
        self.assertEqual(len(saved['attachments']), 1)

    def test_empty_capture_can_close_and_expand_again(self):
        self.window.navigate('Notes')
        capture = self.window.capture
        capture.expand()
        self.assertEqual(capture.height(), 166)
        capture.commit()
        self.assertEqual(capture.height(), 54)
        capture.expand()
        self.assertEqual(capture.height(), 166)

    def test_tooltip_survives_unrelated_leave_and_does_not_restart(self):
        from PySide6.QtGui import QHelpEvent
        from PySide6.QtCore import QEvent
        anchor = self.window.chrome.back
        point = anchor.mapToGlobal(QPoint(10, 10))
        self.app.sendEvent(anchor, QHelpEvent(QEvent.Type.ToolTip, QPoint(10, 10), point))
        popup = self.app._tabla_polish.tooltip
        self.assertTrue(popup.isVisible())
        self.assertIsNone(popup.graphicsEffect())
        geometry = popup.geometry()
        self.app.sendEvent(self.window.chrome.forward, QEvent(QEvent.Type.Leave))
        self.assertTrue(popup.isVisible())
        self.app.sendEvent(anchor, QHelpEvent(QEvent.Type.ToolTip, QPoint(10, 10), point))
        self.assertEqual(popup.geometry(), geometry)
        self.app.sendEvent(anchor, QEvent(QEvent.Type.Leave))
        self.assertFalse(popup.isVisible())

    def test_header_qt_window_method_and_small_layout(self):
        self.assertIs(self.window.chrome.window(), self.window)
        self.window.resize(640, 480)
        self.window.navigate('Notes')
        QTest.qWait(120)
        self.assertEqual((self.window.width(), self.window.height()), (640, 480))
        self.assertTrue(self.window.chrome.overflow.isVisible())
        self.assertTrue(all(not b.isVisible() for b in self.window.chrome.menu_buttons))
        QTest.mouseMove(self.window.chrome, QPoint(5, 15))
        self.assertEqual(self.errors, [])

    def test_resize_reflow_keeps_unfinished_capture(self):
        self.window.navigate('Notes')
        capture = self.window.capture
        capture.body.setPlainText('Still writing this note')
        self.window.resize(640, 480)
        QTest.qWait(140)
        self.assertIs(self.window.capture, capture)
        self.assertEqual(capture.body.toPlainText(), 'Still writing this note')
        self.assertEqual(self.store.records('note'), [])

    def test_capture_grows_for_multiline_text_and_shrinks_on_delete(self):
        self.window.navigate('Notes')
        capture = self.window.capture
        QTest.qWait(150)
        text = '\n'.join('Line ' + str(n) for n in range(100))
        capture.body.setPlainText(text)
        QTest.qWait(100)
        self.assertLessEqual(capture.body.height(), 360)
        self.assertGreater(capture.body.verticalScrollBar().maximum(), 0)
        self.assertLess(capture.body.geometry().bottom(), capture.actions.y())
        self.assertEqual(capture.body.toPlainText(), text)
        capture.body.setPlainText('One short line')
        QTest.qWait(80)
        self.assertEqual(capture.body.height(), 64)
        self.assertEqual(capture.height(), 166)

    def test_capture_wraps_long_words_and_remeasures_on_resize(self):
        self.window.resize(1200, 850)
        self.window.navigate('Notes')
        capture = self.window.capture
        text = 'aVeryLongUnbrokenNote' * 45
        capture.body.setPlainText(text)
        QTest.qWait(100)
        wide_height = capture.body.height()
        self.window.resize(640, 480)
        QTest.qWait(180)
        self.assertIs(self.window.capture, capture)
        self.assertLessEqual(capture.body.height(), 150)
        self.assertGreater(capture.body.verticalScrollBar().maximum(), 0)
        self.assertEqual(capture.body.horizontalScrollBar().maximum(), 0)
        self.assertEqual(self.store.records('note'), [])

    def test_titlebar_search_runs_on_enter_and_preserves_note_capture(self):
        self.store.save({'kind': 'task', 'title': 'Search target', 'body': 'Project reference'})
        self.window.navigate('Notes')
        self.window.capture.body.setPlainText('An unfinished note to keep')
        self.window.focus_search()
        search = self.window.chrome.search
        self.assertIs(self.window.focusWidget(), search)
        search.setText('Project reference')
        self.assertEqual(self.window.page, 'Notes')
        QTest.keyClick(search, Qt.Key.Key_Return)
        self.assertEqual(self.window.page, 'Search')
        self.assertEqual(self.window.search_query, 'Project reference')
        self.assertEqual(self.store.records('note')[0]['body'], 'An unfinished note to keep')
        self.assertTrue(any(b.text() == 'Search target' for b in self.window.workspace.findChildren(QPushButton)))
        self.window.resize(500, 400)
        QTest.qWait(120)
        self.assertTrue(search.isVisible())
        self.assertGreaterEqual(search.width(), 80)

    def test_open_note_sidecar_lists_links_backlinks_and_source_files(self):
        from tabla.dialogs import NoteDialog
        target = self.store.save({'kind': 'note', 'title': 'Reference idea', 'body': 'Supporting details'})
        source = Path(self.tmp.name) / 'Meeting reference.md'
        source.write_text('# Reference file', encoding='utf-8')
        files = self.store.attachments.import_files([source])
        note = self.store.save({'kind': 'note', 'title': 'Meeting notes', 'body': 'Read [[' + target['id'] + ']]', 'attachments': files})
        incoming = self.store.save({'kind': 'task', 'title': 'Follow up', 'body': '[[' + note['id'] + ']]'})
        dialog = NoteDialog(self.store, note, parent=self.window)
        dialog.show()
        QTest.qWait(100)
        self.assertFalse(hasattr(dialog, 'tabs'))
        dialog.resize(420, 600)
        dialog.move(0, 100)
        dialog.layout_context()
        self.assertTrue(dialog.sidecar.isVisible())
        self.assertTrue(dialog.sidecar.isAncestorOf(dialog.attachments))
        self.assertTrue(dialog.sidecar.isWindow())
        self.assertGreater(dialog.sidecar.x(), dialog.geometry().right())
        self.assertEqual(dialog.sources_heading.text(), 'Sources  1')
        outgoing = next(b for b in dialog.sidecar.findChildren(QPushButton) if b.property('linkTarget') == target['id'])
        self.assertTrue(any(b.property('backlinkTarget') == incoming['id'] for b in dialog.sidecar.findChildren(QPushButton)))
        QTest.mouseClick(outgoing, Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.pending_navigation, target['id'])
        self.assertEqual(self.store.get(note['id'])['attachments'], files)
        dialog.deleteLater()

    def test_note_sidecar_collapses_for_compact_editing_without_losing_changes(self):
        from tabla.dialogs import NoteDialog
        dialog = NoteDialog(self.store, parent=self.window)
        dialog.resize(640, 520)
        dialog.show()
        QTest.qWait(100)
        self.assertFalse(hasattr(dialog, 'tabs'))
        dialog._context_visible = False
        dialog.layout_context()
        dialog.title.setText('A compact draft')
        dialog.editor.setPlainText('Still writing with context nearby.')
        QTest.mouseClick(dialog.context_toggle, Qt.MouseButton.LeftButton)
        self.assertTrue(dialog.sidecar.isVisible())
        self.assertTrue(dialog.sidecar.isWindow())
        self.assertEqual(dialog.editor.toPlainText(), 'Still writing with context nearby.')
        QTest.mouseClick(dialog.context_toggle, Qt.MouseButton.LeftButton)
        self.assertFalse(dialog.sidecar.isVisible())
        dialog.close()
        self.assertEqual(self.store.get(dialog.record['id'])['body'], 'Still writing with context nearby.')
        dialog.deleteLater()

    def test_color_swatches_and_reduce_motion_are_real_controls(self):
        from tabla.dialogs import ItemDialog
        dialog = ItemDialog(self.store, 'project', parent=self.window)
        dialog.title.setText('Swatch project')
        QTest.mouseClick(dialog.color.swatches['rose'], Qt.MouseButton.LeftButton)
        dialog.save()
        self.assertEqual(dialog.result_record['color'], 'rose')
        self.window.set_reduce_motion(True)
        self.assertTrue(self.app.property('reduceMotion'))
        self.assertTrue(self.store.setting('reduce_motion'))
        dialog.deleteLater()

    def test_notes_use_only_the_header_search(self):
        from PySide6.QtWidgets import QLineEdit
        self.window.navigate('Notes')
        self.assertTrue(self.window.chrome.search.isVisible())
        self.assertFalse(any(field.placeholderText() == 'Search notes and labels' for field in self.window.findChildren(QLineEdit)))
        self.window.set_note_filters_visible(True)
        self.assertFalse(any(field.placeholderText() == 'Search notes and labels' for field in self.window.findChildren(QLineEdit)))

    def test_card_click_passes_exact_origin_and_image_to_editor(self):
        from PySide6.QtCore import QRect
        note = self.store.save({'kind': 'note', 'title': 'Animate from this card', 'body': 'A visible idea'})
        card = self.window.note_card(note)
        card.resize(240, 190)
        card.show()
        self.app.processEvents()
        expected = QRect(card.mapToGlobal(QPoint()), card.size())
        captured = []
        self.window.edit_note = lambda current: captured.append((self.window._note_origin, self.window._note_snapshot))
        QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=QPoint(4, 4))
        self.assertEqual(captured[0][0], expected)
        self.assertFalse(captured[0][1].isNull())
        card.close()
        card.deleteLater()

    def test_notes_bottom_layer_is_lightweight_and_click_through(self):
        self.store.seed_demo()
        self.window.navigate('Notes')
        for _ in range(12):
            QTest.qWait(50)
            edge = self.window.notes_edge
            if edge.isVisible():
                break
        self.assertTrue(edge.isVisible())
        self.assertEqual(edge.height(), 28)
        self.assertTrue(edge.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertTrue(edge.image.isNull(), 'Scrolling must not require gallery screenshot blur')
        self.assertEqual(edge.geometry().bottom(), self.window.notes_scroll.viewport().height() - 1)


if __name__ == '__main__':
    unittest.main()
