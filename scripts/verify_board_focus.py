"""Windows QA for task boards, full card details and non-native picker surfaces."""
import os
import sys
import subprocess
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if '--child' not in sys.argv:
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
        env.pop(key, None)
    env.update(QT_QPA_PLATFORM='windows', PATH=r'C:\Windows\System32;C:\Windows', PYTHONFAULTHANDLER='1', PYTHONUNBUFFERED='1')
    startup = subprocess.STARTUPINFO(); startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env, startupinfo=startup, check=True, timeout=100)
    raise SystemExit(0)
sys.path.insert(0, str(ROOT))
from datetime import date, timedelta
from PySide6.QtWidgets import QApplication, QPushButton, QComboBox, QLineEdit
from PySide6.QtCore import Qt, QPoint, QPointF, QTimer, QMimeData, QEvent, QCoreApplication
from PySide6.QtGui import QPixmap, QPainter, QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtTest import QTest
from tabla.workspace import TablaWindow
from tabla.storage import Store
from tabla.board_model import BoardModel
from tabla.task_board import CardList, ListPanel, CARD_MIME, LIST_MIME
from tabla.task_card import TaskCardDialog
from tabla.pickers import ChoiceMenu, CalendarPicker
from tabla.theme import load_fonts

app = QApplication([]); app.setStyle('Fusion'); load_fonts()
errors = []
def report(kind, value, tb):
    import traceback
    errors.append(str(value)); traceback.print_exception(kind, value, tb)
sys.excepthook = report
def shot(window, name, overlay=None):
    canvas = QPixmap(window.size()); p = QPainter(canvas); p.drawPixmap(0, 0, window.grab())
    if overlay:
        p.drawPixmap(window.mapFromGlobal(overlay.pos()), overlay.grab())
    popup = app.activePopupWidget()
    if popup and popup is not overlay:
        p.drawPixmap(window.mapFromGlobal(popup.pos()), popup.grab())
    p.end(); assert canvas.save(str(ROOT / 'design' / 'screenshots' / ('board-focus-' + name + '.png')))

with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
    store = Store(Path(folder) / 'tabla.sqlite3'); store.set_setting('reduce_motion', True)
    model = BoardModel(store); review = model.add_list('Review')
    source = Path(folder) / 'Design brief.txt'; source.write_text('Keep this attachment')
    files = store.attachments.import_files([source])
    records = []
    for title, column, color, due in [('Sketch the new dashboard', 'todo', 'blue', 1), ('Polish task cards and interactions', 'doing', 'violet', 2), ('Review the launch checklist', review, 'yellow', 3), ('Set up the project workspace', 'done', 'green', 0)]:
        task = store.save({'kind': 'task', 'title': title, 'body': 'A useful description and [[linked idea]].', 'date': (date.today() + timedelta(days=due)).isoformat(), 'task_labels': [{'name': 'Design' if color == 'blue' else 'Build', 'color': color}], 'cover': color,
            'checklists': [{'id': 'c', 'title': 'Next steps', 'items': [{'id': 'a', 'text': 'Collect references', 'checked': True}, {'id': 'b', 'text': 'Make the first draft', 'checked': False}]}], 'attachments': files})
        records.append(model.move_card(task['id'], column))
    window = TablaWindow(store); window.resize(1500, 900); window.show(); QTest.qWait(400)
    try:
        for appearance in ('Light', 'Dark'):
            window.set_appearance(appearance); QTest.qWait(250)
            window.navigate('My Tasks'); QTest.qWait(150)
            assert window.task_view == 'Board'
            assert not window.board.findChildren(QComboBox)
            assert len(window.board.findChildren(ListPanel)) == 4
            shot(window, 'board-' + appearance.lower())
            destination = next(x for x in window.board.findChildren(ListPanel) if x.column['id'] == 'doing')
            list_mime = QMimeData(); list_mime.setData(LIST_MIME, review.encode())
            app.sendEvent(destination, QDragEnterEvent(QPoint(15, 15), Qt.DropAction.MoveAction, list_mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
            app.sendEvent(destination, QDropEvent(QPointF(15, 15), Qt.DropAction.MoveAction, list_mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
            QTest.qWait(80)
            assert [c['id'] for c in model.lists()] == ['todo', review, 'doing', 'done']
            model.move_list(review)
            window.refresh(); QTest.qWait(80)
            todo = next(x for x in window.board.findChildren(ListPanel) if x.column['id'] == 'todo')
            todo.open_composer(); todo.input.setText('A card added inline'); todo.add_card()
            assert todo.input.hasFocus() and todo.composer.isVisible()
            assert todo.cards.count() >= 2
            todo.input.setText('Keep this unfinished card')
            window.refresh(); QTest.qWait(80)
            todo = next(x for x in window.board.findChildren(ListPanel) if x.column['id'] == 'todo')
            assert todo.composer.isVisible() and todo.input.text() == 'Keep this unfinished card'
            todo.close_composer()
            target = next(x for x in window.board.findChildren(CardList) if x.column['id'] == 'doing')
            mime = QMimeData(); mime.setData(CARD_MIME, records[0]['id'].encode())
            point = QPoint(20, 8)
            app.sendEvent(target.viewport(), QDragEnterEvent(point, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
            app.sendEvent(target.viewport(), QDragMoveEvent(point, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
            app.sendEvent(target.viewport(), QDropEvent(QPointF(point), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
            QTest.qWait(150)
            assert store.get(records[0]['id'])['status'] == 'In progress'

            def inspect_card():
                dialog = app.activeModalWidget(); assert isinstance(dialog, TaskCardDialog)
                assert dialog.labels_data and dialog.checklists and dialog.attachments.items
                shot(window, 'card-' + appearance.lower(), dialog)
                dialog.day.setDate(__import__('PySide6.QtCore', fromlist=['QDate']).QDate(2020, 1, 1))
                QTest.mouseClick(dialog.day, Qt.MouseButton.LeftButton, pos=QPoint(dialog.day.width() - 10, dialog.day.height() // 2))
                QTest.qWait(80)
                assert isinstance(dialog.day.calendarWidget(), CalendarPicker)
                assert dialog.day.calendarWidget().isVisible()
                shot(window, 'calendar-picker-' + appearance.lower(), dialog)
                dialog.day.calendarWidget().choose_today()
                QTest.qWait(30)
                assert dialog.day.date().toPython() == date.today()
                dialog.area.verticalScrollBar().setValue(450); QTest.qWait(30)
                shot(window, 'card-checklists-' + appearance.lower(), dialog)
                dialog.comment.setText('Verified in ' + appearance); dialog.add_comment()
                assert dialog.save()
            QTimer.singleShot(180, inspect_card)
            window.open_record(records[0]['id'])
            assert not errors, errors
            window.navigate('Focus'); QTest.qWait(120)
            assert not window.workspace.findChildren(QComboBox)
            shot(window, 'pomodoro-' + appearance.lower())
            def choose_focus():
                menu = app.activePopupWidget(); assert isinstance(menu, ChoiceMenu)
                search = menu.findChild(QLineEdit); search.setText('Sketch')
                assert sum(not menu.list.item(i).isHidden() for i in range(menu.list.count())) == 1
                shot(window, 'focus-picker-' + appearance.lower(), menu)
                menu.select(next(menu.list.item(i) for i in range(menu.list.count()) if not menu.list.item(i).isHidden()))
            QTimer.singleShot(100, choose_focus)
            window.focus_choose.click(); QTest.qWait(100)
            assert window.timer.data['task'] == records[0]['id'] and not window.timer.data['running']
            window.toggle_timer(); window.tick()
            assert not window.focus_choose.isEnabled()
            window.timer.pause(); window.tick()
            assert window.focus_choose.isEnabled()
            print(appearance, 'board, inline capture, drop, card details, date popup and focus picker passed')
            model.move_card(records[0]['id'], 'todo')
        window.navigate('My Tasks'); window.resize(640, 480); QTest.qWait(350)
        assert window.width() == 640
        assert window.board.horizontalScrollBar().maximum() > 0
        shot(window, 'compact-board')
        window.board.horizontalScrollBar().setValue(window.board.horizontalScrollBar().maximum())
        position = window.board.horizontalScrollBar().value()
        window.refresh(); QTest.qWait(120)
        assert window.board.horizontalScrollBar().value() == position, 'Board jumped after refresh'
        archived = store.get(records[2]['id']); archived['archived'] = True; store.save(archived)
        model.archive_list(review)
        def restore_archive():
            dialog = app.activeModalWidget()
            restore = next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Restore list')
            restore.click()
            QTest.qWait(40)
            card_restore = next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Restore card' and b.isVisible())
            card_restore.click()
            dialog.reject()
        QTimer.singleShot(150, restore_archive)
        window.board_archive()
        assert not store.get(records[2]['id'])['archived']
        assert not errors, errors
        assert store.attachments.path_for(store.get(records[0]['id'])['attachments'][0]).read_text() == 'Keep this attachment'
        print('Compact horizontal board and retained attachment bytes passed')
    finally:
        window.timer.pause(); window.close(); window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        store.close()
