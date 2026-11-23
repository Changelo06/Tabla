"""Native Home dashboard checks against disposable records only."""
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
    env.update(QT_QPA_PLATFORM='windows', PATH=r'C:\Windows\System32;C:\Windows', PYTHONFAULTHANDLER='1')
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env, startupinfo=startup, check=True, timeout=90)
    raise SystemExit(0)
sys.path.insert(0, str(ROOT))
from datetime import date, timedelta
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtGui import QFont, QWheelEvent
from PySide6.QtCore import QTimer, QCoreApplication, QEvent, QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.theme import load_fonts
app = QApplication([])
app.setStyle('Fusion')
load_fonts()
app.setFont(QFont('Inter', 10))
errors = []
sys.excepthook = lambda kind, value, tb: errors.append(str(value))
with tempfile.TemporaryDirectory(prefix='tabla-home-') as folder:
    store = Store(Path(folder) / 'tabla.sqlite3')
    window = TablaWindow(store)
    project = store.save({'kind': 'project', 'title': 'Website refresh'})
    for title in ('Design', 'Development', 'Launch', 'Research', 'Personal planning', 'Reading list'):
        window.board_catalog.create(title, project['id'] if title in ('Design', 'Development', 'Launch') else None)
    for i, title in enumerate(('Review the opening message', 'Prepare image references', 'Send the project outline', 'Plan next week')):
        store.save({'kind': 'task', 'title': title, 'date': (date.today() + timedelta(days=i - 1)).isoformat(), 'status': 'To do'})
    for title, text, color in (
        ('A quieter place to think', 'One thing at a time.\n\nMake room for ideas before turning them into a plan.', 'gray'),
        ('For the next release', '- [ ] Refine the small details\n- [ ] Review the first impression\n- [x] Keep the useful parts', 'blue'),
        ('Weekend reading', 'A few pages, a fresh perspective.\n\nSave the ideas worth returning to.', 'gray'),
        ('Project direction', 'Clear writing. Calm navigation.\n\nSmall choices that make the whole workspace feel considered.', 'yellow')):
        store.save({'kind': 'note', 'title': title, 'body': text, 'color': color})
    window.resize(1500, 960)
    window.show()
    window.navigate('Today')
    for theme in ('Light', 'Dark'):
        window.set_appearance(theme)
        QTest.qWait(250)
        assert len(window.home.notes) == 4 and len(window.home.due_tasks) == 4
        area = window.home.parentWidget().parentWidget()
        assert area.horizontalScrollBar().maximum() == 0
        assert window.home.wide
        from tabla.home import HomeLink
        assert all(w.height() >= (44 if w.compact else 60) for w in window.home.findChildren(HomeLink))
        assert window.home.mode == 3
        assert window.home.left.x() < window.home.deadlines.x() < window.home.notes_section.x()
        assert window.home.notes_section.y() == window.home.deadlines.y()
        window.grab().save(str(ROOT / 'design' / 'screenshots' / ('home-' + theme.lower() + '.png')))
    # Match the reported one-board workspace, with enough note previews to overflow.
    for board in window.board_catalog.boards():
        if board['id'] != window.board_id:
            board['archived'] = True
            store.save(board)
    for note in store.records('note'):
        note['body'] = '- [ ] A checklist item with a comfortably long title\n' * 8
        store.save(note)
    window.resize(1500, 680)
    window.navigate('Today')
    QTest.qWait(250)
    home = window.home
    assert home.page_area.verticalScrollBar().maximum() == 0
    assert home.notes_area.verticalScrollBar().maximum() > 0
    fixed = [home.calendar, home.board_section, home.deadlines, home.notes_section.layout().itemAt(0).widget()]
    before = [w.mapToGlobal(QPoint()) for w in fixed]
    viewport = home.notes_area.viewport()
    point = viewport.rect().center()
    wheel = QWheelEvent(QPointF(point), QPointF(viewport.mapToGlobal(point)), QPoint(), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, False)
    app.sendEvent(viewport, wheel)
    QTest.qWait(100)
    assert home.notes_area.verticalScrollBar().value() > 0
    assert before == [w.mapToGlobal(QPoint()) for w in fixed]
    assert home.page_area.verticalScrollBar().value() == 0
    window.grab().save(str(ROOT / 'design' / 'screenshots' / 'home-notes-scroll.png'))
    # Open the actual note editor from Home, then return using Close.
    note_id = window.home.notes[0]['id']
    def close_note():
        dialog = app.activeModalWidget()
        assert dialog is not None
        close = next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Close')
        close.click()
    QTimer.singleShot(300, close_note)
    window.home.note_cards[0].clicked.emit()
    QTest.qWait(220)
    assert window.page == 'Today' and store.get(note_id)
    for width, height, name in ((1000, 740, 'medium'), (640, 600, 'compact'), (500, 450, 'small')):
        window.resize(width, height)
        QTest.qWait(250)
        area = window.home.parentWidget().parentWidget()
        assert area.horizontalScrollBar().maximum() == 0, (name, area.horizontalScrollBar().maximum())
        assert all(c.width() > 0 for c in window.home.note_cards)
        window.grab().save(str(ROOT / 'design' / 'screenshots' / ('home-' + name + '.png')))
    chosen = date.today() + timedelta(days=2)
    window.home.calendar.open_day(chosen)
    QTest.qWait(100)
    assert window.selected_day == chosen and window.calendar_view == 'Day'
    window.timer.pause()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    store.close()
    assert not errors, errors
print('PASS Home: light/dark, four latest notes, actual note open/close, deadlines, calendar navigation and 1500/1000/640/500 layouts')
