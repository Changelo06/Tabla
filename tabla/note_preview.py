"""A hard visual line limit, including wrapped words, without modifying note text."""
from PySide6.QtCore import Qt, QSize, QPointF
from PySide6.QtGui import QPainter, QTextLayout, QTextOption, QFont
from PySide6.QtWidgets import QWidget, QSizePolicy
from .theme import themed_color


class NotePreview(QWidget):
    def __init__(self, text, lines=6, characters=240, title=False):
        super().__init__()
        self.text = text[:characters] + ('…' if len(text) > characters else '')
        self.line_limit = lines
        self.title = title
        from .tokens import ui_font
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFont(ui_font(14 if title else 13, QFont.Weight.DemiBold if title else QFont.Weight.Normal))
        self.setAccessibleName(self.text)

    def hasHeightForWidth(self):
        return True

    def layout_text(self, width):
        key = (width, self.text, self.line_limit, self.font().toString())
        if getattr(self, '_layout_key', None) == key:
            return self._layout_cache
        layout = QTextLayout(self.text.replace('\n', '\u2028'), self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        y = 0
        for i in range(self.line_limit):
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(max(10, width))
            line.setPosition(QPointF(0, y))
            y += line.height() + 3
        layout.endLayout()
        self._layout_key = key
        self._layout_cache = (layout, max(self.fontMetrics().height(), int(y)))
        return self._layout_cache

    def heightForWidth(self, width):
        return self.layout_text(width)[1]

    def sizeHint(self):
        return QSize(230, self.heightForWidth(max(80, self.width())))

    def paintEvent(self, event):
        from .tokens import current_tokens
        t = current_tokens()
        layout, _ = self.layout_text(self.width())
        painter = QPainter(self)
        painter.setPen(t.ink_primary if self.title else t.ink_secondary)
        painter.setFont(self.font())
        for index in range(layout.lineCount()):
            line = layout.lineAt(index)
            if index == self.line_limit - 1 and line.textStart() + line.textLength() < len(self.text):
                tail = self.text[line.textStart():].replace('\n', ' ').replace('\u2028', ' ')
                painter.drawText(0, int(line.y() + line.ascent()), self.fontMetrics().elidedText(tail, Qt.TextElideMode.ElideRight, self.width()))
            else:
                line.draw(painter, QPointF())
