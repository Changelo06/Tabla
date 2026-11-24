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


def _render_icon(name: str, color: str, size: int, dpr: float) -> QIcon:
    cache = _icon_cache("glyphs")
    key = (name, color, size, dpr)
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
        f'fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
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
    if len(cache) > 256:
        cache.clear()
    cache[key] = result
    return result


def icon(name, color="#5b5b5e", size=22, preserve_color=False):
    from PySide6.QtWidgets import QApplication
    t = current_tokens()
    if (
        not preserve_color
        and QApplication.instance()
        and t.dark
        and color not in ("#ffffff", "#111112", "#2383e2", "#1878f8", "#2563eb", "#3b82f6", t.accent)
    ):
        color = t.ink_secondary
    return _render_icon(name, color, int(size), _display_dpr())


def navigation_icon(name, active=False, dark=False):
    """A quiet outline rail; active icons use high-contrast glyph with subtle dark bloom."""
    from .layer_effects import blurred_pixmap
    size = 21
    dpr = _display_dpr()
    t = current_tokens(dark)
    cache = _icon_cache("nav")
    key = (name, bool(active), t.key, dpr)
    cached = cache.get(key)
    if cached is not None:
        return cached
    px = max(1, round(size * dpr))
    color = t.ink_primary if active else t.ink_muted
    canvas = QPixmap(px, px)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if active and name == "home":
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            f'<path fill="{color}" d="M3 10 12 3 21 10v2h-2v9h-5v-7h-4v7H5v-9H3z"/></svg>'
        )
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
    else:
        _render_icon(name, color, size, dpr).paint(painter, 0, 0, px, px)
    painter.end()
    canvas.setDevicePixelRatio(dpr)
    if active and t.dark:
        halo = blurred_pixmap(canvas, 1.8)
        result = QPixmap(canvas.size())
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setOpacity(0.24)
        painter.drawPixmap(0, 0, px, px, halo)
        painter.setOpacity(1.0)
        painter.drawPixmap(0, 0, px, px, canvas)
        painter.end()
        result.setDevicePixelRatio(dpr)
        canvas = result
    out = QIcon(canvas)
    cache[key] = out
    return out


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
