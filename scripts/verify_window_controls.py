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
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint, QCoreApplication, QEvent
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.theme import load_fonts

app=QApplication([])
app.setStyle('Fusion')
load_fonts()
app.setFont(QFont('Inter',10))
with tempfile.TemporaryDirectory(prefix='tabla-chrome-') as folder:
    store=Store(Path(folder)/'tabla.sqlite3')
    window=TablaWindow(store)
    window.resize(1100,760)
    window.show()
    QTest.qWait(350)
    for theme in ('Light','Dark'):
        window.set_appearance(theme)
        QTest.qWait(300)
        for control in (window.chrome.maximize,window.chrome.minimize,window.chrome.close_button):
            assert (control.width(),control.height())==(48,43)
        header=window.chrome
        assert header.minimize.x()<header.maximize.x()<header.close_button.x()
        header.grab().copy(round((header.width()-190)*header.devicePixelRatioF()),0,round(190*header.devicePixelRatioF()),round(43*header.devicePixelRatioF())).save(str(ROOT/'design'/'screenshots'/('window-circles-'+theme.lower()+'.png')))
    # Click outside the painted circle, inside the wider rectangular slot.
    QTest.mouseClick(window.chrome.maximize,Qt.MouseButton.LeftButton,pos=QPoint(4,12))
    QTest.qWait(200)
    assert window.isMaximized()
    QTest.mouseClick(window.chrome.maximize,Qt.MouseButton.LeftButton,pos=QPoint(44,30))
    QTest.qWait(200)
    assert not window.isMaximized()
    QTest.mouseClick(window.chrome.minimize,Qt.MouseButton.LeftButton,pos=QPoint(4,12))
    QTest.qWait(150)
    assert window.isMinimized()
    window.showNormal()
    QTest.qWait(200)
    import ctypes
    from ctypes import wintypes
    api=ctypes.windll.user32
    api.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    api.SendMessageW.restype=wintypes.LPARAM
    hwnd=int(window.winId())
    for control,expected in ((window.chrome.maximize,9),(window.chrome.minimize,1),(window.chrome.close_button,1)):
        local=control.mapTo(window,QPoint(4,12))
        ratio=window.devicePixelRatioF()
        point=wintypes.POINT(round(local.x()*ratio),round(local.y()*ratio))
        api.ClientToScreen(hwnd,ctypes.byref(point))
        position=(point.x&65535)|((point.y&65535)<<16)
        assert api.SendMessageW(hwnd,0x84,0,position)==expected
    window.timer.pause()
    QTest.mouseClick(window.chrome.close_button,Qt.MouseButton.LeftButton,pos=QPoint(44,30))
    QTest.qWait(100)
    assert not window.isVisible()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    app.processEvents()
    store.close()
print('PASS colored circles in both themes, 48x43 targets, edge clicks, minimize/maximize/restore/close, native Snap hit testing',flush=True)
