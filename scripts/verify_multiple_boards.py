"""Independent native boards: creation, isolation, retained state and compact UI."""
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
    env.update(QT_QPA_PLATFORM='windows', PATH=r'C:\Windows\System32;C:\Windows', PYTHONUNBUFFERED='1', PYTHONFAULTHANDLER='1')
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env, startupinfo=startup, check=True, timeout=100)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT))
import time
import json
from PySide6.QtWidgets import QApplication, QLineEdit, QComboBox, QPushButton
from PySide6.QtCore import QEvent, QCoreApplication, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.boards import BoardCatalog
from tabla.board_model import BoardModel
from tabla.workspace import TablaWindow
from tabla.task_board import ListPanel
from tabla.task_card import TaskCardDialog
from tabla.pickers import ChoiceMenu
from tabla.theme import load_fonts

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
app.setFont(QFont('Inter', 10))
errors = []
def report_error(kind, value, tb):
    import traceback
    traceback.print_exception(kind, value, tb)
    errors.append(str(value))
sys.excepthook = report_error
with tempfile.TemporaryDirectory(prefix='tabla-multiple-boards-') as folder:
    store = Store(Path(folder) / 'tabla.sqlite3')
    project = store.save({'kind': 'project', 'title': 'Website refresh', 'color': 'violet'})
    second = store.save({'kind': 'project', 'title': 'Research', 'color': 'blue'})
    original = store.save({'kind': 'task', 'title': 'Review the opening message', 'status': 'To do', 'project': project['id']})
    store.set_setting('boards_sidebar_hidden', True)
    window = TablaWindow(store)
    catalog = BoardCatalog(store)
    design = next(b for b in catalog.boards() if b.get('project') == project['id'])
    design['title'] = 'Design'
    store.save(design)
    development = catalog.create('Development', project['id'])
    catalog.create('Launch', project['id'])
    catalog.create('Reading list', second['id'])
    catalog.create('Experiments', second['id'])
    catalog.create('Personal planning')
    for title, status, board_id, color in [
        ('Sketch the navigation', 'To do', design['id'], 'violet'),
        ('Choose three featured projects', 'In progress', design['id'], 'blue'),
        ('Prepare the image references', 'Done', design['id'], 'green'),
        ('Build the homepage', 'To do', development['id'], 'blue')]:
        store.save({'kind': 'task', 'title': title, 'status': status, 'board': board_id,
                    'cover': color, 'task_labels': [{'name': 'Design' if board_id == design['id'] else 'Build', 'color': color}],
                    'body': 'Keep the next action clear.'})
    window.resize(1500, 900)
    window.show()
    window.select_board(design['id'])
    QTest.qWait(350)
    assert not window.boards_sidebar.isVisible()
    canvas = window.board
    window.boards_toggle.click()
    QTest.qWait(200)
    assert window.boards_sidebar.isVisible() and window.board is canvas
    assert not store.setting('boards_sidebar_hidden')
    for theme in ('Light', 'Dark'):
        window.set_appearance(theme)
        QTest.qWait(300)
        assert window.boards_sidebar.isVisible()
        assert len(window.board.records) == 4
        assert all(p.cards.verticalScrollBar().maximum() == 0 for p in window.board.findChildren(ListPanel))
        window.grab().save(str(ROOT / 'design' / 'screenshots' / ('multiple-boards-' + theme.lower() + '.png')))
        hide = next(b for b in window.boards_sidebar.findChildren(QPushButton) if b.text() == 'Hide')
        assert hide.width() >= 64 and hide.height() >= 36
        assert window.boards_toggle.text() == 'Hide'
        def configure_list():
            dialog = app.activeModalWidget()
            picker = next(b for b in dialog.findChildren(QPushButton) if b.accessibleName() == 'Completed card destination')
            def choose_destination():
                menu = app.activePopupWidget()
                assert isinstance(menu, ChoiceMenu)
                item = next(menu.list.item(i) for i in range(menu.list.count()) if menu.list.item(i).data(Qt.ItemDataRole.UserRole) == 'doing')
                menu.select(item)
            QTimer.singleShot(60, choose_destination)
            picker.click()
            dialog.grab().save(str(ROOT / 'design' / 'screenshots' / ('list-settings-' + theme.lower() + '.png')))
            next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Save').click()
        QTimer.singleShot(80, configure_list)
        window.board.list_settings('todo')
        assert BoardModel(store, design['id']).lists()[0]['completion_target'] == 'doing'
    card_dialog = TaskCardDialog(store, store.get(original['id']), parent=window)
    card_dialog.completed.setChecked(True)
    assert card_dialog.save()
    assert store.get(original['id'])['board_list'] == 'doing'
    assert store.get(original['id'])['status'] == 'Done'
    card_dialog.deleteLater()
    sidebar = window.boards_sidebar
    panel = window.board.findChildren(ListPanel)[0]
    panel.open_composer()
    panel.input.setText('An unfinished design card')
    window.select_board(development['id'])
    assert len(window.board.records) == 1
    window.select_board(design['id'])
    assert window.board.findChildren(ListPanel)[0].input.text() == 'An unfinished design card'
    canvas = window.board
    window.board.move_card(original['id'], 'doing')
    assert window.board is canvas and window.boards_sidebar is sidebar
    model = BoardModel(store, design['id'])
    model.rename('todo', 'Ideas')
    window.board.reconcile()
    assert BoardModel(store, development['id']).lists()[0]['title'] == 'To do'
    # Exercise the actual New board form and project association.
    def create_in_form():
        dialog = app.activeModalWidget()
        name = next(w for w in dialog.findChildren(QLineEdit) if w.accessibleName() == 'Board name')
        name.setText('Content calendar')
        combo = dialog.findChildren(QComboBox)[0]
        combo.setCurrentIndex(combo.findData(project['id']))
        next(b for b in dialog.findChildren(QPushButton) if b.text() == 'Create board').click()
    QTimer.singleShot(80, create_in_form)
    window.new_board()
    assert store.get(window.board_id)['title'] == 'Content calendar'
    assert store.get(window.board_id)['project'] == project['id']
    created_id = window.board_id
    window.archive_board(created_id)
    assert store.get(created_id)['archived']
    restored = store.get(created_id)
    restored['archived'] = False
    store.save(restored)
    window.select_board(created_id)
    window.resize(640, 480)
    QTest.qWait(250)
    assert not sidebar.isVisible()
    assert window.boards_toggle.accessibleName() == 'Choose a board'
    window.grab().save(str(ROOT / 'design' / 'screenshots' / 'multiple-boards-compact.png'))
    window.resize(1500, 900)
    QTest.qWait(250)
    # A synthetic stress board; measure only actual operations on this laptop.
    stress = catalog.create('Load check')
    with store.atomic():
        for i in range(500):
            store.save({'kind': 'task', 'title': 'Reference card ' + str(i), 'board': stress['id'],
                        'board_list': ('todo', 'doing', 'done')[i % 3], 'status': ('To do', 'In progress', 'Done')[i % 3], 'board_position': i * 1024})
    start = time.perf_counter()
    window.select_board(stress['id'])
    app.processEvents()
    switched = (time.perf_counter() - start) * 1000
    first_card = window.board.records[0]
    before = window.board
    start = time.perf_counter()
    window.board.move_card(first_card['id'], 'doing')
    app.processEvents()
    moved = (time.perf_counter() - start) * 1000
    assert window.board is before
    print(json.dumps({'synthetic_cards': 500, 'switch_ms_single_sample': round(switched, 1), 'move_ms_single_sample': round(moved, 1)}), flush=True)
    window.select_board(design['id'])
    window.timer.pause()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    store.close()
    reopened = Store(Path(folder) / 'tabla.sqlite3')
    assert reopened.setting('selected_board') == design['id']
    assert not reopened.setting('boards_sidebar_hidden')
    assert reopened.get(original['id'])['board'] == design['id']
    assert reopened.setting('board_view_' + design['id'])['drafts']['todo']['text'] == 'An unfinished design card'
    reopened.close()
    assert not errors, errors
print('PASS multiple boards/project, creation form, independent lists/cards, retained drafts, archive/recovery, compact layout and reopen', flush=True)
