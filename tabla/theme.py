from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from pathlib import Path
import sys
from functools import lru_cache


def load_fonts():
    from PySide6.QtGui import QFontDatabase
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for name in ("Inter.ttf",):
        if QFontDatabase.addApplicationFont(str(root / "assets" / "fonts" / name)) < 0:
            raise RuntimeError(f"Could not load bundled font: {name}")

COLORS = {
    "blue": ("#eef6ff", "#1878f8"), "green": ("#eff9ee", "#42a957"),
    "yellow": ("#fffbe6", "#c69a14"), "violet": ("#f4efff", "#8961cf"),
    "rose": ("#fff0f4", "#d65b83"), "gray": ("#f8f8f6", "#75716c"),
}
PATHS = {
    "image": '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
    "bullets": '<circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/><path d="M9 6h12M9 12h12M9 18h12"/>',
    "brand": '<path d="M4 3h10a5 5 0 0 1 0 10H9m11 8H10a5 5 0 0 1 0-10h5" stroke-width="5"/>',
    "home": '<path d="m3 10 9-7 9 7v10H5V10m4 10v-7h6v7"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v5m10-5v5M3 11h18m-13 4h1m3 0h1m3 0h1M8 18h1m3 0h1"/>',
    "tasks": '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="m8 11 3 3 5-6"/>',
    "note": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zm0 0v6h6M8 13h8m-8 4h6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "settings": '<path d="m9 3-1 3-3 1-2 3 2 3v4l4 1 3 3 3-3 4-1v-4l2-3-2-3-3-1-1-3z"/><circle cx="12" cy="12" r="3"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "left": '<path d="m14 5-7 7 7 7"/>',
    "right": '<path d="m10 5 7 7-7 7"/>',
    "link": '<path d="m10 14 4-4m-6 7-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m4 0 1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0"/>',
    "archive": '<path d="M4 9v11h16V9M3 4h18v5H3zM9 13h6"/>',
    "trash": '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
    "play": '<path d="m9 5 10 7-10 7z"/>',
    "pause": '<path d="M9 5v14M15 5v14"/>',
    "pin": '<path d="m8 3 8 0-1 7 4 4H5l4-4zM12 14v7"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18h2a2 2 0 0 0 0-4h-1a2 2 0 0 1 0-4h3a5 5 0 0 0 5-5c0-3-5-5-9-5z"/><circle cx="7" cy="10" r=".7"/><circle cx="10" cy="6.5" r=".7"/><circle cx="15" cy="7" r=".7"/><circle cx="6.5" cy="15" r=".7"/>',
    "undo": '<path d="M9 5 4 10l5 5M4 10h10a6 6 0 0 1 0 12"/>',
    "redo": '<path d="m15 5 5 5-5 5m5-5H10a6 6 0 0 0 0 12"/>',
    "more": '<circle cx="12" cy="5" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="12" cy="19" r="1.3"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/>',
    "minimize": '<path d="M5 12h14"/>',
    "maximize": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "restore": '<rect x="4" y="8" width="12" height="12" rx="2"/><path d="M8 8V4h12v12h-4"/>',
    "close": '<path d="m6 6 12 12M6 18 18 6"/>',
    "attachment": '<path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2m-7 13 9-9"/>',
    "export": '<path d="M12 15V3m-4 4 4-4 4 4M4 14v6h16v-6"/>',
    "import": '<path d="M12 3v12m-4-4 4 4 4-4M4 16v5h16v-5"/>',
    "check": '<path d="m5 12 5 5 9-10"/>',
    "board": '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="10" y="4" width="5" height="12" rx="1"/><rect x="17" y="4" width="4" height="8" rx="1"/>',
}


def icon(name, color="#56647a", size=22, preserve_color=False):
    from PySide6.QtWidgets import QApplication
    if not preserve_color and QApplication.instance() and QApplication.instance().property('tablaDark') and color not in ('#ffffff', '#2383e2', '#1878f8'):
        color = '#bdc1c6'
    path = PATHS['pin'].replace('<path ', f'<path fill="{color}" ') if name == 'pin-filled' else PATHS.get(name, PATHS['note'])
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


@lru_cache(maxsize=48)
def navigation_icon(name, active=False, dark=False):
    """A quiet outline rail; its selected glyph has a small cached bloom."""
    from .layer_effects import blurred_pixmap
    size = 21
    color = ('#ffffff' if dark else '#303332') if active else ('#969b9f' if dark else '#787774')
    canvas = QPixmap(size * 2, size * 2)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    if active and name == 'home':
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
               f'<path fill="{color}" d="M3 10 12 3 21 10v2h-2v9h-5v-7h-4v7H5v-9H3z"/></svg>')
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
    else:
        icon(name, color, size * 2, preserve_color=True).paint(painter, 0, 0, size * 2, size * 2)
    painter.end()
    canvas.setDevicePixelRatio(2)
    if active and dark:
        halo = blurred_pixmap(canvas, 1.8)
        result = QPixmap(canvas.size())
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setOpacity(.26)
        painter.drawPixmap(0, 0, size * 2, size * 2, halo)
        painter.setOpacity(1)
        painter.drawPixmap(0, 0, size * 2, size * 2, canvas)
        painter.end()
        result.setDevicePixelRatio(2)
        canvas = result
    return QIcon(canvas)


def application_icon():
    """The sidebar's charcoal Tabla mark on a legible, neutral launcher tile."""
    from PySide6.QtCore import QRectF
    result = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#f7f7f5'))
        painter.drawRoundedRect(QRectF(0, 0, size, size), size * .22, size * .22)
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
               'fill="none" stroke="#37352f" stroke-linecap="round" stroke-linejoin="round">'
               + PATHS['brand'] + '</svg>')
        QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(size * .18, size * .18, size * .64, size * .64))
        painter.end()
        result.addPixmap(pixmap)
    return result


STYLE = """
QWidget { font-family: 'Alegreya Sans'; font-size: 16px; color: #242321; }
QMainWindow, QWidget#appRoot { background: #f6f5f4; }
QWidget#sidebar { background: transparent; }
QFrame#workspace { background: #ffffff; border: 1px solid #e8e6e2; border-radius: 12px; }
QFrame#card { background: #ffffff; border: 1px solid #e8e6e2; border-radius: 12px; }
QFrame#smallCard { background: #fafaf9; border: 1px solid #e8e6e2; border-radius: 8px; }
QLabel { background: transparent; }
QLabel#title { font-size: 38px; font-weight: 900; color: #242321; }
QLabel#section { font-size: 21px; font-weight: 900; color: #242321; }
QLabel#subtitle { font-family: 'Alegreya'; font-size: 19px; color: #615d59; }
QLabel#muted { font-size: 15px; color: #69645f; }
QLabel#reading { font-family: 'Alegreya'; font-size: 19px; color: #494641; }
QPushButton { background: white; border: 1px solid #d9d6d1; border-radius: 8px;
 padding: 7px 12px; min-height: 22px; font-weight: 500; }
QPushButton:hover { background: #f2f7ff; border-color: #bbd4f6; }
QPushButton:pressed { background: #e5efff; }
QPushButton:focus, QToolButton:focus { border: 2px solid #3388ff; }
QPushButton:disabled { color: #a3adbb; background: #f5f7fa; border-color: #edf0f5; }
QPushButton#primary { background: #006bc7; color: white; border-color: #006bc7; }
QPushButton#primary:hover { background: #005bad; }
QPushButton#danger { color: #b63b50; }
QPushButton#nav { background: transparent; border: none; text-align: left; padding: 9px 12px; border-radius: 8px; }
QPushButton#nav:hover { background: #eeece9; }
QPushButton#nav[active="true"] { background: #e6f3fe; color: #005ea9; font-weight: 500; }
QPushButton#tab { background: transparent; border: none; padding: 7px 12px; }
QPushButton#tab[active="true"] { background: white; color: #0065b9; border: 1px solid #d9d6d1; }
QPushButton#text { border: none; background: transparent; color: #0065b9; text-align: left; padding: 5px 0; }
QPushButton#icon { padding: 6px; min-width: 21px; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {
 background: #ffffff; border: 1px solid #d9d6d1; border-radius: 8px; padding: 8px; selection-background-color: #d6e9ff; placeholder-text-color: #69645f; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #2780ef; }
QPlainTextEdit#noteEditor { font-family: 'Alegreya'; border: none; background: white; font-size: 20px; padding: 12px; }
QTextBrowser { font-family: 'Alegreya'; background: white; border: none; font-size: 20px; padding: 12px; }
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 23px; }
QComboBox { padding-right: 26px; }
QComboBox::down-arrow, QDateEdit::down-arrow { image: url(__DOWN_ICON__); width: 13px; height: 13px; }
QComboBox QAbstractItemView { background: white; color: #242321; selection-background-color: #e6f1ff; }
QCheckBox { spacing: 9px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #aaa49b; border-radius: 5px; background: white; }
QCheckBox::indicator:checked { background: #006bc7; border-color: #006bc7; image: url(__CHECK_ICON__); }
QCheckBox::indicator:focus { border: 2px solid #1878f8; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #d6d2cc; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QDialog { background: #ffffff; }
QDialogButtonBox { background: transparent; }
QStatusBar { background: #f6f5f4; color: #69645f; font-size: 14px; }
QToolTip { background: #202a3a; color: white; border: none; padding: 6px; }
QMenu { background: white; border: 1px solid #dce3ed; padding: 5px; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #e8f2ff; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 9px 18px; background: #f6f5f4; border: none; }
QTabBar::tab:selected { background: #e6f3fe; color: #0065b9; }
"""
_assets = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets"
STYLE = STYLE.replace("__CHECK_ICON__", (_assets / "check-white.svg").as_posix()).replace("__DOWN_ICON__", (_assets / "chevron-down.svg").as_posix())

# The native product shell follows the supplied Notion and Keep references.
STYLE += """
QWidget { font-family: 'Inter'; font-size: 13px; color: #37352f; }
QMainWindow, QWidget#appRoot, QFrame#workspace { background: white; border: none; border-radius: 0; }
QWidget#sidebar { background: #f7f7f5; border-right: 1px solid #e9e9e7; }
QFrame#card, QFrame#smallCard { border-radius: 6px; border: 1px solid #e9e9e7; background: white; }
QLabel#title { font-family: 'Inter'; font-size: 32px; font-weight: 700; color: #37352f; }
QLabel#section { font-size: 16px; font-weight: 600; }
QLabel#subtitle, QLabel#muted { font-family: 'Inter'; font-size: 12px; color: #73726d; }
QLabel#reading { font-family: 'Inter'; font-size: 14px; color: #37352f; }
QPushButton { font-weight: 400; border-radius: 4px; padding: 5px 9px; min-height: 22px; border-color: #e4e4e1; }
QPushButton#nav { padding: 5px 10px; border-radius: 4px; min-height: 22px; color: #5f5e5b; }
QPushButton#nav[active="true"] { background: #eaeae7; color: #252522; font-weight: 500; }
QPushButton#nav:hover { background: #efefec; }
QPushButton#tab { padding: 5px 10px; border-radius: 4px; color: #787774; }
QPushButton#tab[active="true"] { color: #37352f; background: #eeeeec; border: none; font-weight: 600; }
QPushButton#text { color: #696864; }
QPushButton#primary { background: #1473ce; border-color: #1473ce; font-weight: 500; }
QPushButton#primary:hover { background: #0c64b8; }
QLineEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox { padding: 6px 8px; border-radius: 4px; font-size: 13px; }
QComboBox { padding-right: 26px; }
QPlainTextEdit#noteEditor, QTextBrowser { font-family: 'Inter'; font-size: 15px; padding: 12px; }
QLabel#composer { font-size: 14px; color: #666666; }
QFrame#composerBox { background: white; border: 1px solid #dadce0; border-radius: 8px; }
QFrame#calendarCell { border: none; border-right: 1px solid #e5e5e3; border-bottom: 1px solid #e5e5e3; background: white; }
QTableWidget { border: none; gridline-color: #ececea; background: white; selection-background-color: #edf4fc; selection-color: #37352f; }
QTableWidget::item { padding: 7px; border: none; }
QLineEdit, QPlainTextEdit { selection-background-color: #cce3fb; selection-color: #1b3856; }
QDateEdit:disabled { background: #f1f1ef; color: #8b8b85; border-color: #eeeeec; }
QHeaderView::section { background: white; color: #787774; border: none; border-bottom: 1px solid #e5e5e3; padding: 9px; font-size: 12px; }
QDialog { background: white; }
QTabBar::tab { font-size: 12px; padding: 6px 12px; }
QStatusBar { background: white; font-size: 11px; }
QFrame#titleBar { background:#f7f7f5;border-bottom:1px solid #e5e5e3; }
QLineEdit#titleSearch {background:white;border:1px solid #deded9;border-radius:6px;padding:2px 5px;font-size:12px;}
QLineEdit#titleSearch:hover {border-color:#aaa9a3;}
QLineEdit#titleSearch:focus {border-color:#2383e2;}
QPushButton#chromeButton, QToolButton#menuButton { background:transparent;border:none;border-radius:5px;padding:4px 9px;font-size:12px;color:#696864; }
QPushButton#chromeButton:hover, QPushButton#chromeButton[nativeHover="true"], QToolButton#menuButton:hover { background:#eaeae7; }
QPushButton#chromeButton:pressed { background:#deded9; }
QToolButton#menuButton::menu-indicator { image:none; }
QPushButton#windowClose {background:transparent;border:none;border-radius:5px;padding:4px;}
QPushButton#windowClose:hover {background:#f3dede;}
QMenu {border:1px solid #dadce0;border-radius:8px;padding:6px;}
QMenu::item {border-radius:4px;padding:7px 16px;}
QMenu::separator {height:1px;background:#e5e5e3;margin:5px 8px;}
QPushButton:hover {background:#eeeeec;color:#37352f;}
QPushButton:pressed {background:#eaeae7;color:#37352f;}
QPushButton#primary, QPushButton#primary:hover, QPushButton#primary:pressed {color:white;}
QPushButton#primary:pressed {background:#09579f;}
QPushButton#text:hover {background:#eeeeec;color:#37352f;}
QPushButton#danger:hover {background:#fff0f4;color:#b63b50;}
QMenu {background:#ffffff;color:#37352f;}
QMenu::item:selected {background:#eeeeec;color:#37352f;}
QMenu::item:disabled {color:#787774;}
QComboBox QAbstractItemView {background:#ffffff;color:#37352f;selection-background-color:#eaeae7;selection-color:#37352f;border:1px solid #dadce0;padding:4px;outline:0;}
QComboBox QAbstractItemView::item {min-height:30px;padding:3px 8px;}
QComboBox QAbstractItemView::item:selected {background:#eaeae7;color:#37352f;}
QLineEdit, QTextEdit, QPlainTextEdit, QDateEdit, QTimeEdit, QSpinBox {selection-background-color:#293e51;selection-color:white;}
QLabel#fieldLabel {font-size:12px;font-weight:500;color:#696864;}
QLabel#formError {font-size:12px;color:#b63b50;}
QPushButton#sectionTab {background:transparent;border:none;border-bottom:2px solid transparent;border-radius:0;padding:7px 10px;color:#696864;}
QPushButton#sectionTab[active="true"] {border-bottom:2px solid #2383e2;color:#37352f;font-weight:600;}
QPushButton#sectionTab:hover {background:#eeeeec;}
QPlainTextEdit#itemDetails {border:1px solid #dadce0;border-radius:7px;background:#fafaf9;padding:10px;font-size:14px;}
QLineEdit#itemTitle {font-size:22px;font-weight:600;border:none;border-bottom:1px solid transparent;padding:6px 0;background:transparent;}
QLineEdit#itemTitle[invalid="true"] {border-bottom:1px solid #b63b50;}
QFrame#dialogDivider {background:#e5e5e3;max-height:1px;border:none;}
QFrame#boardList {background:#f1f2f4;border:1px solid #e4e4e1;border-radius:11px;}
QLineEdit#listTitle {background:transparent;border:none;padding:5px 2px;font-weight:600;}
QLineEdit#listTitle:focus {background:#ffffff;border:1px solid #2383e2;border-radius:5px;}
QListWidget#boardCards::item {background:transparent;border:none;}
QFrame#focusContext {background:#fafaf9;border:1px solid #dadce0;border-radius:12px;}
QPushButton#focusTaskPicker {background:transparent;border:none;color:#1473ce;padding:5px 0;text-align:left;}
QPushButton#focusTaskPicker:hover {color:#2383e2;}
QPushButton#focusTaskPicker:disabled {color:#8b8b85;}
QProgressBar {background:#eeeeec;border:none;border-radius:3px;text-align:center;font-size:10px;}
QProgressBar::chunk {background:#2383e2;border-radius:3px;}
QScrollBar:horizontal {background:#fafaf9;height:10px;margin:0;border:none;}
QScrollBar::handle:horizontal {background:#dadce0;min-width:32px;border-radius:5px;}
QScrollBar::handle:horizontal:hover {background:#8b8b85;}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {width:0;height:0;background:transparent;border:none;}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {background:transparent;}
"""
STYLE += '''
QTimeEdit::up-button, QSpinBox::up-button {subcontrol-origin:border;subcontrol-position:top right;width:25px;border-left:1px solid #dadce0;background:#eeeeec;border-top-right-radius:4px;}
QTimeEdit::down-button, QSpinBox::down-button {subcontrol-origin:border;subcontrol-position:bottom right;width:25px;border-left:1px solid #dadce0;background:#eeeeec;border-bottom-right-radius:4px;}
QTimeEdit::up-button:hover, QTimeEdit::down-button:hover, QSpinBox::up-button:hover, QSpinBox::down-button:hover {background:#eaeae7;}
QTimeEdit::up-arrow, QSpinBox::up-arrow {image:url(__UP__);width:12px;height:12px;}
QTimeEdit::down-arrow, QSpinBox::down-arrow {image:url(__DOWN__);width:12px;height:12px;}
QTimeEdit, QSpinBox {padding-right:30px;}
'''.replace('__UP__', (_assets / 'step-up.svg').as_posix()).replace('__DOWN__', (_assets / 'step-down.svg').as_posix())

_DARK = {
    '#f1f2f4': '#292a2d',
    '#f1f3f4': '#343639', '#eeece9': '#343639', '#f5f7fa': '#292a2d',
    '#edf0f5': '#45484b', '#e6f1ff': '#3c4043', '#d6e9ff': '#294e73',
    '#b63b50': '#ed9ba8',
    '#deded9': '#454648',
    '#ffffff': '#202124', '#fafaf9': '#252629', '#fafafa': '#252629',
    '#f7f7f5': '#292a2d', '#f6f5f4': '#292a2d', '#f8f8f6': '#292a2d',
    '#eeeeec': '#343639', '#eeeeee': '#343639', '#efefec': '#343639', '#efefed': '#343639',
    '#eaeae7': '#3c4043', '#e9e9e7': '#3c4043', '#e8e6e2': '#3c4043',
    '#e5e5e3': '#3c4043', '#e4e4e1': '#45484b', '#ececea': '#3c4043',
    '#d9d6d1': '#5f6368', '#dadce0': '#5f6368', '#d7d7d2': '#5f6368',
    '#37352f': '#e8eaed', '#242321': '#e8eaed', '#202124': '#e8eaed', '#252522': '#e8eaed',
    '#303332': '#e8eaed', '#494641': '#e8eaed', '#5f5e5b': '#bdc1c6',
    '#69645f': '#bdc1c6', '#696864': '#bdc1c6', '#6b6b66': '#bdc1c6', '#666666': '#bdc1c6',
    '#73726d': '#a7aaa7', '#787774': '#a7aaa7', '#747775': '#a7aaa7', '#8b8b85': '#a7aaa7',
    '#eef6ff': '#26374a', '#eff9ee': '#263e30', '#fffbe6': '#413b24',
    '#f4efff': '#352d48', '#fff0f4': '#482d38', '#e6f3fe': '#293e51',
    '#e8f3fc': '#293e51', '#e6f4e9': '#294033', '#edf4fc': '#293e51',
    '#fff0a5': '#685a26', '#f1f1ef': '#343639',
}


def themed_color(value):
    from PySide6.QtWidgets import QApplication
    dark = bool(QApplication.instance() and QApplication.instance().property('tablaDark'))
    return _DARK.get(value.lower(), '#202124' if value == 'white' else value) if dark else value


def theme_stylesheet(source, dark):
    if not dark:
        return source
    import re
    # One pass avoids recursively mapping a background color into a text color.
    source = re.sub(r'#[0-9a-fA-F]{6}', lambda m: _DARK.get(m[0].lower(), m[0]), source)
    source = re.sub(r'(background(?:-color)?\s*:\s*)white\b', r'\1#202124', source)
    return source


def apply_appearance(app, dark):
    from PySide6.QtGui import QPalette
    app.setProperty('tablaDark', dark)
    palette = app.style().standardPalette()
    if dark:
        for role, color in ((QPalette.ColorRole.Window, '#202124'), (QPalette.ColorRole.Base, '#202124'),
            (QPalette.ColorRole.AlternateBase, '#292a2d'), (QPalette.ColorRole.Text, '#e8eaed'),
            (QPalette.ColorRole.WindowText, '#e8eaed'), (QPalette.ColorRole.Button, '#292a2d'),
            (QPalette.ColorRole.ButtonText, '#e8eaed'), (QPalette.ColorRole.PlaceholderText, '#9aa0a6'),
            (QPalette.ColorRole.Highlight, '#294e73'), (QPalette.ColorRole.HighlightedText, '#ffffff')):
            palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(theme_stylesheet(STYLE, dark))


def polish_surfaces(root):
    from PySide6.QtWidgets import QWidget, QApplication
    dark = bool(QApplication.instance().property('tablaDark'))
    for widget in [root, *root.findChildren(QWidget)]:
        original = widget.property('tablaOriginalStyle')
        if original is None:
            original = widget.styleSheet()
            widget.setProperty('tablaOriginalStyle', original)
        if original:
            converted = theme_stylesheet(original, dark)
            if widget.styleSheet() != converted:
                widget.setStyleSheet(converted)
