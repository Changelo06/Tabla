from __future__ import annotations

import math
from PySide6.QtCore import Qt, Signal, QRectF, QSize, QStringListModel
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
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
    result = ElidedButton(text) if elide else QPushButton(text)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    if name:
        result.setObjectName(name)
    if glyph:
        result.setIcon(icon(glyph, "#ffffff" if name == "primary" else "#69645f"))
        result.setIconSize(QSize(19, 19))
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


class PinButton(QPushButton):
    """A Keep-style pin toggle, with visible and accessible state."""
    def __init__(self, checked=False):
        super().__init__()
        self.setObjectName('notePin')
        self.setCheckable(True)
        self.setFixedSize(30, 30)
        self.setIconSize(QSize(22, 22))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet('QPushButton#notePin {border:none;background:transparent;padding:4px;border-radius:15px;}'
                           'QPushButton#notePin:hover {background:#eeeeec;}'
                           'QPushButton#notePin:checked {background:#e6f3fe;}'
                           'QPushButton#notePin:focus {border:1px solid #2383e2;}')
        self.toggled.connect(self.update_pin)
        self.setChecked(checked)
        self.update_pin(checked)

    def update_pin(self, checked):
        action = 'Unpin' if checked else 'Pin'
        self.setToolTip(action)
        self.setAccessibleName(action)
        self.setIcon(icon('pin-filled' if checked else 'pin', '#2383e2' if checked else '#73726d', 20))


def panel(name="card", padding=20):
    result = QFrame()
    result.setObjectName(name)
    layout = QVBoxLayout(result)
    layout.setContentsMargins(padding, padding, padding, padding)
    layout.setSpacing(14)
    return result, layout


def scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    return area


class ClickCard(QFrame):
    clicked = Signal()

    def __init__(self, color="gray", parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_color(color)

    def set_color(self, color):
        bg, _ = COLORS.get(color, COLORS["gray"])
        self.setStyleSheet(f"ClickCard {{ background: {bg}; border: 1px solid transparent; border-radius: 12px; }} ClickCard:hover {{ border-color: #b9d6fc; }} ClickCard:focus {{ border: 2px solid #3388ff; }}")

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
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width() - 18, self.height() - 18)
        rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        p.setPen(QPen(QColor("#e8e6e2"), 4))
        p.drawEllipse(rect)
        remaining = self.timer.remaining()
        progress = 1 - remaining / max(1, self.timer.data["duration"])
        p.setPen(QPen(QColor("#006bc7"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        if progress > 0:
            p.drawArc(rect, 90 * 16, -int(progress * 360 * 16))
        seconds = int(math.ceil(remaining))
        text = f"{seconds // 60:02}:{seconds % 60:02}"
        p.setPen(QColor("#242321"))
        p.setFont(QFont("Alegreya Sans", 29 if self.compact else 48, QFont.Weight.Black))
        p.drawText(rect.adjusted(0, -8, 0, -8), Qt.AlignmentFlag.AlignCenter, text)
        p.setFont(QFont("Alegreya Sans", 12 if self.compact else 14))
        p.setPen(QColor("#69645f"))
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
            items = [r for r in self.store.records(state="all") if r["kind"] in ("note", "task", "project", "event", "block")]
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
