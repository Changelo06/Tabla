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
import json
import ctypes
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QGraphicsOpacityEffect
from PySide6.QtGui import QFont, QFontInfo, QFontDatabase, QPainter, QColor, QRawFont
from PySide6.QtTest import QTest
from tabla.theme import load_fonts
app = QApplication([])
app.setStyle('Fusion')
load_fonts()
font = QFont('Inter')
font.setPixelSize(13)
app.setFont(font)
report = {'qt': __import__('PySide6').__version__, 'samples': {}}
report['font_tables'] = {}
for family in ('Inter', 'Segoe UI'):
    raw = QRawFont.fromFont(QFont(family, 10))
    report['font_tables'][family] = {'resolved_family':raw.familyName(),
        'truetype_hinting_bytes': {tag:len(raw.fontTable(tag)) for tag in ('fpgm','prep','cvt ')},
        'variable_axes_bytes': len(raw.fontTable('fvar'))}
windows = []
class SampleWindow(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('white'))

modes = ('opaque', 'opacity_effect', 'translucent', 'segoe_14', 'inter_14')
for index, mode in enumerate(modes):
    window = SampleWindow()
    window.resize(620, 100)
    window.move(40, 80 + index * 140)
    if mode == 'translucent':
        window.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    window.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, mode != 'translucent')
    family = 'Segoe UI' if mode == 'segoe_14' else 'Inter'
    size = 14 if mode in ('segoe_14', 'inter_14') else 13
    window.setStyleSheet(f'QWidget {{background:transparent;color:black;font-family:"{family}";font-size:{size}px;}}')
    layout = QVBoxLayout(window)
    label = QLabel('Small text: The quick brown fox jumps over 0123456789. m il fl fi')
    label.setFixedHeight(40)
    layout.addWidget(label)
    if mode == 'opacity_effect':
        effect = QGraphicsOpacityEffect(label)
        effect.setOpacity(1.0)
        label.setGraphicsEffect(effect)
    window.show()
    windows.append(window)
QTest.qWait(300)
for window, mode in zip(windows, modes):
    label = window.findChild(QLabel)
    point = label.mapTo(window, QPoint())
    image = window.grab().toImage()
    ratio = image.devicePixelRatio()
    crop = image.copy(round(point.x()*ratio), round(point.y()*ratio), round(label.width()*ratio), round(label.height()*ratio))
    chromatic = gray = 0
    for y in range(crop.height()):
        for x in range(crop.width()):
            c = crop.pixelColor(x,y)
            if min(c.red(),c.green(),c.blue()) < 245:
                if max(c.red(),c.green(),c.blue())-min(c.red(),c.green(),c.blue()) > 4:
                    chromatic += 1
                elif 5 < c.red() < 245:
                    gray += 1
    info = QFontInfo(label.font())
    report['samples'][mode] = {'subpixel_color_pixels':chromatic, 'gray_edge_pixels':gray,
        'font':info.family(), 'pixel_size':info.pixelSize(), 'device_pixel_ratio':window.devicePixelRatioF()}
    crop.save(str(ROOT/'design'/'screenshots'/('text-render-'+mode+'.png')))
    window.close()
awareness = ctypes.c_int()
try:
    ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(awareness))
    report['process_dpi_awareness'] = awareness.value
except Exception:
    pass
try:
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Control Panel\Desktop')
    report['windows_font_smoothing'] = {name:winreg.QueryValueEx(key,name)[0] for name in ('FontSmoothing','FontSmoothingType')}
    winreg.CloseKey(key)
except OSError:
    pass
(ROOT/'build'/'text-rendering-diagnosis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
