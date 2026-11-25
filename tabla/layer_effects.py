"""Cached native blur surfaces and lightweight viewport edge depth."""
from PySide6.QtCore import Qt, QEvent, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QLinearGradient
from PySide6.QtWidgets import (
    QWidget,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsBlurEffect,
)
from .tokens import current_tokens


def _render_blur(source: QPixmap, radius: float) -> QPixmap:
    ratio = source.devicePixelRatio() or 1.0
    width, height = source.width() / ratio, source.height() / ratio
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(source)
    scene.addItem(item)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.PerformanceHint)
    item.setGraphicsEffect(effect)
    scene.setSceneRect(QRectF(0, 0, width, height))
    result = QPixmap(source.size())
    result.setDevicePixelRatio(ratio)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    scene.render(painter, QRectF(0, 0, width, height), scene.sceneRect())
    painter.end()
    return result


def blurred_pixmap(source, radius=4):
    if source.isNull():
        return QPixmap()
    # Downscale large surfaces (e.g. full-window modal backdrops) 4x before blur:
    # 1/16th the pixel count (~14x faster on CPU) with indistinguishable softness.
    if max(source.width(), source.height()) > 240:
        ratio = source.devicePixelRatio() or 1.0
        small = source.scaled(
            max(1, source.width() // 4),
            max(1, source.height() // 4),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        small.setDevicePixelRatio(1.0)
        soft = _render_blur(small, max(1.2, radius * 0.45))
        upscaled = soft.scaled(
            source.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        upscaled.setDevicePixelRatio(ratio)
        return upscaled
    return _render_blur(source, radius)


class WorkspaceBackdrop(QWidget):
    def __init__(self, parent, source):
        super().__init__(parent)
        self.source = source
        self.soft = blurred_pixmap(source, 5)
        self.strength = 1.0
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def set_strength(self, value):
        self.strength = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.source)
        painter.setOpacity(self.strength)
        painter.drawPixmap(self.rect(), self.soft)
        painter.setOpacity(1.0)
        dim_alpha = 115 if current_tokens().dark else 78
        painter.fillRect(self.rect(), QColor(0, 0, 0, round(dim_alpha * self.strength)))


class ScrollEdgeLayer(QWidget):
    """A zero-allocation progressive bottom scrim over scrolling Notes content."""
    def __init__(self, area):
        super().__init__(area.viewport())
        self.area = area
        self.image = QPixmap()
        self.setObjectName("notesBottomLayer")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        area.viewport().installEventFilter(self)
        area.verticalScrollBar().rangeChanged.connect(self._sync_bounds)
        self._sync_bounds()

    def _sync_bounds(self, *args):
        viewport = self.area.viewport()
        height = min(28, viewport.height())
        if height <= 0 or viewport.width() <= 0 or self.area.widget() is None:
            self.hide()
            return
        self.setGeometry(0, viewport.height() - height, viewport.width(), height)
        self.show()
        self.raise_()

    def schedule(self, *args):
        self._sync_bounds()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self._sync_bounds()
        return False

    def paintEvent(self, event):
        t = current_tokens()
        painter = QPainter(self)
        base = QColor(t.bg_canvas)
        gradient = QLinearGradient(0, 0, 0, self.height())
        c0 = QColor(base); c0.setAlpha(0)
        c1 = QColor(base); c1.setAlpha(120)
        c2 = QColor(base); c2.setAlpha(230)
        gradient.setColorAt(0.0, c0)
        gradient.setColorAt(0.55, c1)
        gradient.setColorAt(1.0, c2)
        painter.fillRect(self.rect(), gradient)
        line = QColor(t.border_subtle)
        line.setAlpha(90)
        painter.setPen(line)
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
