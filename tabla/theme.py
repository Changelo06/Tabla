from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from pathlib import Path
import sys
from functools import lru_cache
from .tokens import (
    DAYLIGHT,
    OBSIDIAN,
    THEME_PRESETS,
    NOTE_COLORS_LIGHT,
    DARK_HEX_MAP,
    build_stylesheet,
    current_tokens,
    hex_map_for_tokens,
    resolve_theme,
)


def load_fonts():
    from PySide6.QtGui import QFontDatabase
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for name in ("Inter.ttf", "Manrope.ttf"):
        if QFontDatabase.addApplicationFont(str(root / "assets" / "fonts" / name)) < 0:
            raise RuntimeError(f"Could not load bundled font: {name}")


COLORS = dict(NOTE_COLORS_LIGHT)

PATHS = {
    "image": '<rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="8.5" cy="9" r="1.5"/><path d="m21 15.5-4.5-4.5-6.5 6.5M3.5 17l3.5-3.5 3 3"/>',
    "bullets": '<circle cx="4.5" cy="6.5" r="1" fill="currentColor" stroke="none"/><circle cx="4.5" cy="12" r="1" fill="currentColor" stroke="none"/><circle cx="4.5" cy="17.5" r="1" fill="currentColor" stroke="none"/><path d="M9 6.5h11M9 12h11M9 17.5h11"/>',
    "brand": '<path d="M4 3h10a5 5 0 0 1 0 10H9m11 8H10a5 5 0 0 1 0-10h5" stroke-width="5"/>',
    "home": '<path d="M3 10.5 12 3.5l9 7"/><path d="M5.5 9.5V19a1.5 1.5 0 0 0 1.5 1.5h10A1.5 1.5 0 0 0 18.5 19V9.5"/><path d="M9.5 20.5v-5.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v5.5"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2.5"/><path d="M8 3v4M16 3v4M3 10h18"/><circle cx="8" cy="14" r=".9" fill="currentColor" stroke="none"/><circle cx="12" cy="14" r=".9" fill="currentColor" stroke="none"/><circle cx="16" cy="14" r=".9" fill="currentColor" stroke="none"/><circle cx="8" cy="17.5" r=".9" fill="currentColor" stroke="none"/><circle cx="12" cy="17.5" r=".9" fill="currentColor" stroke="none"/>',
    "tasks": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="m8.5 12.2 2.4 2.4 4.8-5.2"/>',
    "table": '<rect x="3" y="4" width="18" height="16" rx="2.2"/><path d="M3 9.5h18M3 14.5h18M9.5 9.5V20"/>',
    "note": '<path d="M14.5 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V7.5z"/><path d="M14.5 3v4.5H19M8.5 12.5h7M8.5 16h4.5"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4.5l2 2.5H19a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 4.5 4.5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "left": '<path d="m14.5 6-6 6 6 6"/>',
    "right": '<path d="m9.5 6 6 6-6 6"/>',
    "link": '<path d="m10 14 4-4m-6 7-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0m4 0 1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0"/>',
    "archive": '<rect x="3" y="4" width="18" height="4.5" rx="1.2"/><path d="M5 8.5V19a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19V8.5M9.5 13h5"/>',
    "trash": '<path d="M3.5 6h17M8.5 6V4.5A1.5 1.5 0 0 1 10 3h4a1.5 1.5 0 0 1 1.5 1.5V6M5.5 6l1 13.2A1.8 1.8 0 0 0 8.3 21h7.4a1.8 1.8 0 0 0 1.8-1.8L18.5 6M10 10.5v6M14 10.5v6"/>',
    "play": '<path d="m8.5 5.5 10.5 6.5-10.5 6.5z"/>',
    "pause": '<rect x="7" y="5" width="3.2" height="14" rx="1"/><rect x="13.8" y="5" width="3.2" height="14" rx="1"/>',
    "pin": '<path d="M12 16.5V21M9 4h6l-1 5.5 3 3H7l3-3z"/>',
    "palette": '<path d="M12 3a9 9 0 1 0 0 18h1.5a2 2 0 0 0 0-4h-.8a1.8 1.8 0 0 1 0-3.6h3.1A5.2 5.2 0 0 0 21 8.2C21 5.2 17 3 12 3z"/><circle cx="7.5" cy="10.5" r=".9" fill="currentColor" stroke="none"/><circle cx="10.5" cy="7" r=".9" fill="currentColor" stroke="none"/><circle cx="15" cy="7.5" r=".9" fill="currentColor" stroke="none"/><circle cx="7" cy="14.5" r=".9" fill="currentColor" stroke="none"/>',
    "undo": '<path d="M8.5 6 4 10.5 8.5 15M4 10.5h10.5a5.2 5.2 0 0 1 0 10.4H12"/>',
    "redo": '<path d="m15.5 6 4.5 4.5-4.5 4.5M20 10.5H9.5a5.2 5.2 0 0 0 0 10.4H12"/>',
    "more": '<circle cx="12" cy="5.5" r="1.25" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.25" fill="currentColor" stroke="none"/><circle cx="12" cy="18.5" r="1.25" fill="currentColor" stroke="none"/>',
    "more-h": '<circle cx="5.5" cy="12" r="1.25" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.25" fill="currentColor" stroke="none"/><circle cx="18.5" cy="12" r="1.25" fill="currentColor" stroke="none"/>',
    "sidebar": '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M9 4v16"/>',
    "minimize": '<path d="M5 12h14"/>',
    "maximize": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "restore": '<rect x="4" y="8" width="12" height="12" rx="2"/><path d="M8 8V4h12v12h-4"/>',
    "close": '<path d="m6 6 12 12M6 18 18 6"/>',
    "attachment": '<path d="m8 13 7-7a3 3 0 0 1 4 4L9 20a5 5 0 0 1-7-7L13 2m-7 13 9-9"/>',
    "export": '<path d="M12 15V4m-4 4 4-4 4 4M4 14.5v4A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5v-4"/>',
    "import": '<path d="M12 4v11m-4-4 4 4 4-4M4 14.5v4A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5v-4"/>',
    "check": '<path d="m5 12.5 4.5 4.5 9.5-10"/>',
    "board": '<rect x="3.5" y="4" width="4.4" height="16" rx="1.2"/><rect x="9.8" y="4" width="4.4" height="11.5" rx="1.2"/><rect x="16.1" y="4" width="4.4" height="7.5" rx="1.2"/>',
    "format": '<path d="M5 18 9.5 6h1L15 18M6.8 14h6.4M17 12c1.2-.8 3-.5 3 1.2V18m0-3.2c-1.8-.3-3.2.5-3.2 1.7 0 1 .9 1.6 2 1.5"/>',
    "grip": '<circle cx="9" cy="6" r="1.1" fill="currentColor" stroke="none"/><circle cx="15" cy="6" r="1.1" fill="currentColor" stroke="none"/><circle cx="9" cy="12" r="1.1" fill="currentColor" stroke="none"/><circle cx="15" cy="12" r="1.1" fill="currentColor" stroke="none"/><circle cx="9" cy="18" r="1.1" fill="currentColor" stroke="none"/><circle cx="15" cy="18" r="1.1" fill="currentColor" stroke="none"/>',
}


def _display_dpr() -> float:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app and app.primaryScreen():
        return round(max(1.0, float(app.primaryScreen().devicePixelRatio())), 2)
    return 2.0


def _icon_cache(bucket: str) -> dict:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return {}
    caches = getattr(app, "_tabla_icon_caches", None)
    if caches is None:
        caches = {}
        app._tabla_icon_caches = caches
        app.aboutToQuit.connect(caches.clear)
    return caches.setdefault(bucket, {})


def _render_icon(name: str, color: str, size: int, dpr: float, stroke_width: float = 1.65) -> QIcon:
    cache = _icon_cache("glyphs")
    key = (name, color, size, dpr, round(stroke_width, 2))
    cached = cache.get(key)
    if cached is not None:
        return cached
    path = (
        PATHS["pin"].replace("<path ", f'<path fill="{color}" ')
        if name == "pin-filled"
        else PATHS.get(name, PATHS["note"]).replace("currentColor", color)
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="{stroke_width:.2f}" stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
    )
    px = max(1, round(size * dpr))
    pixmap = QPixmap(px, px)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    result = QIcon(pixmap)
    if len(cache) > 320:
        cache.clear()
    cache[key] = result
    return result


def icon(name, color="#5b5b5e", size=22, preserve_color=False, stroke_width=1.65):
    from PySide6.QtWidgets import QApplication
    t = current_tokens()
    if (
        not preserve_color
        and QApplication.instance()
        and t.dark
        and color not in ("#ffffff", "#111112", "#2383e2", "#1878f8", "#2563eb", "#3b82f6", t.accent)
    ):
        color = t.ink_secondary
    return _render_icon(name, color, int(size), _display_dpr(), stroke_width)


def navigation_icon(name, active=False, dark=False):
    """Unified crisp stroke icon family across all rail items (consistent active/inactive geometry)."""
    size = 20
    dpr = _display_dpr()
    t = current_tokens(dark)
    color = t.ink_primary if active else t.ink_muted
    stroke = 1.95 if active else 1.60
    return _render_icon(name, color, size, dpr, stroke)


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
        painter.setBrush(QColor(DAYLIGHT.bg_surface))
        painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="none" stroke="#161617" stroke-linecap="round" stroke-linejoin="round">'
            + PATHS["brand"]
            + "</svg>"
        )
        QSvgRenderer(QByteArray(svg.encode())).render(
            painter, QRectF(size * 0.18, size * 0.18, size * 0.64, size * 0.64)
        )
        painter.end()
        result.addPixmap(pixmap)
    return result


_assets = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets"
STYLE = build_stylesheet(False, _assets)
_DARK = DARK_HEX_MAP


def themed_color(value):
    t = current_tokens()
    if t.key == "light":
        return value
    mapping = hex_map_for_tokens(t)
    return mapping.get(value.lower(), t.bg_canvas if value == "white" else value)


def theme_stylesheet(source, dark):
    t = current_tokens(dark)
    if t.key == "light":
        return source
    import re
    mapping = hex_map_for_tokens(t)
    source = re.sub(r"#[0-9a-fA-F]{6}", lambda m: mapping.get(m[0].lower(), m[0]), source)
    source = re.sub(r"(background(?:-color)?\s*:\s*)white\b", rf"\1{t.bg_canvas}", source)
    return source


def apply_appearance(app, dark):
    from PySide6.QtGui import QPalette
    t = resolve_theme(dark)
    app.setProperty("tablaTheme", t.key)
    app.setProperty("tablaDark", t.dark)
    palette = app.style().standardPalette()
    for role, color in (
        (QPalette.ColorRole.Window, t.bg_canvas),
        (QPalette.ColorRole.Base, t.bg_elevated),
        (QPalette.ColorRole.AlternateBase, t.bg_surface),
        (QPalette.ColorRole.Text, t.ink_primary),
        (QPalette.ColorRole.WindowText, t.ink_primary),
        (QPalette.ColorRole.Button, t.bg_surface),
        (QPalette.ColorRole.ButtonText, t.ink_primary),
        (QPalette.ColorRole.PlaceholderText, t.ink_muted),
        (QPalette.ColorRole.Highlight, t.selection_bg),
        (QPalette.ColorRole.HighlightedText, t.selection_fg),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet(t, _assets))


def polish_surfaces(root):
    from PySide6.QtWidgets import QWidget
    t = current_tokens()
    for widget in [root, *root.findChildren(QWidget)]:
        if widget.property("tablaThemed"):
            continue
        original = widget.property("tablaOriginalStyle")
        if original is None:
            original = widget.styleSheet()
            widget.setProperty("tablaOriginalStyle", original)
        if original:
            converted = theme_stylesheet(original, t)
            if widget.styleSheet() != converted:
                widget.setStyleSheet(converted)
