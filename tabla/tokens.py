"""Semantic design tokens and unified stylesheet builder (Tabla × Dashcon)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


UI_FONT_FAMILY = "Segoe UI Variable Text" if sys.platform == "win32" else "Inter"
UI_FONT_CSS = "'Segoe UI Variable Text', 'Segoe UI', 'Inter', sans-serif" if sys.platform == "win32" else "'Inter', sans-serif"
PROSE_FONT_FAMILY = "Inter"
PROSE_FONT_CSS = "'Inter', 'Segoe UI', sans-serif"
MONO_FONT_FAMILY = "Consolas"
MONO_FONT_CSS = "'JetBrains Mono', 'Cascadia Mono', 'Consolas', monospace"


def _resolve_ui_family() -> str:
    if sys.platform != "win32":
        return "Inter"
    from PySide6.QtGui import QFontDatabase
    families = set(QFontDatabase.families())
    for candidate in ("Segoe UI Variable Text", "Segoe UI", "Inter"):
        if candidate in families:
            return candidate
    return "Inter"


def ui_font(px: int = 13, weight=None):
    from PySide6.QtGui import QFont
    f = QFont(_resolve_ui_family())
    f.setPixelSize(px)
    if weight is not None:
        f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    return f


def prose_font(px: int = 15, weight=None):
    from PySide6.QtGui import QFont
    f = QFont(PROSE_FONT_FAMILY)
    f.setPixelSize(px)
    if weight is not None:
        f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    return f


def mono_font(px: int = 12, weight=None):
    from PySide6.QtGui import QFont
    from PySide6.QtGui import QFontDatabase
    families = set(QFontDatabase.families())
    fam = next((c for c in ("JetBrains Mono", "Cascadia Mono", "Consolas") if c in families), "Consolas")
    f = QFont(fam)
    f.setPixelSize(px)
    if weight is not None:
        f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferDefaultHinting)
    return f


def display_numeral_font(px: int = 86, weight=None):
    """Premium geometric display font with OpenType tabular lining figures and centered colon."""
    from PySide6.QtGui import QFont, QFontDatabase
    families = set(QFontDatabase.families())
    fam = next(
        (c for c in ("Manrope", "Inter", "Segoe UI Variable Display", "Segoe UI") if c in families),
        PROSE_FONT_FAMILY,
    )
    f = QFont(fam)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight.DemiBold if weight is None else weight)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -2.0)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if hasattr(f, "setFeature") and hasattr(QFont, "Tag"):
        f.setFeature(QFont.Tag("tnum"), 1)
        f.setFeature(QFont.Tag("case"), 1)
    return f


@dataclass(frozen=True)
class ThemeTokens:
    key: str
    label: str
    tagline: str
    dark: bool
    bg_canvas: str
    bg_surface: str
    bg_surface_hover: str
    bg_surface_active: str
    bg_elevated: str
    bg_pill: str
    bg_pill_hover: str
    bg_pill_pressed: str
    ink_primary: str
    ink_secondary: str
    ink_muted: str
    ink_inverse: str
    border_subtle: str
    border_strong: str
    accent: str
    accent_soft: str
    accent_hover: str
    danger: str
    danger_soft: str
    selection_bg: str
    selection_fg: str
    scrollbar_handle: str
    scrollbar_hover: str
    tooltip_bg: str
    tooltip_fg: str
    tooltip_border: str


DAYLIGHT = ThemeTokens(
    key="light",
    label="Daylight",
    tagline="Crisp studio white",
    dark=False,
    bg_canvas="#ffffff",
    bg_surface="#f5f5f7",
    bg_surface_hover="#ececef",
    bg_surface_active="#e5e5ea",
    bg_elevated="#ffffff",
    bg_pill="#161617",
    bg_pill_hover="#2c2c2e",
    bg_pill_pressed="#0b0b0c",
    ink_primary="#161617",
    ink_secondary="#5b5b5e",
    ink_muted="#86868b",
    ink_inverse="#ffffff",
    border_subtle="#e6e6e9",
    border_strong="#d2d2d7",
    accent="#2563eb",
    accent_soft="#eef5ff",
    accent_hover="#1d4ed8",
    danger="#c9364e",
    danger_soft="#fff1f4",
    selection_bg="#dbeafe",
    selection_fg="#161617",
    scrollbar_handle="rgba(22, 22, 23, 0.18)",
    scrollbar_hover="rgba(22, 22, 23, 0.34)",
    tooltip_bg="#161617",
    tooltip_fg="#ffffff",
    tooltip_border="#2c2c2e",
)

PAPER = ThemeTokens(
    key="paper",
    label="Paper",
    tagline="Warm editorial ivory",
    dark=False,
    bg_canvas="#fbf9f5",
    bg_surface="#f3efe7",
    bg_surface_hover="#eae4d8",
    bg_surface_active="#e1d9ca",
    bg_elevated="#fffdf9",
    bg_pill="#231f1a",
    bg_pill_hover="#38322a",
    bg_pill_pressed="#14120f",
    ink_primary="#231f1a",
    ink_secondary="#615a51",
    ink_muted="#8f877b",
    ink_inverse="#fbf9f5",
    border_subtle="#e6dfd3",
    border_strong="#d4cbbd",
    accent="#2c5ea8",
    accent_soft="#edf3fb",
    accent_hover="#214987",
    danger="#c23b4b",
    danger_soft="#fdefef",
    selection_bg="#dce8f8",
    selection_fg="#231f1a",
    scrollbar_handle="rgba(35, 31, 26, 0.18)",
    scrollbar_hover="rgba(35, 31, 26, 0.34)",
    tooltip_bg="#231f1a",
    tooltip_fg="#fbf9f5",
    tooltip_border="#3a342c",
)

MIST = ThemeTokens(
    key="mist",
    label="Mist",
    tagline="Cool low-glare slate",
    dark=False,
    bg_canvas="#f6f8fa",
    bg_surface="#edf1f5",
    bg_surface_hover="#e2e8f0",
    bg_surface_active="#d8e1eb",
    bg_elevated="#ffffff",
    bg_pill="#161b22",
    bg_pill_hover="#2b3340",
    bg_pill_pressed="#0d1117",
    ink_primary="#161b22",
    ink_secondary="#526071",
    ink_muted="#7c8b9c",
    ink_inverse="#ffffff",
    border_subtle="#dce3ec",
    border_strong="#c6d1df",
    accent="#2563eb",
    accent_soft="#e8f1ff",
    accent_hover="#1d4ed8",
    danger="#c9364e",
    danger_soft="#fdeef1",
    selection_bg="#d7e6fe",
    selection_fg="#161b22",
    scrollbar_handle="rgba(22, 27, 34, 0.18)",
    scrollbar_hover="rgba(22, 27, 34, 0.34)",
    tooltip_bg="#161b22",
    tooltip_fg="#ffffff",
    tooltip_border="#2e3744",
)

SAGE = ThemeTokens(
    key="sage",
    label="Sage",
    tagline="Soft botanical calm",
    dark=False,
    bg_canvas="#f6f8f6",
    bg_surface="#edf2ee",
    bg_surface_hover="#e2eae4",
    bg_surface_active="#d6e2d9",
    bg_elevated="#fbfdfb",
    bg_pill="#1b241e",
    bg_pill_hover="#2d3b32",
    bg_pill_pressed="#111713",
    ink_primary="#1b241e",
    ink_secondary="#526258",
    ink_muted="#7c8d82",
    ink_inverse="#fbfdfb",
    border_subtle="#dbe5dd",
    border_strong="#c5d4c9",
    accent="#2e7d5b",
    accent_soft="#e6f4ed",
    accent_hover="#236347",
    danger="#c23b4b",
    danger_soft="#fdeef0",
    selection_bg="#d2eadf",
    selection_fg="#1b241e",
    scrollbar_handle="rgba(27, 36, 30, 0.18)",
    scrollbar_hover="rgba(27, 36, 30, 0.34)",
    tooltip_bg="#1b241e",
    tooltip_fg="#fbfdfb",
    tooltip_border="#324036",
)

OBSIDIAN = ThemeTokens(
    key="dark",
    label="Obsidian",
    tagline="Deep studio dark",
    dark=True,
    bg_canvas="#0b0b0c",
    bg_surface="#141416",
    bg_surface_hover="#1e1e22",
    bg_surface_active="#26262b",
    bg_elevated="#1c1c1f",
    bg_pill="#f5f5f7",
    bg_pill_hover="#ffffff",
    bg_pill_pressed="#e2e2e7",
    ink_primary="#f5f5f7",
    ink_secondary="#a1a1a6",
    ink_muted="#6e6e73",
    ink_inverse="#111112",
    border_subtle="#242428",
    border_strong="#34343a",
    accent="#3b82f6",
    accent_soft="#162133",
    accent_hover="#60a5fa",
    danger="#f28b9c",
    danger_soft="#2d1920",
    selection_bg="#223756",
    selection_fg="#f5f5f7",
    scrollbar_handle="rgba(245, 245, 247, 0.20)",
    scrollbar_hover="rgba(245, 245, 247, 0.36)",
    tooltip_bg="#f5f5f7",
    tooltip_fg="#111112",
    tooltip_border="#d2d2d7",
)

GRAPHITE = ThemeTokens(
    key="graphite",
    label="Graphite",
    tagline="Soft neutral charcoal",
    dark=True,
    bg_canvas="#19191b",
    bg_surface="#212125",
    bg_surface_hover="#2b2b31",
    bg_surface_active="#34343b",
    bg_elevated="#26262b",
    bg_pill="#f1f1f4",
    bg_pill_hover="#ffffff",
    bg_pill_pressed="#dcdce2",
    ink_primary="#ececf0",
    ink_secondary="#a4a4ad",
    ink_muted="#75757f",
    ink_inverse="#161618",
    border_subtle="#2f2f36",
    border_strong="#404049",
    accent="#4f8ff7",
    accent_soft="#1c293f",
    accent_hover="#73a7fa",
    danger="#f28b9c",
    danger_soft="#331e24",
    selection_bg="#283d5e",
    selection_fg="#f1f1f4",
    scrollbar_handle="rgba(236, 236, 240, 0.20)",
    scrollbar_hover="rgba(236, 236, 240, 0.36)",
    tooltip_bg="#ececf0",
    tooltip_fg="#161618",
    tooltip_border="#c8c8d0",
)

NORD = ThemeTokens(
    key="nord",
    label="Nord",
    tagline="Calm arctic slate",
    dark=True,
    bg_canvas="#1e222a",
    bg_surface="#252a34",
    bg_surface_hover="#2e3440",
    bg_surface_active="#373f4e",
    bg_elevated="#2a303c",
    bg_pill="#eceff4",
    bg_pill_hover="#ffffff",
    bg_pill_pressed="#d8dee9",
    ink_primary="#eceff4",
    ink_secondary="#aeb8c8",
    ink_muted="#7b889e",
    ink_inverse="#1e222a",
    border_subtle="#333a48",
    border_strong="#444e61",
    accent="#88c0d0",
    accent_soft="#243542",
    accent_hover="#9bd0df",
    danger="#e27d87",
    danger_soft="#36242b",
    selection_bg="#33485c",
    selection_fg="#eceff4",
    scrollbar_handle="rgba(236, 239, 244, 0.20)",
    scrollbar_hover="rgba(236, 239, 244, 0.36)",
    tooltip_bg="#eceff4",
    tooltip_fg="#1e222a",
    tooltip_border="#cbd3e0",
)

ESPRESSO = ThemeTokens(
    key="espresso",
    label="Espresso",
    tagline="Warm evening dark",
    dark=True,
    bg_canvas="#171513",
    bg_surface="#201d1a",
    bg_surface_hover="#2a2622",
    bg_surface_active="#342f2a",
    bg_elevated="#25221e",
    bg_pill="#f2ece4",
    bg_pill_hover="#fbf8f3",
    bg_pill_pressed="#dfd6ca",
    ink_primary="#f2ece4",
    ink_secondary="#b2a89b",
    ink_muted="#80776c",
    ink_inverse="#171513",
    border_subtle="#302b26",
    border_strong="#423b34",
    accent="#d98c4a",
    accent_soft="#312418",
    accent_hover="#e7a468",
    danger="#e47c84",
    danger_soft="#331f22",
    selection_bg="#423121",
    selection_fg="#f2ece4",
    scrollbar_handle="rgba(242, 236, 228, 0.20)",
    scrollbar_hover="rgba(242, 236, 228, 0.36)",
    tooltip_bg="#f2ece4",
    tooltip_fg="#171513",
    tooltip_border="#cfc5b8",
)

THEME_PRESETS: tuple[ThemeTokens, ...] = (
    DAYLIGHT,
    PAPER,
    MIST,
    SAGE,
    OBSIDIAN,
    GRAPHITE,
    NORD,
    ESPRESSO,
)

_THEME_BY_NAME: dict[str, ThemeTokens] = {}
for _preset in THEME_PRESETS:
    _THEME_BY_NAME[_preset.key.lower()] = _preset
    _THEME_BY_NAME[_preset.label.lower()] = _preset
_THEME_BY_NAME["daylight"] = DAYLIGHT
_THEME_BY_NAME["obsidian"] = OBSIDIAN


def resolve_theme(value: str | bool | ThemeTokens | None) -> ThemeTokens:
    if isinstance(value, ThemeTokens):
        return value
    if isinstance(value, bool):
        return OBSIDIAN if value else DAYLIGHT
    if isinstance(value, str):
        return _THEME_BY_NAME.get(value.strip().lower(), DAYLIGHT)
    return DAYLIGHT


# Harmonized light/dark semantic washes (eliminates muddy dark tints like #413b24)
NOTE_COLORS_LIGHT = {
    "blue": ("#eef5ff", "#2563eb"),
    "green": ("#eef9f2", "#16a34a"),
    "yellow": ("#fdf9e7", "#ca8a04"),
    "violet": ("#f5f0ff", "#7c3aed"),
    "rose": ("#fff1f4", "#e11d48"),
    "gray": ("#f5f5f7", "#6e6e73"),
}

NOTE_COLORS_DARK = {
    "blue": ("#161e2b", "#3b82f6"),
    "green": ("#15221c", "#22c55e"),
    "yellow": ("#242015", "#eab308"),
    "violet": ("#1f1929", "#a78bfa"),
    "rose": ("#28181e", "#fb7185"),
    "gray": ("#1c1c1f", "#8e8e93"),
}


def hex_map_for_tokens(t: ThemeTokens) -> dict[str, str]:
    """Map legacy inline Daylight hex colors onto any active theme preset."""
    if t.key == "light":
        return {}
    base = {
        # Surfaces & canvas
        "#ffffff": t.bg_canvas,
        "#fafaf9": t.bg_surface,
        "#fafafa": t.bg_surface,
        "#f7f7f5": t.bg_surface,
        "#f6f5f4": t.bg_surface,
        "#f8f8f6": t.bg_surface,
        "#f5f5f7": t.bg_surface,
        "#f5f7fa": t.bg_surface,
        "#f1f2f4": t.bg_surface,
        "#f1f3f4": t.bg_surface_hover,
        "#f1f1ef": t.bg_surface_hover,
        "#eeece9": t.bg_surface_hover,
        "#eeeeec": t.bg_surface_hover,
        "#eeeeee": t.bg_surface_hover,
        "#efefec": t.bg_surface_hover,
        "#efefed": t.bg_surface_hover,
        "#ececef": t.bg_surface_hover,
        "#eaeae7": t.bg_surface_active,
        # Borders
        "#e9e9e7": t.border_subtle,
        "#e8e6e2": t.border_subtle,
        "#e6e6e9": t.border_subtle,
        "#e5e5e3": t.border_subtle,
        "#e4e4e1": t.border_subtle,
        "#ececea": t.border_subtle,
        "#edf0f5": t.border_subtle,
        "#deded9": t.border_strong,
        "#d9d6d1": t.border_strong,
        "#dadce0": t.border_strong,
        "#d7d7d2": t.border_strong,
        "#d2d2d7": t.border_strong,
        # Inks
        "#161617": t.ink_primary,
        "#37352f": t.ink_primary,
        "#242321": t.ink_primary,
        "#202124": t.ink_primary,
        "#252522": t.ink_primary,
        "#303332": t.ink_primary,
        "#494641": t.ink_primary,
        "#5b5b5e": t.ink_secondary,
        "#5f5e5b": t.ink_secondary,
        "#69645f": t.ink_secondary,
        "#696864": t.ink_secondary,
        "#6b6b66": t.ink_secondary,
        "#666666": t.ink_secondary,
        "#73726d": t.ink_muted,
        "#787774": t.ink_muted,
        "#747775": t.ink_muted,
        "#80868b": t.ink_muted,
        "#86868b": t.ink_muted,
        "#8b8b85": t.ink_muted,
        "#a5a5a0": t.ink_muted,
        "#aaa9a3": t.ink_muted,
    }
    if t.dark:
        base.update({
            "#eef5ff": NOTE_COLORS_DARK["blue"][0],
            "#eef6ff": NOTE_COLORS_DARK["blue"][0],
            "#eef9f2": NOTE_COLORS_DARK["green"][0],
            "#eff9ee": NOTE_COLORS_DARK["green"][0],
            "#fdf9e7": NOTE_COLORS_DARK["yellow"][0],
            "#fffbe6": NOTE_COLORS_DARK["yellow"][0],
            "#f5f0ff": NOTE_COLORS_DARK["violet"][0],
            "#f4efff": NOTE_COLORS_DARK["violet"][0],
            "#fff1f4": NOTE_COLORS_DARK["rose"][0],
            "#fff0f4": NOTE_COLORS_DARK["rose"][0],
            "#e6f1ff": t.accent_soft,
            "#e6f3fe": t.accent_soft,
            "#e8f0fe": t.accent_soft,
            "#e8f3fc": t.accent_soft,
            "#edf4fc": t.accent_soft,
            "#d6e9ff": t.selection_bg,
            "#e6f4e9": NOTE_COLORS_DARK["green"][0],
            "#fff0a5": "#4d4019",
            "#b63b50": t.danger,
            "#c9364e": t.danger,
        })
    return base


# Backwards-compatible map for legacy inline hex colors -> Obsidian Studio tokens
DARK_HEX_MAP = hex_map_for_tokens(OBSIDIAN)


def current_tokens(dark: str | bool | ThemeTokens | None = None) -> ThemeTokens:
    if isinstance(dark, ThemeTokens):
        return dark
    if isinstance(dark, str):
        return resolve_theme(dark)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    active_key = app.property("tablaTheme") if app else None
    if active_key:
        active = resolve_theme(str(active_key))
    else:
        active = OBSIDIAN if (app and app.property("tablaDark")) else DAYLIGHT
    if isinstance(dark, bool):
        return active if active.dark == dark else (OBSIDIAN if dark else DAYLIGHT)
    return active


def build_stylesheet(dark: str | bool | ThemeTokens, assets_dir: Path) -> str:
    """Generate one clean, non-redundant QSS directly from semantic ThemeTokens."""
    t = resolve_theme(dark)
    check_icon = (assets_dir / "check-white.svg").as_posix()
    down_icon = (assets_dir / "chevron-down.svg").as_posix()
    step_up = (assets_dir / "step-up.svg").as_posix()
    step_down = (assets_dir / "step-down.svg").as_posix()
    pill_focus = t.accent
    close_hover = t.danger_soft
    disabled_fg = t.ink_muted
    disabled_bg = t.bg_surface

    return f"""
QWidget {{
    font-family: {UI_FONT_CSS};
    font-size: 13px;
    color: {t.ink_primary};
}}
QMainWindow, QWidget#appRoot, QFrame#workspace {{
    background: {t.bg_canvas};
    border: none;
    border-radius: 0;
}}
QWidget#sidebar {{
    background: {t.bg_surface};
    border-right: 1px solid {t.border_subtle};
}}
QFrame#card, QFrame#smallCard {{
    background: {t.bg_elevated};
    border: 1px solid {t.border_subtle};
    border-radius: 12px;
}}
QFrame#segmentedTrack {{
    background: {t.bg_surface};
    border: 1px solid {t.border_subtle};
    border-radius: 11px;
}}
QLabel {{
    background: transparent;
}}
QLabel#title {{
    font-family: {PROSE_FONT_CSS};
    font-size: 28px;
    font-weight: 700;
    color: {t.ink_primary};
}}
QLabel#section {{
    font-family: {PROSE_FONT_CSS};
    font-size: 15px;
    font-weight: 600;
    color: {t.ink_primary};
}}
QLabel#subtitle, QLabel#muted {{
    font-family: {UI_FONT_CSS};
    font-size: 12px;
    color: {t.ink_muted};
}}
QLabel#reading {{
    font-family: {PROSE_FONT_CSS};
    font-size: 14px;
    color: {t.ink_primary};
}}
QLabel#composer {{
    font-size: 14px;
    color: {t.ink_muted};
}}
QLabel#fieldLabel {{
    font-size: 12px;
    font-weight: 500;
    color: {t.ink_secondary};
}}
QLabel#formError {{
    font-size: 12px;
    color: {t.danger};
}}

/* Buttons: unified control geometry with zero 1px focus shift */
QPushButton {{
    background: {t.bg_elevated};
    color: {t.ink_primary};
    border: 1px solid {t.border_strong};
    border-radius: 9px;
    padding: 6px 12px;
    min-height: 22px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {t.bg_surface_hover};
    border-color: {t.border_strong};
    color: {t.ink_primary};
}}
QPushButton:pressed {{
    background: {t.bg_surface_active};
    color: {t.ink_primary};
}}
QPushButton:focus, QToolButton:focus {{
    border: 1px solid {pill_focus};
}}
QPushButton:disabled {{
    color: {disabled_fg};
    background: {disabled_bg};
    border-color: {t.border_subtle};
}}

/* Primary CTA: Dashcon monochrome-first tactile pill */
QPushButton#primary {{
    background: {t.bg_pill};
    color: {t.ink_inverse};
    border: 1px solid {t.bg_pill};
    border-radius: 15px;
    padding: 6px 14px;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: {t.bg_pill_hover};
    border-color: {t.bg_pill_hover};
    color: {t.ink_inverse};
}}
QPushButton#primary:pressed {{
    background: {t.bg_pill_pressed};
    color: {t.ink_inverse};
}}
QPushButton#primary:focus {{
    border: 1px solid {pill_focus};
}}

QPushButton#danger {{
    color: {t.danger};
}}
QPushButton#danger:hover {{
    background: {t.danger_soft};
    border-color: {t.danger};
    color: {t.danger};
}}
QPushButton#nav {{
    background: transparent;
    border: none;
    text-align: left;
    padding: 6px 10px;
    border-radius: 10px;
    min-height: 22px;
    color: {t.ink_secondary};
}}
QPushButton#nav:hover {{
    background: {t.bg_surface_hover};
    color: {t.ink_primary};
}}
QPushButton#nav[active="true"] {{
    background: {t.bg_surface_active};
    color: {t.ink_primary};
    font-weight: 600;
}}
QPushButton#tab {{
    background: transparent;
    border: 1px solid transparent;
    padding: 4px 11px;
    border-radius: 8px;
    min-height: 20px;
    color: {t.ink_secondary};
    font-weight: 500;
}}
QPushButton#tab:hover {{
    background: {t.bg_surface_hover};
    color: {t.ink_primary};
}}
QPushButton#tab[active="true"] {{
    color: {t.ink_primary};
    background: {t.bg_elevated};
    border: 1px solid {t.border_subtle};
    font-weight: 600;
}}
QPushButton#text {{
    border: none;
    background: transparent;
    color: {t.ink_secondary};
    text-align: left;
    padding: 5px 7px;
    border-radius: 8px;
}}
QPushButton#text:hover {{
    background: {t.bg_surface_hover};
    color: {t.ink_primary};
}}
QPushButton#icon {{
    padding: 6px;
    min-width: 21px;
}}
QPushButton#sectionTab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    padding: 7px 10px;
    color: {t.ink_secondary};
}}
QPushButton#sectionTab[active="true"] {{
    border-bottom: 2px solid {t.ink_primary};
    color: {t.ink_primary};
    font-weight: 600;
}}
QPushButton#sectionTab:hover {{
    background: {t.bg_surface};
}}

/* Inputs */
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit, QTimeEdit, QSpinBox {{
    background: {t.bg_elevated};
    color: {t.ink_primary};
    border: 1px solid {t.border_strong};
    border-radius: 9px;
    padding: 6px 9px;
    font-size: 13px;
    selection-background-color: {t.selection_bg};
    selection-color: {t.selection_fg};
    placeholder-text-color: {t.ink_muted};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus {{
    border: 1px solid {t.accent};
}}
QDateEdit:disabled {{
    background: {t.bg_surface};
    color: {t.ink_muted};
    border-color: {t.border_subtle};
}}
QPlainTextEdit#noteEditor, QTextBrowser {{
    font-family: 'Inter';
    border: none;
    background: transparent;
    font-size: 15px;
    padding: 12px;
}}
QPlainTextEdit#itemDetails {{
    border: 1px solid {t.border_subtle};
    border-radius: 10px;
    background: {t.bg_surface};
    padding: 10px;
    font-size: 14px;
}}
QLineEdit#itemTitle {{
    font-size: 22px;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid transparent;
    padding: 6px 0;
    background: transparent;
}}
QLineEdit#itemTitle[invalid="true"] {{
    border-bottom: 1px solid {t.danger};
}}

/* Combo & Steppers */
QComboBox {{
    padding-right: 26px;
}}
QComboBox::drop-down, QDateEdit::drop-down {{
    border: none;
    width: 23px;
}}
QComboBox::down-arrow, QDateEdit::down-arrow {{
    image: url({down_icon});
    width: 13px;
    height: 13px;
}}
QComboBox QAbstractItemView {{
    background: {t.bg_elevated};
    color: {t.ink_primary};
    selection-background-color: {t.bg_surface_hover};
    selection-color: {t.ink_primary};
    border: 1px solid {t.border_strong};
    border-radius: 10px;
    padding: 4px;
    outline: 0;
}}
QComboBox QAbstractItemView::item {{
    min-height: 30px;
    padding: 3px 8px;
    border-radius: 6px;
}}
QComboBox QAbstractItemView::item:selected {{
    background: {t.bg_surface_hover};
    color: {t.ink_primary};
}}
QTimeEdit, QSpinBox {{
    padding-right: 30px;
}}
QTimeEdit::up-button, QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 25px;
    border-left: 1px solid {t.border_subtle};
    background: {t.bg_surface};
    border-top-right-radius: 8px;
}}
QTimeEdit::down-button, QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 25px;
    border-left: 1px solid {t.border_subtle};
    background: {t.bg_surface};
    border-bottom-right-radius: 8px;
}}
QTimeEdit::up-button:hover, QTimeEdit::down-button:hover, QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {t.bg_surface_hover};
}}
QTimeEdit::up-arrow, QSpinBox::up-arrow {{
    image: url({step_up});
    width: 12px;
    height: 12px;
}}
QTimeEdit::down-arrow, QSpinBox::down-arrow {{
    image: url({step_down});
    width: 12px;
    height: 12px;
}}

/* Checkboxes */
QCheckBox {{
    spacing: 9px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 17px;
    height: 17px;
    border: 1.5px solid {t.border_strong};
    border-radius: 5px;
    background: {t.bg_elevated};
}}
QCheckBox::indicator:checked {{
    background: {t.accent};
    border-color: {t.accent};
    image: url({check_icon});
}}
QCheckBox::indicator:focus {{
    border: 1.5px solid {t.accent};
}}

/* Surfaces, Tables, Calendar, Boards, Focus */
QFrame#composerBox {{
    background: {t.bg_elevated};
    border: 1px solid {t.border_strong};
    border-radius: 14px;
}}
QFrame#calendarCell {{
    border: none;
    border-right: 1px solid {t.border_subtle};
    border-bottom: 1px solid {t.border_subtle};
    background: {t.bg_canvas};
}}
QTableWidget {{
    border: none;
    gridline-color: {t.border_subtle};
    background: {t.bg_canvas};
    selection-background-color: {t.accent_soft};
    selection-color: {t.ink_primary};
}}
QTableWidget::item {{
    padding: 7px;
    border: none;
}}
QHeaderView::section {{
    background: {t.bg_canvas};
    color: {t.ink_muted};
    border: none;
    border-bottom: 1px solid {t.border_subtle};
    padding: 9px;
    font-size: 12px;
}}
QFrame#dialogDivider {{
    background: {t.border_subtle};
    max-height: 1px;
    border: none;
}}
QFrame#boardList {{
    background: {t.bg_surface};
    border: 1px solid {t.border_subtle};
    border-radius: 14px;
}}
QLineEdit#listTitle {{
    background: transparent;
    border: none;
    padding: 5px 2px;
    font-weight: 600;
    color: {t.ink_primary};
}}
QLineEdit#listTitle:focus {{
    background: {t.bg_elevated};
    border: 1px solid {t.accent};
    border-radius: 6px;
}}
QListWidget#boardCards::item {{
    background: transparent;
    border: none;
}}
QFrame#focusContext {{
    background: {t.bg_surface};
    border: 1px solid {t.border_subtle};
    border-radius: 14px;
}}
QPushButton#focusTaskPicker {{
    background: transparent;
    border: none;
    color: {t.accent};
    padding: 5px 0;
    text-align: left;
}}
QPushButton#focusTaskPicker:hover {{
    color: {t.accent_hover};
}}
QPushButton#focusTaskPicker:disabled {{
    color: {t.ink_muted};
}}
QProgressBar {{
    background: {t.bg_surface_hover};
    border: none;
    border-radius: 3px;
    text-align: center;
    font-size: 10px;
}}
QProgressBar::chunk {{
    background: {t.ink_primary};
    border-radius: 3px;
}}

/* Title bar & Chrome */
QFrame#titleBar {{
    background: {t.bg_surface};
    border-bottom: 1px solid {t.border_subtle};
}}
QLineEdit#titleSearch {{
    background: {t.bg_elevated};
    border: 1px solid {t.border_subtle};
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 12px;
    color: {t.ink_primary};
}}
QLineEdit#titleSearch:hover {{
    border-color: {t.border_strong};
}}
QLineEdit#titleSearch:focus {{
    border-color: {t.accent};
}}
QPushButton#chromeButton, QToolButton#menuButton {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 4px 9px;
    font-size: 12px;
    color: {t.ink_secondary};
}}
QPushButton#chromeButton:hover, QPushButton#chromeButton[nativeHover="true"], QToolButton#menuButton:hover {{
    background: {t.bg_surface_hover};
    color: {t.ink_primary};
}}
QPushButton#chromeButton:pressed {{
    background: {t.bg_surface_active};
}}
QToolButton#menuButton::menu-indicator {{
    image: none;
}}
QPushButton#windowClose {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 4px;
}}
QPushButton#windowClose:hover {{
    background: {close_hover};
}}

/* Menus & Dialogs */
QDialog {{
    background: {t.bg_elevated};
}}
QDialogButtonBox {{
    background: transparent;
}}
QMenu {{
    background: {t.bg_elevated};
    color: {t.ink_primary};
    border: 1px solid {t.border_strong};
    border-radius: 11px;
    padding: 5px;
}}
QMenu::item {{
    border-radius: 7px;
    padding: 7px 14px;
}}
QMenu::item:selected {{
    background: {t.bg_surface_hover};
    color: {t.ink_primary};
}}
QMenu::item:disabled {{
    color: {t.ink_muted};
}}
QMenu::separator {{
    height: 1px;
    background: {t.border_subtle};
    margin: 5px 8px;
}}

/* Subtle Scrollbars */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 7px;
    margin: 2px 1px;
}}
QScrollBar::handle:vertical {{
    background: {t.scrollbar_handle};
    border-radius: 3.5px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t.scrollbar_hover};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 1px 2px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {t.scrollbar_handle};
    min-width: 32px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t.scrollbar_hover};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
    height: 0;
    background: transparent;
    border: none;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

QStatusBar {{
    background: {t.bg_canvas};
    color: {t.ink_muted};
    font-size: 11px;
}}
QToolTip {{
    background: {t.tooltip_bg};
    color: {t.tooltip_fg};
    border: 1px solid {t.tooltip_border};
    border-radius: 8px;
    padding: 6px 10px;
}}
QTabWidget::pane {{
    border: none;
}}
QTabBar::tab {{
    font-size: 12px;
    padding: 6px 12px;
    background: {t.bg_surface};
    border: none;
    border-radius: 8px;
}}
QTabBar::tab:selected {{
    background: {t.bg_surface_active};
    color: {t.ink_primary};
}}
"""
