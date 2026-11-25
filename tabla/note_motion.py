"""High-refresh (60-120fps) spring-driven transitions between a gallery card and its note editor."""
from PySide6.QtCore import Qt, QRect, QRectF, QPoint
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen
from PySide6.QtWidgets import QWidget
from .theme import themed_color
from .tokens import current_tokens
from .spring import HighRefreshSpring, SILKY, SNAPPY


class NoteOpening(QWidget):
    """Fixed-geometry child/overlay canvas: animates via subpixel QPainter with zero HWND resizing."""
    def __init__(self, owner, origin, card_image, note_image, closing=False, presentation=None):
        host = owner.parentWidget()
        origin_rect = QRect(origin)
        target_rect = QRect(owner.geometry())
        close_start = QRect(presentation[0]) if presentation else QRect(target_rect)
        union_global = origin_rect.united(target_rect).united(close_start)
        host_global = QRect(host.mapToGlobal(QPoint()), host.size()) if host is not None else QRect()
        in_host = host is not None and host_global.isValid() and host_global.contains(union_global)

        if in_host:
            super().__init__(host)
            self._origin_global = host_global.topLeft()
            self.setGeometry(host.rect())
        else:
            super().__init__(
                owner,
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowDoesNotAcceptFocus
                | Qt.WindowType.WindowTransparentForInput,
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            bounds = union_global.adjusted(-28, -28, 28, 28)
            self._origin_global = bounds.topLeft()
            self.setGeometry(bounds)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setObjectName("noteOpeningSnapshot")
        self._in_host = in_host
        self.origin, self.target = origin_rect, target_rect
        self.card_image, self.note_image = card_image, note_image
        self.owner, self.closing = owner, closing
        self.close_start = close_start
        self.visual_start = presentation[1] if presentation else 1.0
        self.progress = 0.0
        self._current_global = QRectF(self.close_start if closing else self.origin)
        self._prev_dirty = QRect()
        self.animation = HighRefreshSpring(
            preset=SNAPPY if closing else SILKY,
            duration_ms=155 if closing else 205,
            parent=self,
        )
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(owner.finish_closing if closing else owner.finish_opening)
        if in_host:
            self.raise_()

    def current_global_rect(self) -> QRect:
        r = self._current_global
        return QRect(round(r.x()), round(r.y()), max(1, round(r.width())), max(1, round(r.height())))

    def _local_rect(self, r: QRectF) -> QRectF:
        ox, oy = self._origin_global.x(), self._origin_global.y()
        return QRectF(r.x() - ox, r.y() - oy, r.width(), r.height())

    def advance(self, value):
        self.progress = float(value)
        start, end = (self.close_start, self.origin) if self.closing else (self.origin, self.target)
        p = self.progress
        self._current_global = QRectF(
            start.x() + (end.x() - start.x()) * p,
            start.y() + (end.y() - start.y()) * p,
            max(1.0, start.width() + (end.width() - start.width()) * p),
            max(1.0, start.height() + (end.height() - start.height()) * p),
        )
        if self.owner._backdrop:
            strength = self.visual_start * (1.0 - max(0.0, min(1.0, p))) if self.closing else max(0.0, min(1.0, p))
            self.owner._backdrop.set_strength(strength)
        local_dirty = self._local_rect(self._current_global).toAlignedRect().adjusted(-20, -20, 20, 20)
        dirty = local_dirty.united(self._prev_dirty) if not self._prev_dirty.isNull() else local_dirty
        self._prev_dirty = local_dirty
        self.update(dirty)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clamped = max(0.0, min(1.0, self.progress))
        visual = self.visual_start * (1.0 - clamped) if self.closing else clamped
        overall = 1.0 - clamped if self.closing and self.card_image is None else 1.0
        local = self._local_rect(self._current_global)
        inset = 12.0 * visual
        surface_rect = local.adjusted(inset, inset, -inset, -inset)
        if surface_rect.width() <= 1 or surface_rect.height() <= 1:
            painter.end()
            return

        # Soft elevation shadow rings (zero blur cost)
        t = current_tokens()
        shadow_alpha = (32 if t.dark else 16) * overall * visual
        if shadow_alpha > 1.0:
            painter.setPen(Qt.PenStyle.NoPen)
            for expand, mult in ((10.0, 0.35), (5.0, 0.55), (2.0, 0.85)):
                c = QColor(0, 0, 0, max(0, min(255, round(shadow_alpha * mult))))
                painter.setBrush(c)
                painter.drawRoundedRect(surface_rect.adjusted(-expand, -expand + 2.0, expand, expand + 4.0), 14.0 + expand * 0.4, 14.0 + expand * 0.4)

        path = QPainterPath()
        path.addRoundedRect(surface_rect, 14.0, 14.0)
        painter.save()
        painter.setClipPath(path)
        painter.setOpacity(overall)
        painter.setPen(Qt.PenStyle.NoPen)
        surface = (
            self.owner.surface_background()
            if hasattr(self.owner, "surface_background")
            else themed_color("#ffffff")
        )
        painter.setBrush(QColor(surface))
        painter.drawRoundedRect(surface_rect, 14.0, 14.0)

        # Crossfade card preview -> native 1:1 DPI note snapshot inside the expanding clip
        card_opacity = max(0.0, 1.0 - visual / 0.24)
        note_opacity = min(1.0, max(0.0, (visual - 0.14) / 0.28)) if self.card_image is not None else 1.0
        if self.card_image and not self.card_image.isNull() and card_opacity > 0.0:
            painter.setOpacity(card_opacity * overall)
            painter.drawPixmap(local, self.card_image, QRectF(self.card_image.rect()))
        if self.note_image and not self.note_image.isNull() and note_opacity > 0.0:
            painter.setOpacity(note_opacity * overall)
            dpr = self.note_image.devicePixelRatio() or 1.0
            nat_w = self.note_image.width() / dpr
            nat_h = self.note_image.height() / dpr
            painter.drawPixmap(QRectF(local.x(), local.y(), nat_w, nat_h), self.note_image, QRectF(self.note_image.rect()))
        painter.restore()

        # Subtle crisp perimeter hairline matching FloatingSurface
        painter.setOpacity(overall)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(t.border_subtle), 1.0))
        painter.drawRoundedRect(surface_rect, 14.0, 14.0)
        painter.end()
