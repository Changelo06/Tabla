"""Exercise actual Windows Qt motion/chrome without touching the real profile."""
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
    subprocess.run([sys.executable, '-X', 'faulthandler', __file__, '--child'], cwd=ROOT,
                   env=env, startupinfo=startup, check=True, timeout=35)
    raise SystemExit(0)

sys.path.insert(0, str(ROOT))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QEvent, QPoint
from PySide6.QtGui import QHelpEvent
from PySide6.QtTest import QTest
from tabla.theme import load_fonts
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.polish import motion_enabled

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
profile = ROOT / 'build' / 'native-polish-qa'
profile.mkdir(parents=True, exist_ok=True)
store = Store(profile / 'tabla.sqlite3')
if not store.records(state='all'):
    store.seed_demo()
store.set_setting('reduce_motion', False)
store.set_setting('sidebar_hidden', False)
window = TablaWindow(store)
def qa_exception(kind, value, traceback):
    window.timer.pause()
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    store.close()
    sys.__excepthook__(kind, value, traceback)
sys.excepthook = qa_exception
window.resize(1250, 850)
window.show()
QTest.qWait(200)
window.navigate('Notes')
QTest.qWait(180)
assert motion_enabled()
capture = window.capture
start = capture.height()
capture.expand()
assert hasattr(capture, '_height_motion')
QTest.qWait(240)
assert capture.height() == 166
window.activateWindow()
window.raise_()
QTest.qWait(120)
capture.body.setPlainText('Unfinished note while arranging windows')
capture.body.setFocus()
QTest.qWait(80)
assert capture.body.hasFocus(), 'Writer could not receive keyboard focus'
window.resize(640, 480)
QTest.qWait(180)
assert window.capture is capture and capture.body.hasFocus(), 'Resizing lost writer focus'
assert capture.body.toPlainText() == 'Unfinished note while arranging windows'
capture.body.clear()
window.chrome.maximize.click()
QTest.qWait(100)
assert window.isMaximized()
assert window.frameGeometry().bottom() <= window.screen().availableGeometry().bottom(), 'Maximized window covers the taskbar'
window.chrome.maximize.click()
QTest.qWait(100)
assert not window.isMaximized()
target = window.nav_buttons['Notes']
QTest.mouseMove(target, QPoint(10, 10))
QTest.qWait(160)
event = QHelpEvent(QEvent.Type.ToolTip, QPoint(12, 12), target.mapToGlobal(QPoint(12, 12)))
app.sendEvent(target, event)
QTest.qWait(180)
tooltip = app._tabla_polish.tooltip
assert tooltip.isVisible()
tooltip.grab().save(str(ROOT / 'design' / 'screenshots' / 'polished-tooltip.png'))
tooltip.hide()
window.set_reduce_motion(True)
assert app.property('reduceMotion')
import ctypes
native_style = ctypes.windll.user32.GetWindowLongW(int(window.winId()), -16)
assert native_style & 0x00040000, 'Window lacks native resizing style'
from ctypes import wintypes
send = ctypes.windll.user32.SendMessageW
send.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
button_point = window.chrome.maximize.mapTo(window, window.chrome.maximize.rect().center())
client_point = wintypes.POINT(round(button_point.x() * window.devicePixelRatioF()), round(button_point.y() * window.devicePixelRatioF()))
ctypes.windll.user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
ctypes.windll.user32.ClientToScreen(int(window.winId()), ctypes.byref(client_point))
position = (client_point.y & 0xffff) << 16 | (client_point.x & 0xffff)
assert send(int(window.winId()), 0x84, 0, position) == 9, 'Maximize does not expose native Snap hit target'
from PySide6.QtGui import QCursor
from unittest.mock import patch
# Control only the app's cursor query, without moving the user's real pointer.
with patch('tabla.chrome.QCursor.pos', return_value=window.chrome.maximize.mapToGlobal(window.chrome.maximize.rect().center())):
    send(int(window.winId()), 0xA0, 9, position)
    QTest.qWait(1200)
    assert window.chrome.maximize.property('nativeHover'), 'Native maximize hover did not remain visible'
    hover_image = window.chrome.maximize.grab()
    hover_image.save(str(ROOT / 'design' / 'screenshots' / 'maximize-hover.png'))
    maximize_hover_color = hover_image.toImage().pixelColor(5, hover_image.height() // 2).name()
with patch('tabla.chrome.QCursor.pos', return_value=window.chrome.drag_area.mapToGlobal(window.chrome.drag_area.rect().center())):
    send(int(window.winId()), 0x2A2, 0, 0)
assert not window.chrome.maximize.property('nativeHover'), 'Hover stuck after leaving'
from tabla.theme import themed_color
# Minimize and native maximize share the same stylesheet background token.
assert maximize_hover_color == themed_color('#eaeae7'), maximize_hover_color
send(int(window.winId()), 0xA2, 9, position)
QTest.qWait(100)
assert window.isMaximized()
send(int(window.winId()), 0xA2, 9, position)
QTest.qWait(100)
assert not window.isMaximized()
window.set_reduce_motion(False)
anchor = window.chrome.back
hint = QHelpEvent(QEvent.Type.ToolTip, QPoint(12, 12), anchor.mapToGlobal(QPoint(12, 12)))
app.sendEvent(anchor, hint)
QTest.qWait(160)
tooltip = app._tabla_polish.tooltip
assert tooltip.isVisible() and tooltip.graphicsEffect() is None
geometry = tooltip.geometry()
animation = tooltip._fade
app.sendEvent(anchor, QHelpEvent(QEvent.Type.ToolTip, QPoint(12, 12), anchor.mapToGlobal(QPoint(12, 12))))
assert tooltip._fade is animation, 'Repeated tooltip event restarted the transition'
app.sendEvent(window.chrome.forward, QEvent(QEvent.Type.Leave))
assert tooltip.isVisible(), 'An unrelated control hid the tooltip'
QTest.qWait(1200)
assert tooltip.isVisible() and tooltip.geometry() == geometry, 'Long hover moved or hid the tooltip'
tooltip.grab().save(str(ROOT / 'design' / 'screenshots' / 'header-tooltip.png'))
app.sendEvent(anchor, QEvent(QEvent.Type.Leave))
assert not tooltip.isVisible()
window.set_reduce_motion(True)
sizes = []
for width, height in ((960, 520), (640, 480), (500, 400), (1280, 720)):
    window.resize(width, height)
    for page in ('Calendar', 'Notes', 'My Tasks', 'Focus'):
        window.navigate(page)
        QTest.qWait(120)
        assert window.width() == width and window.height() == height, (page, width, height, window.size())
        QTest.mouseMove(window.chrome, QPoint(5, 15))
        if width == 640:
            window.grab().save(str(ROOT / 'design' / 'screenshots' / ('compact-' + page.lower().replace(' ', '-') + '.png')))
    sizes.append([width, height])
window.close()
app.processEvents()
store.close()
report = {'platform': app.platformName(), 'composer_start_height': start, 'composer_end_height': 166,
          'native_animation': True, 'maximize_restore': True, 'rounded_tooltip': True, 'reduce_motion': True}
report['verified_window_sizes'] = sizes
report['native_window_style'] = hex(native_style & 0xffffffff)
report['native_snap_hit_target'] = True
report['resize_preserves_writer_focus'] = True
report['native_maximize_hover_and_leave'] = True
report['stable_long_hover_tooltip'] = True
report['caption_hover_background_matches'] = maximize_hover_color
(ROOT / 'build' / 'native-polish-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
