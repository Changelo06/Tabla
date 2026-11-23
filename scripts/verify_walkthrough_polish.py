"""Native visual/interaction checks for the October 22 recording fixes."""
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
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env,
                   startupinfo=startup, check=True, timeout=100)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT))
from datetime import date
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QMenu
from PySide6.QtCore import Qt, QTimer, QEvent, QCoreApplication, QPoint
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.dialogs import ItemDialog, PolishedDialog
from tabla.polish import ColorPicker
from tabla.surfaces import CalendarCell
from tabla.theme import load_fonts

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
errors = []
def error_hook(kind, value, tb):
    import traceback
    errors.append(str(value))
    traceback.print_exception(kind, value, tb)
sys.excepthook = error_hook
shots = ROOT / 'design' / 'screenshots'

def capture(window, name, overlay=None):
    pixmap = QPixmap(window.size())
    painter = QPainter(pixmap)
    painter.drawPixmap(0, 0, window.grab())
    if overlay:
        painter.drawPixmap(window.mapFromGlobal(overlay.pos()), overlay.grab())
    popup = app.activePopupWidget()
    if popup and popup is not overlay:
        painter.drawPixmap(window.mapFromGlobal(popup.pos()), popup.grab())
    painter.end()
    assert pixmap.save(str(shots / ('walkthrough-' + name + '.png')))

with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
    store = Store(Path(folder) / 'tabla.sqlite3')
    store.set_setting('reduce_motion', True)
    project = store.save({'kind': 'project', 'title': 'ByaheNOW PID System', 'color': 'yellow', 'body': 'A clearer project workspace.'})
    task = store.save({'kind': 'task', 'title': 'Review project brief', 'project': project['id'], 'date': '2026-11-15'})
    event = store.save({'kind': 'event', 'title': 'End of Phase 1', 'project': project['id'], 'date': '2026-11-15', 'time': '09:00', 'end_time': '10:00', 'color': 'rose'})
    window = TablaWindow(store)
    window.resize(1500, 900)
    window.show()
    QTest.qWait(400)
    try:
        for appearance in ('Light', 'Dark'):
            window.set_appearance(appearance)
            QTest.qWait(250)
            window.project_id = project['id']
            window.page = 'Calendar'
            window.month = date(2026, 11, 1)
            window.render()
            QTest.qWait(200)
            headers = window.workspace.findChildren(QLabel, 'weekdayHeader')
            assert len(headers) == 7
            assert all(not window.calendar_scroll.isAncestorOf(h) for h in headers)
            before = [h.mapTo(window.workspace, QPoint()).y() for h in headers]
            window.calendar_scroll.verticalScrollBar().setValue(99999)
            app.processEvents()
            assert before == [h.mapTo(window.workspace, QPoint()).y() for h in headers]
            capture(window, 'calendar-' + appearance.lower())
            for kind in ('project', 'task', 'event', 'block'):
                record = project if kind == 'project' else event if kind == 'event' else None
                dialog = ItemDialog(store, kind, record=record, project=project['id'], day='2026-11-15', parent=window)
                dialog.show()
                QTest.qWait(130)
                assert dialog._surface_backdrop is not None and dialog._surface_backdrop.isVisible()
                assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
                if kind == 'task':
                    dialog.save()
                    assert dialog.title.property('invalid') and 'title' in dialog.error.text()
                    assert dialog.error.y() < dialog.project.y()
                    capture(window, 'title-error-' + appearance.lower(), dialog)
                    dialog.title.setFocus()
                    QTest.keyClicks(dialog.title, 'A real task')
                    assert not dialog.title.property('invalid')
                    dialog.project.showPopup()
                    QTest.qWait(80)
                    capture(window, 'dropdown-' + appearance.lower(), dialog)
                    dialog.project.hidePopup()
                if kind == 'block':
                    dialog.title.setText('Focused work')
                    dialog.task.setCurrentIndex(dialog.task.findData(task['id']))
                capture(window, kind + '-' + appearance.lower(), dialog)
                dialog.reject()
                assert dialog._surface_backdrop is None
                dialog.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

            def inspect_day():
                dialog = app.activeModalWidget()
                assert isinstance(dialog, PolishedDialog)
                assert dialog._surface_backdrop and dialog._surface_backdrop.isVisible()
                picker = dialog.findChild(ColorPicker)
                picker.setCurrentText('rose')
                assert dialog.isVisible(), 'Highlight selection unexpectedly closed the day'
                assert picker.swatches['rose'].isChecked()
                assert window.day_annotation(date(2026, 11, 15))['day_color'] == 'rose'
                picker.setCurrentText('None')
                assert window.day_annotation(date(2026, 11, 15))['day_color'] is None
                capture(window, 'day-' + appearance.lower(), dialog)
                dialog.reject()
            QTimer.singleShot(150, inspect_day)
            window.day_dialog(date(2026, 11, 15))
            assert not errors, errors

            def inspect_projects():
                menu = app.activePopupWidget()
                assert isinstance(menu, QMenu)
                entries = [a for a in menu.actions() if a.text() == project['title']]
                assert len(entries) == 1 and entries[0].isChecked()
                menu.setActiveAction(menu.actions()[-1])
                capture(window, 'projects-' + appearance.lower(), menu)
                menu.close()
            QTimer.singleShot(100, inspect_projects)
            projects_button = next(b for b in window.sidebar.findChildren(QPushButton) if b.accessibleName() == 'Projects')
            projects_button.click()
            assert not errors, errors
            print(appearance, 'dialogs/backdrops, field errors, project menu, highlight/clear, sticky weekdays passed')

        window.resize(640, 480)
        QTest.qWait(350)
        assert window.width() == 640
        assert window.calendar_scroll.verticalScrollBar().maximum() > 0
        window.calendar_scroll.verticalScrollBar().setValue(99999)
        headers = window.workspace.findChildren(QLabel, 'weekdayHeader')
        assert all(h.isVisible() for h in headers)
        capture(window, 'compact-calendar')
        compact = ItemDialog(store, 'event', record=event, parent=window)
        compact.show()
        QTest.qWait(130)
        assert compact.height() <= window.height()
        assert compact.form_scroll.verticalScrollBar().maximum() > 0
        save = next(b for b in compact.findChildren(QPushButton) if b.text() == 'Save')
        assert save.isVisible() and save.mapTo(compact, QPoint()).y() + save.height() <= compact.height()
        capture(window, 'compact-editor', compact)
        compact.reject()
        compact.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert store.get(project['id'])['body'] == project['body']
        assert store.get(event['id'])['color'] == 'rose'
        assert not errors, errors
        print('Compact calendar/editor, reachable footer and retained records passed')
    finally:
        window.timer.pause()
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        store.close()
