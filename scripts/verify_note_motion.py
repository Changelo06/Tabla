"""Exercise real card clicks and the opening animation using native Windows Qt."""
import os
import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if '--child' not in sys.argv:
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
        env.pop(key, None)
    env['QT_QPA_PLATFORM'] = 'windows'
    env['PATH'] = r'C:\Windows\System32;C:\Windows'
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env, startupinfo=startup, check=True, timeout=30)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtCore import Qt, QTimer, QPoint, QRect
from PySide6.QtGui import QPixmap, QPainter, QFont
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.theme import load_fonts
from tabla.workspace import TablaWindow
from tabla.dialogs import NoteDialog
from tabla.widgets import ClickCard

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
app.setFont(QFont('Inter', 10))
errors, results = [], []
def report_error(kind, value, tb):
    import traceback
    errors.append(str(value))
    traceback.print_exception(kind, value, tb)
sys.excepthook = report_error
profile = ROOT / 'build' / 'note-motion-qa'
store = Store(profile / 'tabla.sqlite3')
if not store.records():
    store.seed_demo()
store.set_setting('reduce_motion', False)
window = TablaWindow(store)
window.resize(1500, 900)
window.show()
window.navigate('Notes')
window.set_appearance('Dark')
QTest.qWait(100)

def probe(callback):
    def run():
        try:
            callback()
        except Exception as exc:
            import traceback
            traceback.print_exc()
            errors.append(str(exc))
            active = app.activeModalWidget()
            if active:
                active.reject()
    return run

def click_card(callback):
    QTest.qWait(180)
    card = next(c for c in window.workspace.findChildren(ClickCard) if c.isVisible())
    origin = QRect(card.mapToGlobal(QPoint()), card.size())
    QTimer.singleShot(50, probe(lambda: callback(origin)))
    QTest.mouseClick(card, Qt.MouseButton.LeftButton, pos=QPoint(5, 5))
    QTest.qWait(30)
    assert not errors, errors

def opening(origin):
    dialog = app.activeModalWidget()
    assert isinstance(dialog, NoteDialog)
    overlay = dialog._morph_overlay
    assert overlay and overlay.isVisible(), 'No card-to-note transition was shown'
    if overlay.progress == 0:
        QTimer.singleShot(45, probe(lambda: opening(origin)))
        return
    assert overlay.origin == origin, 'Transition did not start at the clicked card'
    assert overlay.target == dialog.geometry()
    assert overlay.geometry() != overlay.target and overlay.geometry() != overlay.origin
    assert 0 < overlay.progress < 1
    opening_duration = overlay.animation.duration()
    canvas = QPixmap(window.size())
    painter = QPainter(canvas)
    painter.drawPixmap(0, 0, window.grab())
    painter.drawPixmap(window.mapFromGlobal(overlay.pos()), overlay.grab())
    painter.end()
    canvas.save(str(ROOT / 'design' / 'screenshots' / 'note-opening-midpoint.png'))
    def finished():
        assert dialog._morph_overlay is None and not dialog._opening_pending
        assert dialog.windowOpacity() == 1
        assert dialog.sidecar.isVisible()
        assert not any(e.placeholderText() == 'Search notes and labels' for e in window.findChildren(QLineEdit))
        results.append('Actual card click expands into the centered editor; snapshot and opacity clean up')
        dialog.editor.insertPlainText('Saved before closing ')
        dialog.accept()
        assert dialog._closing_pending and dialog._closing_overlay is not None
        assert 'Saved before closing ' in store.get(dialog.record['id'])['body']
        assert dialog._closing_overlay.animation.duration() < opening_duration
        def closing_frame():
            closing = dialog._closing_overlay
            assert closing and 0 < closing.progress < 1, 'No intermediate closing animation'
            assert closing.geometry() != closing.target
            assert dialog._backdrop and 0 < dialog._backdrop.strength < 1
            results.append('Close saves first, returns toward the card faster, and eases background blur out')
        QTimer.singleShot(45, probe(closing_frame))
    QTimer.singleShot(280, probe(finished))

try:
    click_card(opening)
    window.set_reduce_motion(True)
    def reduced(origin):
        dialog = app.activeModalWidget()
        assert dialog._morph_overlay is None and not dialog._opening_pending
        assert dialog.windowOpacity() == 1
        results.append('Reduce motion opens immediately without an animated snapshot')
        dialog.accept()
    click_card(reduced)
    window.set_reduce_motion(False)
    def interrupted(origin):
        dialog = app.activeModalWidget()
        assert dialog._opening_pending
        dialog.editor.setFocus()
        QTest.keyClicks(dialog.editor, 'Typed immediately ')
        assert dialog._morph_overlay is None and not dialog._opening_pending
        assert 'Typed immediately ' in dialog.editor.toPlainText()
        results.append('Typing interrupts the transition and edits the live note immediately')
        dialog.accept()
    click_card(interrupted)
    def closing(origin):
        dialog = app.activeModalWidget()
        assert dialog._opening_pending
        if dialog._morph_overlay is None or dialog._morph_overlay.progress == 0:
            QTimer.singleShot(20, probe(lambda: closing(origin)))
            return
        presentation = QRect(dialog._morph_overlay.geometry()) if dialog._morph_overlay else None
        def closed():
            assert not dialog._closing_pending and dialog._closing_overlay is None
            assert dialog._backdrop is None and not dialog.isVisible()
            results.append('Closing during opening reverses from its current frame and cleans up')
        dialog.finished.connect(probe(closed))
        dialog.reject()
        assert dialog._morph_overlay is None
        if dialog._closing_overlay:
            assert dialog._closing_overlay.close_start == presentation, 'Close jumped to a different starting geometry'
        assert not dialog.sidecar.isVisible()
    click_card(closing)
    QTest.qWait(80)
    assert not errors, errors
    (ROOT / 'build' / 'note-motion-verification.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
finally:
    window.close()
    store.close()
