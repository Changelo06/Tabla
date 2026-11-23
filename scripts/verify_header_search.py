"""Native Windows header search and caption hit-testing with sample data."""
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
import ctypes
from ctypes import wintypes
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import QEvent, Qt, QPoint
from PySide6.QtTest import QTest
from tabla.theme import load_fonts
from tabla.storage import Store
from tabla.workspace import TablaWindow

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
store = Store(ROOT / 'build' / 'header-search-qa' / 'tabla.sqlite3')
if not store.records(state='all'):
    store.seed_demo()
window = TablaWindow(store)
window.resize(1400, 850)
window.show()
results = []
try:
    send = ctypes.windll.user32.SendMessageW
    send.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    ctypes.windll.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    def hit(widget, point):
        local = widget.mapTo(window, point)
        native = wintypes.POINT(round(local.x() * window.devicePixelRatioF()), round(local.y() * window.devicePixelRatioF()))
        ctypes.windll.user32.ClientToScreen(int(window.winId()), ctypes.byref(native))
        position = (native.y & 0xffff) << 16 | (native.x & 0xffff)
        return send(int(window.winId()), 0x84, 0, position)
    for appearance in ('Light', 'Dark'):
        window.set_appearance(appearance)
        window.navigate('Notes')
        window.focus_search()
        window.chrome.search.setText('Website')
        QTest.keyClick(window.chrome.search, Qt.Key.Key_Return)
        QTest.qWait(150)
        assert window.page == 'Search' and window.search_query == 'Website'
        assert any(b.text() == 'Website ideas' for b in window.workspace.findChildren(QPushButton))
        assert hit(window.chrome.search, window.chrome.search.rect().center()) == 1
        assert hit(window.chrome.drag_area, QPoint(3, window.chrome.height()//2)) == 2
        assert hit(window.chrome.maximize, window.chrome.maximize.rect().center()) == 9
        window.chrome.grab().save(str(ROOT / 'design' / 'screenshots' / ('header-search-' + appearance.lower() + '.png')))
        results.append(appearance)
    window.resize(500, 400)
    QTest.qWait(160)
    assert window.chrome.search.isVisible() and window.chrome.search.width() >= 80
    window.chrome.grab().save(str(ROOT / 'design' / 'screenshots' / 'header-search-compact.png'))
    report = {'platform': app.platformName(), 'search_themes': results, 'native_search_client_hit': True,
              'caption_drag_and_snap_retained': True, 'compact_width': window.chrome.search.width()}
    (ROOT / 'build' / 'header-search-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
finally:
    window.timer.pause()
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    store.close()
