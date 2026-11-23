"""Input-transparent transitions between a gallery card and its note editor."""
from PySide6.QtCore import Qt, QVariantAnimation, QEasingCurve, QRect, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QColor
from PySide6.QtWidgets import QWidget
from .theme import themed_color


class NoteOpening(QWidget):
    def __init__(self, owner, origin, card_image, note_image, closing=False, presentation=None):
        super().__init__(owner, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName('noteOpeningSnapshot')
        self.origin, self.target = QRect(origin), QRect(owner.geometry())
        self.card_image, self.note_image = card_image, note_image
        self.owner, self.closing = owner, closing
        self.close_start = QRect(presentation[0]) if presentation else QRect(self.target)
        self.visual_start = presentation[1] if presentation else 1.0
        self.progress = 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(150 if closing else 180)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(owner.finish_closing if closing else owner.finish_opening)
        self.setGeometry(self.close_start if closing else self.origin)

    def advance(self, value):
        self.progress = float(value)
        start, end = (self.close_start, self.origin) if self.closing else (self.origin, self.target)
        p = self.progress
        self.setGeometry(QRect(round(start.x() + (end.x() - start.x()) * p),
            round(start.y() + (end.y() - start.y()) * p),
            max(1, round(start.width() + (end.width() - start.width()) * p)),
            max(1, round(start.height() + (end.height() - start.height()) * p))))
        self.update()
        if self.owner._backdrop:
            self.owner._backdrop.set_strength(self.visual_start * (1 - p) if self.closing else p)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 10, 10)
        painter.setClipPath(path)
        visual = self.visual_start * (1 - self.progress) if self.closing else self.progress
        overall = 1 - self.progress if self.closing and self.card_image is None else 1.0
        inset = 12 * visual
        painter.setOpacity(overall)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(themed_color('#ffffff')))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(inset, inset, -inset, -inset), 10, 10)
        # Separate the text fades so a card's preview never overlaps the full
        # note's differently sized text during the expansion.
        card_opacity = max(0.0, 1 - visual / .18)
        note_opacity = min(1.0, max(0.0, (visual - .18) / .25)) if self.card_image is not None else 1.0
        if self.card_image and not self.card_image.isNull() and card_opacity:
            painter.setOpacity(card_opacity * overall)
            painter.drawPixmap(self.rect(), self.card_image)
        painter.setOpacity(note_opacity * overall)
        painter.drawPixmap(self.rect(), self.note_image)
