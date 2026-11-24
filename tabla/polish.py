"""Small native interaction details: color swatches, tooltips and optional motion."""
from PySide6.QtCore import (Qt, QObject, QEvent, QTimer, Signal, QPoint, QSize,
                            QPropertyAnimation, QVariantAnimation, QEasingCurve, QRectF)
from PySide6.QtGui import QColor, QPainter, QPen, QCursor
from PySide6.QtWidgets import (QApplication, QWidget, QFrame, QLabel, QHBoxLayout,
    QVBoxLayout, QPushButton, QAbstractButton, QGraphicsOpacityEffect, QGraphicsDropShadowEffect,
    QMenu, QWidgetAction, QStyle, QProxyStyle)
from .theme import COLORS, themed_color, polish_surfaces


def motion_enabled():
    app = QApplication.instance()
    return bool(app and not app.property('reduceMotion') and app.platformName() != 'offscreen')


def fade_in(widget, duration=150):
    if not motion_enabled():
        return
    effect = widget.graphicsEffect()
    if effect and not isinstance(effect, QGraphicsOpacityEffect):
        return
    if effect is None:
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    previous = getattr(widget, '_fade', None)
    if previous:
        previous.stop()
    animation = QPropertyAnimation(effect, b'opacity', widget)
    animation.setDuration(duration)
    animation.setStartValue(.84 if effect.opacity() >= .99 else effect.opacity())
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    def cleanup():
        if getattr(widget, '_fade', None) is animation and widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)
    animation.finished.connect(cleanup)
    widget._fade = animation
    animation.start()


def fade_window(widget, duration=150):
    """Fade a native translucent window without an offscreen widget surface."""
    previous = getattr(widget, '_fade', None)
    if previous:
        previous.stop()
    if not motion_enabled():
        widget.setWindowOpacity(1.0)
        return
    animation = QPropertyAnimation(widget, b'windowOpacity', widget)
    animation.setDuration(duration)
    animation.setStartValue(.84)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._fade = animation
    animation.start()


def set_reduced_motion(reduced):
    app = QApplication.instance()
    app.setProperty('reduceMotion', bool(reduced))
    if reduced:
        for window in app.topLevelWidgets():
            finish_motion = getattr(window, 'finish_motion', None)
            if callable(finish_motion):
                finish_motion()
        for widget in app.allWidgets():
            for name in ('_fade', '_hover_motion', '_height_motion', '_swoop'):
                animation = getattr(widget, name, None)
                if animation:
                    animation.stop()
                    if name == '_swoop':
                        widget.move(animation.endValue())
            effect = widget.graphicsEffect()
            if isinstance(effect, QGraphicsOpacityEffect):
                effect.setOpacity(1.0)
            if widget.isWindow() and widget.windowOpacity() < 1.0:
                widget.setWindowOpacity(1.0)
            if hasattr(widget, '_height_target'):
                widget.setFixedHeight(widget._height_target)
            base = widget.property('motionIconSize')
            if base and isinstance(widget, QPushButton):
                widget.setIconSize(QSize(base, base))


def animate_height(widget, target):
    if getattr(widget, '_height_target', None) == target:
        return
    widget._height_target = target
    previous = getattr(widget, '_height_motion', None)
    if previous:
        previous.stop()
    if not motion_enabled():
        widget.setFixedHeight(target)
        return
    current = widget.height()
    widget.setMinimumHeight(0)
    widget.setMaximumHeight(current)
    animation = QPropertyAnimation(widget, b'maximumHeight', widget)
    animation.setStartValue(current)
    animation.setEndValue(target)
    animation.setDuration(170)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.finished.connect(lambda: widget.setFixedHeight(target))
    widget._height_motion = animation
    animation.start()


class Swatch(QAbstractButton):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = color
        self.setCheckable(True)
        self.setFixedSize(34, 34)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('Clear highlight' if color == 'None' else 'Default' if color == 'gray' else color.capitalize())
        self.setAccessibleName(self.toolTip())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = themed_color('#dadce0') if self.color == 'None' else '#b9b9b4' if self.color == 'gray' else COLORS[self.color][1]
        p.setBrush(QColor(accent))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(5, 5, 24, 24))
        if self.color == 'None':
            p.setPen(QPen(QColor(themed_color('#696864')), 1.5))
            p.drawLine(10, 24, 24, 10)
        if self.isChecked():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(themed_color('#37352f')), 1.5))
            p.drawEllipse(QRectF(1.5, 1.5, 31, 31))
            if self.color != 'None':
                p.setPen(QPen(QColor('white'), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawLine(11, 17, 15, 21)
                p.drawLine(15, 21, 23, 12)
        elif self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor('#2383e2'), 1.5))
            p.drawEllipse(QRectF(1.5, 1.5, 31, 31))
        p.end()


class ColorPicker(QWidget):
    currentTextChanged = Signal(str)
    currentIndexChanged = Signal(int)
    def __init__(self, current='blue', parent=None, values=None):
        super().__init__(parent)
        self.value = current
        self.values = list(values or ['blue', 'green', 'yellow', 'violet', 'rose', 'gray'])
        self.swatches = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for color in self.values:
            swatch = Swatch(color)
            swatch.setChecked(color == current)
            swatch.clicked.connect(lambda checked=False, c=color: self.setCurrentText(c))
            self.swatches[color] = swatch
            layout.addWidget(swatch)
        layout.addStretch()

    def currentText(self):
        return self.value

    def addItems(self, values):
        pass

    def setCurrentText(self, color):
        if color not in self.values:
            color = self.values[-1]
        changed = color != self.value
        self.value = color
        for name, swatch in self.swatches.items():
            swatch.setChecked(name == color)
            swatch.update()
        if changed:
            self.currentTextChanged.emit(color)
            self.currentIndexChanged.emit(self.values.index(color))


def color_popup(owner, current, changed, anchor=None):
    menu = QMenu(owner)
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(10, 8, 10, 8)
    heading = QLabel('Note color')
    heading.setStyleSheet('font-size:12px;color:#73726d;padding-bottom:5px;')
    layout.addWidget(heading)
    picker = ColorPicker(current)
    picker.currentTextChanged.connect(lambda color: (changed(color), menu.close()))
    layout.addWidget(picker)
    action = QWidgetAction(menu)
    action.setDefaultWidget(panel)
    menu.addAction(action)
    polish_surfaces(menu)
    origin = anchor or owner
    menu.exec(origin.mapToGlobal(origin.rect().bottomLeft()))


class SoftTooltip(QFrame):
    def __init__(self):
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self.anchor = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 6, 7, 9)
        bubble = QFrame()
        bubble.setObjectName('tooltipBubble')
        self._bubble = bubble
        inner = QVBoxLayout(bubble)
        inner.setContentsMargins(11, 7, 11, 7)
        self.label = QLabel()
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(360)
        inner.addWidget(self.label)
        self._apply_theme()
        shadow = QGraphicsDropShadowEffect(bubble)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 55))
        bubble.setGraphicsEffect(shadow)
        layout.addWidget(bubble)

    def _apply_theme(self):
        from .tokens import current_tokens
        t = current_tokens()
        self._bubble.setStyleSheet(
            f'QFrame#tooltipBubble {{background:{t.tooltip_bg};border:1px solid {t.tooltip_border};border-radius:10px;}}'
        )
        self.label.setStyleSheet(
            f'color:{t.tooltip_fg};font-family:Inter;font-size:12px;font-weight:500;background:transparent;'
        )

    def show_for(self, widget, text, point):
        self._apply_theme()
        if self.isVisible() and self.anchor is widget and self.label.text() == text:
            return
        self.anchor = widget
        self.label.setText(text)
        self.layout().activate()
        self.adjustSize()
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(point.x() + 10, area.right() - self.width() - 4)
        y = min(point.y() + 16, area.bottom() - self.height() - 4)
        self.move(max(area.left(), x), max(area.top(), y))
        # A native popup must not use a widget opacity effect: its offscreen
        # backing surface can flash at the screen origin on Windows.
        previous = getattr(self, '_fade', None)
        if previous:
            previous.stop()
        self.setWindowOpacity(0.0 if motion_enabled() else 1.0)
        self.show()
        if motion_enabled():
            animation = QPropertyAnimation(self, b'windowOpacity', self)
            animation.setDuration(110)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._fade = animation
            animation.start()

    def hideEvent(self, event):
        animation = getattr(self, '_fade', None)
        if animation:
            animation.stop()
        self.anchor = None
        super().hideEvent(event)


class TooltipTimingStyle(QProxyStyle):
    """Use Qt's own hover lifecycle, including safe destruction and warm tooltips."""
    def __init__(self):
        super().__init__('Fusion')

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return 380
        if hint == QStyle.StyleHint.SH_ToolTip_FallAsleepDelay:
            return 1200
        return super().styleHint(hint, option, widget, returnData)


class InteractionPolish(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.tooltip = SoftTooltip()
        self.dismiss = QTimer(self)
        self.dismiss.setSingleShot(True)
        self.dismiss.timeout.connect(self.tooltip.hide)
        app.installEventFilter(self)
        app.aboutToQuit.connect(self.tooltip.close)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.ToolTip and isinstance(obj, QWidget) and obj.toolTip():
            self.tooltip.show_for(obj, obj.toolTip(), event.globalPos())
            self.dismiss.start(6000)
            event.accept()
            return True
        if kind == QEvent.Type.Leave and obj is self.tooltip.anchor:
            self.tooltip.hide()
        elif kind == QEvent.Type.MouseButtonPress:
            self.tooltip.hide()
        elif kind == QEvent.Type.WindowDeactivate and isinstance(obj, QWidget) and obj.isWindow() and obj is not self.tooltip:
            self.tooltip.hide()
        return False


def install_polish(app):
    if not hasattr(app, '_tabla_polish'):
        app.setStyle(TooltipTimingStyle())
        app._tabla_polish = InteractionPolish(app)
