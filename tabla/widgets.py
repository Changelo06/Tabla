from __future__ import annotations

import math
from PySide6.QtCore import Qt, Signal, QRectF, QSize, QStringListModel
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QAbstractButton, QVBoxLayout, QHBoxLayout,
    QScrollArea, QPlainTextEdit, QCompleter, QSizePolicy,
)
from .theme import icon, COLORS


def clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            clear(item.layout())


def label(text, name=None, wrap=False):
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(wrap)
    if name:
        result.setObjectName(name)
    return result


class ElidedButton(QPushButton):
    """Keep a full accessible title while fitting calendar entries to their cells."""
    def __init__(self, text):
        super().__init__(text)
        self.full_text = text
        self.setAccessibleName(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideRight, max(1, self.width() - 10)))


def button(text="", callback=None, name=None, glyph=None, elide=False):
    from .tokens import current_tokens
    result = ElidedButton(text) if elide else QPushButton(text)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    if name:
        result.setObjectName(name)
    if glyph:
        t = current_tokens()
        px = 16 if text else 18
        result.setIcon(icon(glyph, t.ink_inverse if name == "primary" else t.ink_secondary, size=px, preserve_color=(name == "primary")))
        result.setIconSize(QSize(px, px))
    if callback:
        result.clicked.connect(callback)
    return result


def row(*widgets, spacing=10):
    result = QHBoxLayout()
    result.setSpacing(spacing)
    for widget in widgets:
        if widget is None:
            result.addStretch()
        elif isinstance(widget, QWidget):
            result.addWidget(widget)
        else:
            result.addLayout(widget)
    return result


class StripeDivider(QWidget):
    """Dashcon signature delicate diagonal pinstripe hairline."""
    def __init__(self, parent=None, height=4):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        from .tokens import current_tokens
        t = current_tokens()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(t.bg_canvas))
        stripe = QColor(255, 255, 255, 18) if t.dark else QColor(22, 22, 23, 18)
        p.setPen(QPen(stripe, 1.5))
        h = self.height()
        for x in range(-h, self.width() + h, 8):
            p.drawLine(x, h, x + h, 0)
        p.setPen(QPen(QColor(t.border_subtle), 1))
        p.drawLine(0, h - 1, self.width(), h - 1)
        p.end()


class SegmentedSwitch(QFrame):
    """Unified Dashcon-style rounded pill track for mutually exclusive view modes."""
    def __init__(self, items, active_key, callback, parent=None):
        super().__init__(parent)
        self.setObjectName("segmentedTrack")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.buttons = {}
        for key, text, glyph in items:
            btn = button(text, lambda checked=False, k=key: callback(k), "tab", glyph)
            btn.setProperty("active", key == active_key)
            layout.addWidget(btn)
            self.buttons[key] = btn


class PinButton(QPushButton):
    """A quiet Dashcon-refined pin toggle, with visible and accessible state."""
    def __init__(self, checked=False):
        super().__init__()
        self.setObjectName('notePin')
        self.setCheckable(True)
        self.setFixedSize(30, 30)
        self.setIconSize(QSize(19, 19))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()
        self.toggled.connect(self.update_pin)
        self.clicked.connect(lambda: __import__('tabla.foley', fromlist=['play']).play('pop'))
        self.setChecked(checked)
        self.update_pin(checked)

    def _apply_style(self):
        from .tokens import current_tokens
        t = current_tokens()
        checked_bg = "rgba(245, 245, 247, 0.14)" if t.dark else "rgba(22, 22, 23, 0.08)"
        hover_bg = "rgba(245, 245, 247, 0.10)" if t.dark else "rgba(22, 22, 23, 0.05)"
        self.setProperty('tablaThemed', True)
        self.setStyleSheet(
            f'QPushButton#notePin {{border:none;background:transparent;padding:4px;border-radius:15px;}}'
            f'QPushButton#notePin:hover {{background:{hover_bg};}}'
            f'QPushButton#notePin:checked {{background:{checked_bg};}}'
            f'QPushButton#notePin:focus {{border:1px solid {t.accent};}}'
        )

    def update_pin(self, checked):
        from .tokens import current_tokens
        t = current_tokens()
        self._apply_style()
        action = 'Unpin' if checked else 'Pin'
        self.setToolTip(action)
        self.setAccessibleName(action)
        self.setIcon(icon('pin-filled' if checked else 'pin', t.ink_primary if checked else t.ink_muted, 19, preserve_color=True))


def panel(name="card", padding=20):
    result = QFrame()
    result.setObjectName(name)
    layout = QVBoxLayout(result)
    layout.setContentsMargins(padding, padding, padding, padding)
    layout.setSpacing(14)
    return result, layout


def scroll(widget):
    from .spring import SmoothWheelFilter
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    area._smooth_wheel = SmoothWheelFilter(area)
    return area


class ClickCard(QFrame):
    clicked = Signal()

    def __init__(self, color="gray", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_color(color)

    def set_color(self, color):
        from .tokens import current_tokens
        t = current_tokens()
        bg, _ = COLORS.get(color, COLORS["gray"])
        self.setStyleSheet(
            f"ClickCard {{ background: {bg}; border: 1px solid {t.border_subtle}; border-radius: 14px; }} "
            f"ClickCard:hover {{ border-color: {t.border_strong}; }} "
            f"ClickCard:focus {{ border: 1px solid {t.accent}; }}"
        )

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)


class NoteCard(ClickCard):
    """Reserved action space, revealed on hover or keyboard focus without reflow."""
    def setup_controls(self, actions, pin):
        from PySide6.QtCore import QTimer
        self.setProperty('notesSurface', True)
        self._quiet_actions, self._quiet_pin = actions, pin
        self._controls_update = QTimer(self)
        self._controls_update.setSingleShot(True)
        self._controls_update.timeout.connect(self.update_controls)
        for widget in (actions, pin):
            policy = widget.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            widget.setSizePolicy(policy)
        for widget in [self] + self.findChildren(QWidget):
            widget.installEventFilter(self)
        pin.toggled.connect(self.update_controls)
        self.update_controls()

    def update_controls(self, *args):
        from PySide6.QtWidgets import QApplication
        focus = self.window().focusWidget()
        active = self.underMouse() or focus is self or (focus is not None and self.isAncestorOf(focus))
        self._quiet_actions.setVisible(active)
        self._quiet_pin.setVisible(active or self._quiet_pin.isChecked())

    def eventFilter(self, watched, event):
        from PySide6.QtCore import QEvent, QTimer
        if event.type() in (QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self._controls_update.start(0)
        return super().eventFilter(watched, event)


class ThemePresetCard(QAbstractButton):
    """Visual theme preset card with a live miniature Tabla window preview."""
    def __init__(self, preset, active=False, callback=None, parent=None):
        super().__init__(parent)
        self.preset = preset
        self.active = bool(active)
        self.setProperty("tablaThemed", True)
        self.setProperty("themeKey", preset.key)
        self.setCheckable(True)
        self.setChecked(self.active)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(114)
        self.setMinimumWidth(148)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(f"{preset.label} theme: {preset.tagline}")
        self.setToolTip(f"{preset.label} — {preset.tagline}")
        if callback is not None:
            self.clicked.connect(lambda checked=False, k=preset.key: callback(k))

    def sizeHint(self):
        return QSize(172, 114)

    def minimumSizeHint(self):
        return QSize(148, 114)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainterPath
        from .tokens import current_tokens, ui_font
        t = current_tokens()
        p_tok = self.preset
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        hovered = self.underMouse()

        # Card container
        bg = QColor(t.bg_surface_hover if hovered and not self.active else t.bg_elevated)
        painter.setBrush(bg)
        if self.active:
            painter.setPen(QPen(QColor(t.accent), 2.0))
        else:
            painter.setPen(QPen(QColor(t.border_strong if hovered else t.border_subtle), 1.0))
        painter.drawRoundedRect(outer, 12, 12)

        # Miniature window preview box
        preview = QRectF(outer.left() + 9, outer.top() + 9, outer.width() - 18, 56)
        clip = QPainterPath()
        clip.addRoundedRect(preview, 7, 7)
        painter.save()
        painter.setClipPath(clip)
        painter.fillRect(preview, QColor(p_tok.bg_canvas))
        # Top mini chrome strip
        chrome = QRectF(preview.left(), preview.top(), preview.width(), 11)
        painter.fillRect(chrome, QColor(p_tok.bg_surface))
        # Left mini sidebar rail
        rail = QRectF(preview.left(), preview.top() + 11, 17, preview.height() - 11)
        painter.fillRect(rail, QColor(p_tok.bg_surface))
        painter.setPen(QPen(QColor(p_tok.border_subtle), 1))
        painter.drawLine(QRectF(preview.left(), preview.top() + 11, preview.width(), 0).topLeft(),
                         QRectF(preview.left(), preview.top() + 11, preview.width(), 0).topRight())
        painter.drawLine(rail.topRight(), rail.bottomRight())
        # Sidebar mini dots
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            painter.setBrush(QColor(p_tok.ink_primary if i == 0 else p_tok.ink_muted))
            painter.drawRoundedRect(QRectF(rail.left() + 5.5, rail.top() + 7 + i * 10, 6, 4), 2, 2)
        # Mini elevated card on canvas
        card_r = QRectF(rail.right() + 7, chrome.bottom() + 7, preview.width() - 31, preview.height() - 25)
        painter.setBrush(QColor(p_tok.bg_elevated))
        painter.setPen(QPen(QColor(p_tok.border_subtle), 1))
        painter.drawRoundedRect(card_r, 4, 4)
        # Mini ink lines & CTA pill
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(p_tok.ink_primary))
        painter.drawRoundedRect(QRectF(card_r.left() + 6, card_r.top() + 6, card_r.width() * 0.45, 4), 2, 2)
        painter.setBrush(QColor(p_tok.ink_muted))
        painter.drawRoundedRect(QRectF(card_r.left() + 6, card_r.top() + 14, card_r.width() * 0.65, 3), 1.5, 1.5)
        # Accent + monochrome pill indicators
        painter.setBrush(QColor(p_tok.bg_pill))
        painter.drawRoundedRect(QRectF(card_r.right() - 22, card_r.top() + 5, 16, 6), 3, 3)
        painter.setBrush(QColor(p_tok.accent))
        painter.drawEllipse(QRectF(card_r.right() - 12, card_r.bottom() - 10, 6, 6))
        painter.restore()

        # Preview border
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(p_tok.border_strong if p_tok.dark != t.dark else p_tok.border_subtle), 1.0))
        painter.drawRoundedRect(preview, 7, 7)

        # Label + tagline
        text_left = outer.left() + 11
        text_right = outer.right() - 11
        name_rect = QRectF(text_left, preview.bottom() + 7, text_right - text_left - 18, 18)
        painter.setFont(ui_font(12, QFont.Weight.DemiBold))
        painter.setPen(QColor(t.ink_primary))
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, p_tok.label)

        # Active check badge
        if self.active:
            badge = QRectF(text_right - 14, preview.bottom() + 9, 14, 14)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t.accent))
            painter.drawEllipse(badge)
            painter.setPen(QPen(QColor("#ffffff"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(badge.left() + 3.8, badge.top() + 7.2, badge.left() + 6.1, badge.top() + 9.5)
            painter.drawLine(badge.left() + 6.1, badge.top() + 9.5, badge.left() + 10.3, badge.top() + 4.8)

        tag_rect = QRectF(text_left, name_rect.bottom() + 1, text_right - text_left, 15)
        painter.setFont(ui_font(11))
        painter.setPen(QColor(t.ink_muted))
        painter.drawText(tag_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, p_tok.tagline)
        painter.end()


class CountdownDisplay(QWidget):
    """QSS-immune display numeral widget using OpenType tabular figures and centered colon."""
    def __init__(self, text="25:00", px=92, parent=None):
        super().__init__(parent)
        self._text = str(text)
        self._px = int(px)
        self.setProperty("tablaThemed", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._px + 42)
        self.setAccessibleName("Focus countdown")

    def text(self):
        return self._text

    def setText(self, value):
        value = str(value)
        if value != self._text:
            self._text = value
            self.update()

    def paintEvent(self, event):
        from .tokens import current_tokens, display_numeral_font
        t = current_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(QColor(t.ink_primary))
        p.setFont(display_numeral_font(self._px, QFont.Weight.DemiBold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)
        p.end()


class TimerRing(QWidget):
    def __init__(self, timer, compact=False):
        super().__init__()
        self.timer = timer
        self.compact = compact
        self.setMinimumSize(140 if compact else 260, 140 if compact else 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(145 if compact else 290)
        self.setAccessibleName("Focus timer")

    def paintEvent(self, event):
        from .tokens import current_tokens, display_numeral_font, ui_font
        t = current_tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width() - 18, self.height() - 18)
        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        p.setPen(QPen(QColor(t.border_subtle), 4))
        p.drawEllipse(rect)
        remaining = self.timer.remaining()
        progress = 1 - remaining / max(1, self.timer.data["duration"])
        p.setPen(QPen(QColor(t.accent), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if progress > 0:
            p.drawArc(rect, 90 * 16, -int(progress * 360 * 16))
        seconds = int(math.ceil(remaining))
        text = f"{seconds // 60:02}:{seconds % 60:02}"
        p.setPen(QColor(t.ink_primary))
        p.setFont(display_numeral_font(30 if self.compact else 52))
        p.drawText(rect.adjusted(0, -8, 0, -8), Qt.AlignmentFlag.AlignCenter, text)
        p.setFont(ui_font(12 if self.compact else 14))
        p.setPen(QColor(t.ink_secondary))
        p.drawText(rect.adjusted(0, 62 if self.compact else 90, 0, 0), Qt.AlignmentFlag.AlignCenter, self.timer.data["mode"])
        p.end()


class LinkEditor(QPlainTextEdit):
    """A native text editor with explicit title completions for [[references]]."""
    linkActivated = Signal(str)
    filesDropped = Signal(list)
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.setObjectName("noteEditor")
        from .surfaces import MarkdownHighlighter
        self.highlighter = MarkdownHighlighter(self.document())
        self.setPlaceholderText("Start writing...\n\nType [[ to link a note, task, or project.\nUse - [ ] for a checklist item.")
        self.completer = QCompleter(self)
        self.model = QStringListModel(self.completer)
        self.completer.setModel(self.model)
        self.link_targets = {}
        self.candidates = {}
        self.completer.setWidget(self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.activated.connect(self.insert_link)
        self._start = None

    def insert_link(self, title):
        cursor = self.textCursor()
        if self._start is None:
            return
        end = cursor.position()
        cursor.setPosition(self._start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        record = self.candidates.get(title)
        text = record["title"] if record else title
        if record:
            self.link_targets[text] = record["id"]
        cursor.insertText(text + "]] ")
        self.setTextCursor(cursor)
        self.completer.popup().hide()

    def keyPressEvent(self, event):
        if self.completer.popup().isVisible() and event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Tab):
            event.ignore()
            return
        super().keyPressEvent(event)
        cursor = self.textCursor()
        before = self.toPlainText()[:cursor.position()]
        start = before.rfind("[[")
        text = before[start + 2:] if start >= 0 else ""
        if start >= 0 and "]" not in text and "\n" not in text and len(text) <= 80:
            self._start = start + 2
            items = self.store.link_candidates(text, kinds=("note", "task", "project", "event", "block"))
            self.candidates = {f'{r["title"]} · {r["kind"]} · {r["id"][:6]}': r for r in items}
            self.model.setStringList(sorted(self.candidates))
            self.completer.setCompletionPrefix(text)
            if self.completer.completionCount():
                rect = self.cursorRect()
                rect.setWidth(320)
                self.completer.complete(rect)
            else:
                self.completer.popup().hide()
        else:
            self.completer.popup().hide()

    def mouseReleaseEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            import re
            cursor = self.cursorForPosition(event.position().toPoint())
            position = cursor.positionInBlock()
            for match in re.finditer(r'\[\[([^\]]+)\]\]', cursor.block().text()):
                if match.start() <= position <= match.end():
                    self.linkActivated.emit(match[1])
                    return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.filesDropped.emit([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
