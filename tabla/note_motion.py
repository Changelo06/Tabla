"""Input-transparent spring-driven transitions between a gallery card and its note editor."""
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QColor
from PySide6.QtWidgets import QWidget
from .theme import themed_color
from .spring import SpringAnimation, SILKY, SNAPPY


class NoteOpening(QWidget):
    def __init__(self, owner, origin, card_image, note_image, closing=False, presentation=None):
        super().__init__(
            owner,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("noteOpeningSnapshot")
        self.origin, self.target = QRect(origin), QRect(owner.geometry())
        self.card_image, self.note_image = card_image, note_image
        self.owner, self.closing = owner, closing
        self.close_start = QRect(presentation[0]) if presentation else QRect(self.target)
        self.visual_start = presentation[1] if presentation else 1.0
        self.progress = 0.0
        self.animation = SpringAnimation(
            preset=SNAPPY if closing else SILKY,
            duration_ms=165 if closing else 220,
            parent=self,
        )
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(owner.finish_closing if closing else owner.finish_opening)
        self.setGeometry(self.close_start if closing else self.origin)

    def advance(self, value):
        self.progress = float(value)
        start, end = (self.close_start, self.origin) if self.closing else (self.origin, self.target)
        p = self.progress
        self.setGeometry(
            QRect(
                round(start.x() + (end.x() - start.x()) * p),
                round(start.y() + (end.y() - start.y()) * p),
                max(1, round(start.width() + (end.width() - start.width()) * p)),
                max(1, round(start.height() + (end.height() - start.height()) * p)),
            )
        )
        self.update()
        if self.owner._backdrop:
            strength = self.visual_start * (1.0 - max(0.0, min(1.0, p))) if self.closing else max(0.0, min(1.0, p))
            self.owner._backdrop.set_strength(strength)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clamped = max(0.0, min(1.0, self.progress))
        visual = self.visual_start * (1.0 - clamped) if self.closing else clamped
        overall = 1.0 - clamped if self.closing and self.card_image is None else 1.0
        inset = 12.0 * visual
        surface_rect = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        path = QPainterPath()
        path.addRoundedRect(surface_rect, 14, 14)
        painter.setClipPath(path)
        painter.setOpacity(overall)
        painter.setPen(Qt.PenStyle.NoPen)
        surface = (
            self.owner.surface_background()
            if hasattr(self.owner, "surface_background")
            else themed_color("#ffffff")
        )
        painter.setBrush(QColor(surface))
        painter.drawRoundedRect(surface_rect, 14, 14)
        # Separate text fades and clip-reveal note text at native 1:1 DPI (zero text squashing)
        card_opacity = max(0.0, 1.0 - visual / 0.22)
        note_opacity = min(1.0, max(0.0, (visual - 0.16) / 0.28)) if self.card_image is not None else 1.0
        if self.card_image and not self.card_image.isNull() and card_opacity > 0.0:
            painter.setOpacity(card_opacity * overall)
            painter.drawPixmap(QRectF(self.rect()), self.card_image, QRectF(self.card_image.rect()))
        if self.note_image and not self.note_image.isNull() and note_opacity > 0.0:
            painter.setOpacity(note_opacity * overall)
            dpr = self.note_image.devicePixelRatio() or 1.0
            nat_w = self.note_image.width() / dpr
            nat_h = self.note_image.height() / dpr
            # Draw at native logical size anchored to top-left so glyphs stay crisp inside the expanding clip
            painter.drawPixmap(QRectF(0, 0, nat_w, nat_h), self.note_image, QRectF(self.note_image.rect()))
