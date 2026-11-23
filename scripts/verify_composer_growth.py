"""Native Windows QA for growing note capture; uses a disposable profile."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if '--child' not in sys.argv:
    env = dict(os.environ)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH'):
        env.pop(key, None)
    env['QT_QPA_PLATFORM'] = 'windows'
    env['PATH'] = r'C:\Windows\System32;C:\Windows'
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    subprocess.run([sys.executable, __file__, '--child'], cwd=ROOT, env=env, startupinfo=startup, check=True, timeout=30)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from tabla.theme import load_fonts
from tabla.storage import Store
from tabla.workspace import TablaWindow

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
store = Store(ROOT / 'build' / 'composer-growth-qa' / 'tabla.sqlite3')
window = TablaWindow(store)
window.resize(1200, 850)
window.show()
results = []
try:
    for appearance in ('Light', 'Dark'):
        window.set_appearance(appearance)
        window.navigate('Notes')
        QTest.qWait(100)
        capture = window.capture
        capture.title.setText('A little more room to write')
        text = ('I want my notes to stay readable as I write.\n\n'
                'The composer grows with each new paragraph, keeping the entire thought visible.\n\n'
                'Ideas, plans, meeting notes, and the details I want to remember can stay together.\n\n'
                'There is room for the next thought too.')
        capture.body.setPlainText(text)
        capture.body.moveCursor(QTextCursor.MoveOperation.End)
        QTest.qWait(220)
        assert capture.body.height() > 64
        assert capture.body.verticalScrollBar().maximum() == 0
        assert capture.body.cursorRect().bottom() < capture.body.viewport().height()
        assert capture.actions.y() > capture.body.geometry().bottom()
        capture.grab().save(str(ROOT / 'design' / 'screenshots' / ('composer-growing-' + appearance.lower() + '.png')))
        capture.body.setPlainText('AlongUnbrokenThought' * 60)
        QTest.qWait(120)
        wide = capture.body.height()
        window.resize(640, 480)
        QTest.qWait(200)
        assert window.capture is capture
        assert capture.body.height() > wide
        assert capture.body.verticalScrollBar().maximum() == capture.body.horizontalScrollBar().maximum() == 0
        results.append({'appearance': appearance, 'paragraph_growth': True, 'long_word_wrap': True, 'narrow_growth': True})
        capture.body.clear()
        capture.title.clear()
        window.resize(1200, 850)
        QTest.qWait(120)
    report = {'platform': app.platformName(), 'scenarios': results, 'full_text_visible': True, 'toolbar_below_text': True}
    (ROOT / 'build' / 'composer-growth-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
finally:
    window.timer.pause()
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    store.close()
