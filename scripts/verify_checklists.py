"""Real Windows checklist interaction and visual checks; isolated temporary data."""
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
    env['QT_QPA_PLATFORM'] = 'windows'
    env['PYTHONFAULTHANDLER'] = '1'
    env['PYTHONUNBUFFERED'] = '1'
    env['PATH'] = r'C:\Windows\System32;C:\Windows'
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env,
                   startupinfo=startup, check=True, timeout=50)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QCoreApplication, QEvent, QPointF
from PySide6.QtGui import QTextCursor, QMouseEvent
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.dialogs import NoteDialog
from tabla.theme import load_fonts

app = QApplication([])
app.setStyle('Fusion')
app.setProperty('reduceMotion', True)
load_fonts()
with tempfile.TemporaryDirectory(dir=ROOT / 'build') as folder:
    store = Store(Path(folder) / 'tabla.sqlite3')
    note = store.save({'kind': 'note', 'title': 'A clearer checklist', 'body':
        'A little room for notes, then a few things to do.\n\n'
        '- [ ] **Review the project brief**\n'
        '- [x] Capture the first idea\n'
        '- [ ] A longer item that wraps naturally onto the next line while its checkbox and drag handle stay aligned with the start of the text.\n\n'
        'Keep the rest of the note right here.'})
    window = TablaWindow(store)
    window.resize(1450, 900)
    window.show()
    QTest.qWait(400)
    for appearance in ('Light', 'Dark'):
        window.set_appearance(appearance)
        QTest.qWait(250)
        dialog = NoteDialog(store, store.get(note['id']), parent=window)
        dialog.show()
        QTest.qWait(120)
        editor = dialog.editor
        hits = lambda action: [(p, r) for a, p, r in editor._check_hits if a == action]
        assert len(hits('toggle')) == 3
        position, rect = hits('toggle')[0]
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
        assert editor.document().findBlock(position).blockFormat().marker().value == 2
        QTest.qWait(40)
        start, target = hits('drag')[0], hits('drag')[2]
        QTest.mousePress(editor.viewport(), Qt.MouseButton.LeftButton, pos=start[1].center().toPoint())
        QTest.mouseMove(editor.viewport(), target[1].center().toPoint())
        QTest.mouseRelease(editor.viewport(), Qt.MouseButton.LeftButton, pos=target[1].center().toPoint())
        QTest.qWait(40)
        assert editor.plain_body().index('Capture the first idea') < editor.plain_body().index('Review the project brief')
        position, rect = hits('add')[0]
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
        editor.insertPlainText('One more small step')
        QTest.qWait(40)
        assert len(hits('toggle')) == 4
        position, rect = hits('remove')[-1]
        QTest.mouseMove(editor.viewport(), rect.center().toPoint())
        # QTest's native pointer move can be coalesced when the desktop is unfocused.
        app.sendEvent(editor.viewport(), QMouseEvent(QEvent.Type.MouseMove, QPointF(rect.center()),
            QPointF(editor.viewport().mapToGlobal(rect.center().toPoint())),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
        QTest.qWait(30)
        assert editor._check_hover == position, (editor._check_hover, position)
        dialog.grab().save(str(ROOT / 'design' / 'screenshots' / f'checklist-{appearance.lower()}.png'))
        QTest.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
        assert 'One more small step' not in editor.plain_body()
        assert 'Keep the rest of the note right here.' in editor.plain_body()
        assert dialog.save()
        snapshot = editor.snapshot()
        dialog.close()
        app.processEvents()
        reopened = NoteDialog(store, store.get(note['id']), parent=window)
        assert reopened.editor.snapshot() == snapshot
        reopened.close()
        QTest.qWait(100)
        reopened.deleteLater()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        # Reset the sample between themes.
        store.save(note)
        print(appearance, 'checkbox, drag, add, remove, formatting and reopen passed')
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    store.close()
