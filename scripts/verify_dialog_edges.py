"""Check translucent rounded popup edges using isolated native Windows Qt."""
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
from PySide6.QtCore import QEvent
from PySide6.QtGui import QPixmap, QPainter, QColor
from PySide6.QtTest import QTest
from tabla.theme import load_fonts
from tabla.storage import Store
from tabla.workspace import TablaWindow
from tabla.dialogs import ItemDialog, NoteDialog

app = QApplication([])
app.setStyle('Fusion')
load_fonts()
profile = ROOT / 'build' / 'dialog-edges-qa'
store = Store(profile / 'tabla.sqlite3')
store.set_setting('reduce_motion', False)
window = TablaWindow(store)
window.show()
verified = []
try:
    for appearance in ('Light', 'Dark'):
        window.set_appearance(appearance)
        for kind in ('project', 'task', 'note'):
            dialog = NoteDialog(store, parent=window) if kind == 'note' else ItemDialog(store, kind, parent=window)
            try:
                dialog.show()
                QTest.qWait(200)
                image = dialog.grab().toImage()
                assert dialog.graphicsEffect() is None, 'Dialog still uses an offscreen opacity effect'
                for x, y in ((0, 0), (image.width()-1, 0), (0, image.height()-1), (image.width()-1, image.height()-1)):
                    assert image.pixelColor(x, y).alpha() == 0, (appearance, kind, x, y, image.pixelColor(x, y).getRgb())
                assert image.pixelColor(image.width()//2, image.height()//2).alpha() == 255
                canvas = QPixmap(image.size())
                canvas.setDevicePixelRatio(image.devicePixelRatio())
                canvas.fill(QColor('#ffffff' if appearance == 'Light' else '#292a2d'))
                painter = QPainter(canvas)
                painter.drawImage(0, 0, image)
                painter.end()
                canvas.save(str(ROOT / 'design' / 'screenshots' / f'{kind}-edges-{appearance.lower()}.png'))
                verified.append(kind + '/' + appearance.lower())
            finally:
                dialog.close()
                QTest.qWait(180)
                dialog.deleteLater()
    report = {'platform': app.platformName(), 'transparent_corners': verified, 'opaque_content': True, 'no_widget_opacity_effect': True}
    (ROOT / 'build' / 'dialog-edges-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
finally:
    window.timer.pause()
    window.close()
    window.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    store.close()
