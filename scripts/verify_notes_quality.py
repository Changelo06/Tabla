"""Native Notes acceptance checks. Uses a disposable profile, never personal data."""
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
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env, startupinfo=startup, check=True, timeout=90)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication, QStyle
from PySide6.QtCore import Qt, QTimer, QPoint, QEvent, QCoreApplication
from PySide6.QtGui import QFont, QPainter, QPixmap, QHelpEvent
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.theme import load_fonts
from tabla.note_dialog import NoteDialog

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
app.setFont(QFont('Inter', 10))
errors = []
def error_hook(kind, value, tb):
    import traceback
    traceback.print_exception(kind, value, tb)
    errors.append(str(value))
sys.excepthook = error_hook
shots = ROOT / 'design' / 'screenshots'
shots.mkdir(exist_ok=True)

with tempfile.TemporaryDirectory(prefix='tabla-notes-quality-') as profile:
    store = Store(Path(profile) / 'tabla.sqlite3')
    examples = [
        ('Ideas for the next chapter', 'Make room for the work that matters.\n\nA private space to collect references, shape an idea and decide what comes next.\n\nWriting should feel immediate. Tools should stay within reach.\n\nStart small, then connect the pieces.', 'gray', True),
        ('A little reminder', 'One thing at a time.', 'blue', True),
        ('Website launch', 'Before publishing\n\n- [ ] Review the opening message\n- [ ] Check the mobile layout\n- [ ] Choose three featured projects\n\nKeep the first impression clear.\n\nUse the project brief as a guide.', 'yellow', True),
        ('Reading list', 'Designing for attention\n\nThe small details make a familiar tool comfortable to use.\n\nResponse\nPredictability\nGood defaults\n\nA quiet interface leaves space for thought.', 'violet', False),
        ('Weekend plans', '- [ ] Visit the market\n- [ ] Take a long walk\n- [x] Finish the book', 'gray', False),
        ('Field notes', '\n\n'.join(['A few observations from today. Good ideas rarely arrive fully formed. Keep the useful details and come back to them.'] * 8), 'green', False),
        ('Something to remember', 'Less friction. More room to think.', 'rose', False),
    ]
    records = [store.save(dict(kind='note', title=t, body=b, color=c, pinned=p)) for t,b,c,p in examples]
    window = TablaWindow(store)
    window.resize(1500, 900)
    window.show()
    window.navigate('Notes')
    QTest.qWait(400)
    for appearance in ('Light', 'Dark'):
        print('Checking', appearance, flush=True)
        window.set_appearance(appearance)
        QTest.qWait(300)
        window.grab().save(str(shots / ('notes-quality-gallery-' + appearance.lower() + '.png')))
        capture = window.capture
        capture.title.setText('A longer thought, without losing the tools')
        capture.body.setPlainText('\n\n'.join(['Keep writing comfortably. The toolbar stays below this bounded editor, while the text scrolls inside it.'] * 35))
        capture.body.setFocus()
        capture.body.moveCursor(__import__('PySide6.QtGui', fromlist=['QTextCursor']).QTextCursor.MoveOperation.End)
        QTest.qWait(450)
        assert capture.body.verticalScrollBar().maximum() > 0
        assert capture.body.height() <= 360
        viewport = window.notes_scroll.viewport()
        bottom = capture.actions.mapTo(viewport, capture.actions.rect().bottomLeft()).y()
        assert bottom < viewport.height(), (bottom, viewport.height())
        window.grab().save(str(shots / ('notes-quality-capture-' + appearance.lower() + '.png')))
        capture.body.clear()
        capture.title.clear()
        capture.commit()
        QTest.qWait(200)
    window.resize(640, 480)
    print('Checking compact', flush=True)
    QTest.qWait(300)
    capture = window.capture
    capture.body.setPlainText('Long compact writing.\n' * 100)
    capture.body.setFocus()
    QTest.qWait(350)
    assert capture.body.height() <= 150
    assert capture.body.horizontalScrollBar().maximum() == 0
    window.grab().save(str(shots / 'notes-quality-compact.png'))
    capture.body.clear()
    capture.commit()
    window.resize(1500, 900)
    QTest.qWait(300)
    card = window._gallery_cards[records[0]['id']]
    print('Checking tooltip', flush=True)
    window.notes_scroll.ensureWidgetVisible(card)
    window.raise_()
    window.activateWindow()
    QTest.qWait(180)
    card.setFocus()
    assert card._quiet_pin.style().styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay, None, card._quiet_pin) == 380
    # Synthetic mouse moves cannot establish real hover timing when another
    # desktop app owns foreground activation; exercise delivery separately.
    event = QHelpEvent(QEvent.Type.ToolTip, QPoint(12, 12), card._quiet_pin.mapToGlobal(QPoint(12, 12)))
    app.sendEvent(card._quiet_pin, event)
    QTest.qWait(140)
    assert app._tabla_polish.tooltip.isVisible()
    assert app._tabla_polish.tooltip.label.text() == 'Unpin'
    app._tabla_polish.tooltip.hide()
    print('PASS long capture, both themes, compact width, 380ms tooltip policy', flush=True)
    dialog_errors = []
    def inspect_note():
        dialog = app.activeModalWidget()
        try:
            assert isinstance(dialog, NoteDialog)
            QTest.qWait(240)
            image = QPixmap(window.size())
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.drawPixmap(0, 0, window.grab())
            for surface in (dialog, dialog.sidecar):
                if surface.isVisible():
                    painter.drawPixmap(window.mapFromGlobal(surface.pos()), surface.grab())
            painter.end()
            image.save(str(shots / 'notes-quality-editor-dark.png'))
            dialog.editor.appendPlainText('A saved addition.')
            dialog.accept()
        except Exception as exc:
            dialog_errors.append(str(exc))
            if dialog:
                dialog.reject()
    capture = window.capture
    scroll = window.notes_scroll
    QTimer.singleShot(70, inspect_note)
    window.open_note_card(records[0], card)
    QTest.qWait(200)
    assert not dialog_errors, dialog_errors
    assert window.capture is capture and window.notes_scroll is scroll
    assert 'A saved addition.' in store.get(records[0]['id'])['body']
    assert not errors, errors
    print('PASS opening/closing, persisted edit, retained gallery and capture', flush=True)
    window.timer.pause()
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    store.close()
print('Native Notes quality checks passed.', flush=True)
