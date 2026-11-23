"""Cached native blur surfaces; live text is never blurred or intercepted."""
from PySide6.QtCore import Qt, QTimer, QEvent, QPoint, QRect, QRectF, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QLinearGradient
from PySide6.QtWidgets import (QWidget, QGraphicsScene, QGraphicsPixmapItem,
                              QGraphicsBlurEffect)
from .theme import themed_color


def blurred_pixmap(source, radius=4):
    if source.isNull():
        return QPixmap()
    ratio = source.devicePixelRatio()
    width, height = source.width() / ratio, source.height() / ratio
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(source)
    scene.addItem(item)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.setSceneRect(QRectF(0, 0, width, height))
    result = QPixmap(source.size())
    result.setDevicePixelRatio(ratio)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    scene.render(painter, QRectF(0, 0, width, height), scene.sceneRect())
    painter.end()
    return result


class WorkspaceBackdrop(QWidget):
    def __init__(self, parent, source):
        super().__init__(parent)
        self.source = source
        self.soft = blurred_pixmap(source, 5)
        self.strength = 1.0
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_strength(self, value):
        self.strength = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.source)
        painter.setOpacity(self.strength)
        painter.drawPixmap(self.rect(), self.soft)
        painter.setOpacity(1)
        painter.fillRect(self.rect(), QColor(0, 0, 0, round(85 * self.strength)))


class ScrollEdgeLayer(QWidget):
    """A small frosted bottom lip over the scrolling Notes content."""
    def __init__(self, area):
        super().__init__(area.viewport())
        self.area, self.image = area, QPixmap()
        self.setObjectName('notesBottomLayer')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.refresh)
        area.viewport().installEventFilter(self)
        area.verticalScrollBar().valueChanged.connect(self.schedule)
        area.verticalScrollBar().rangeChanged.connect(self.schedule)
        self.schedule()

    def schedule(self, *args):
        viewport = self.area.viewport()
        height = min(28, viewport.height())
        self.setGeometry(0, viewport.height() - height, viewport.width(), height)
        if not self.timer.isActive():
            self.timer.start()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.schedule()
        return False

    def refresh(self):
        viewport, content = self.area.viewport(), self.area.widget()
        height = min(28, viewport.height())
        if height <= 0 or viewport.width() <= 0 or content is None:
            self.hide()
            return
        self.setGeometry(0, viewport.height() - height, viewport.width(), height)
        # Depth without taking screenshots or rendering blur during scrolling.
        self.image = QPixmap()
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.image)
        color = QColor(themed_color('#ffffff'))
        gradient = QLinearGradient(0, 0, 0, self.height())
        clear = QColor(color)
        clear.setAlpha(0)
        color.setAlpha(190)
        gradient.setColorAt(0, clear)
        gradient.setColorAt(1, color)
        painter.fillRect(self.rect(), gradient)
        line = QColor(themed_color('#dadce0'))
        line.setAlpha(75)
        painter.setPen(line)
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
