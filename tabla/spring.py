"""Dashcon-inspired analytical damped harmonic spring engine for native Qt."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from PySide6.QtCore import Qt, QObject, QEvent, QTimer, QVariantAnimation, Signal
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class SpringPreset:
    stiffness: float
    damping: float
    mass: float = 1.0


SNAPPY = SpringPreset(420.0, 30.0, 0.9)       # Crisp pills, toggles, closing morphs
TACTILE = SpringPreset(320.0, 20.0, 1.0)      # Subtle organic spring settle
SILKY = SpringPreset(220.0, 26.0, 1.0)        # Smooth container / note opening
SECONDARY_LAG = SpringPreset(260.0, 24.0, 1.05)  # Sidecar / popover follow-through


def _motion_enabled() -> bool:
    app = QApplication.instance()
    return bool(app and not app.property("reduceMotion") and app.platformName() != "offscreen")


def evaluate_step(t: float, preset: SpringPreset) -> float:
    """Analytical step response 0.0 -> 1.0 for a damped harmonic oscillator."""
    if t <= 0.0:
        return 0.0
    k = max(20.0, preset.stiffness)
    c = max(1.0, preset.damping)
    m = max(0.2, preset.mass)
    w0 = math.sqrt(k / m)
    zeta = c / (2.0 * math.sqrt(k * m))
    if zeta < 1.0:
        wd = w0 * math.sqrt(1.0 - zeta * zeta)
        return 1.0 - math.exp(-zeta * w0 * t) * (
            math.cos(wd * t) + (zeta / math.sqrt(1.0 - zeta * zeta)) * math.sin(wd * t)
        )
    if abs(zeta - 1.0) < 1e-4:
        return 1.0 - math.exp(-w0 * t) * (1.0 + w0 * t)
    s = math.sqrt(zeta * zeta - 1.0)
    r1 = -w0 * (zeta - s)
    r2 = -w0 * (zeta + s)
    return 1.0 - (r2 * math.exp(r1 * t) - r1 * math.exp(r2 * t)) / (r2 - r1)


def evaluate_impulse(t: float, preset: SpringPreset) -> float:
    """Analytical impulse response (starts at 0, peaks ~1.0, settles cleanly to 0)."""
    if t <= 0.0:
        return 0.0
    k = max(20.0, preset.stiffness)
    c = max(1.0, preset.damping)
    m = max(0.2, preset.mass)
    w0 = math.sqrt(k / m)
    zeta = c / (2.0 * math.sqrt(k * m))
    if zeta < 1.0:
        wd = w0 * math.sqrt(1.0 - zeta * zeta)
        t_peak = math.acos(zeta) / wd
        peak = math.exp(-zeta * w0 * t_peak) * math.sin(wd * t_peak)
        norm = 1.0 / peak if peak > 1e-4 else 1.0
        return math.exp(-zeta * w0 * t) * math.sin(wd * t) * norm
    return w0 * t * math.exp(1.0 - w0 * t)


class SpringAnimation(QVariantAnimation):
    """Interruptible Qt animation using analytical damped spring physics."""
    def __init__(self, preset: SpringPreset = SILKY, duration_ms: int = 240, parent=None):
        super().__init__(parent)
        self.preset = preset
        self._base_duration = max(1, int(duration_ms))
        self.setStartValue(0.0)
        self.setEndValue(1.0)
        self.setDuration(self._base_duration if _motion_enabled() else 1)

    def interpolated(self, start, end, progress: float):
        if progress <= 0.0:
            return start
        if progress >= 1.0:
            return end
        t = progress * (self._base_duration / 1000.0)
        val = evaluate_step(t, self.preset)
        return start + (end - start) * val


class HighRefreshSpring(QObject):
    """Wall-clock PreciseTimer (~120Hz) spring driver avoiding Windows CoarseTimer 30fps stutter."""
    valueChanged = Signal(float)
    finished = Signal()

    def __init__(self, preset: SpringPreset = SILKY, duration_ms: int = 210, parent=None):
        super().__init__(parent)
        self.preset = preset
        self._duration = max(0.001, int(duration_ms) / 1000.0)
        self._t0 = 0.0
        self._active = False
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(8)
        self._timer.timeout.connect(self._tick)

    def start(self):
        if not _motion_enabled():
            self._active = False
            self.valueChanged.emit(1.0)
            self.finished.emit()
            return
        self._t0 = time.perf_counter()
        self._active = True
        self._timer.start()

    def stop(self):
        self._active = False
        self._timer.stop()

    def _tick(self):
        if not self._active:
            return
        elapsed = time.perf_counter() - self._t0
        if elapsed >= self._duration:
            self._active = False
            self._timer.stop()
            self.valueChanged.emit(1.0)
            self.finished.emit()
            return
        # Normalize step response so value reaches 1.0 cleanly at duration without a final jump.
        end_val = evaluate_step(self._duration, self.preset)
        val = evaluate_step(elapsed, self.preset) / (end_val if abs(end_val) > 1e-4 else 1.0)
        self.valueChanged.emit(val)


class SmoothWheelFilter(QObject):
    """Silky damped mouse-wheel scroller (bypasses precision touchpads & Reduce motion)."""
    def __init__(self, area):
        super().__init__(area)
        self.area = area
        self._target = None
        self._current = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(8)  # ~120Hz tick
        self._timer.timeout.connect(self._step)
        area.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Wheel or not _motion_enabled():
            return False
        # Preserve native precision touchpad pixel scrolling and Ctrl+zoom untouched.
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False
        if not event.pixelDelta().isNull():
            return False
        delta = event.angleDelta().y()
        if not delta:
            return False
        bar = self.area.verticalScrollBar()
        if not bar or bar.maximum() <= bar.minimum():
            return False
        if not self._timer.isActive() or self._target is None:
            self._current = float(bar.value())
            self._target = float(bar.value())
        step = -delta * 0.55
        self._target = max(float(bar.minimum()), min(float(bar.maximum()), self._target + step))
        if not self._timer.isActive():
            self._timer.start()
        event.accept()
        return True

    def _step(self):
        bar = self.area.verticalScrollBar()
        if not bar or self._target is None or not _motion_enabled():
            self._timer.stop()
            self._target = None
            return
        diff = self._target - self._current
        if abs(diff) < 0.75:
            bar.setValue(round(self._target))
            self._timer.stop()
            self._target = None
            return
        self._current += diff * 0.24
        bar.setValue(round(self._current))
