"""Optional procedural tactile micro-foley (Dashcon-inspired, zero audio assets)."""
from __future__ import annotations

import io
import math
import struct
import sys
import time
import wave
from functools import lru_cache
from PySide6.QtWidgets import QApplication

_SAMPLE_RATE = 22050
_last_played = 0.0


def enabled() -> bool:
    app = QApplication.instance()
    return bool(app and app.property("tactileSound") and app.platformName() != "offscreen")


def set_enabled(value: bool):
    app = QApplication.instance()
    if app is not None:
        app.setProperty("tactileSound", bool(value))


@lru_cache(maxsize=8)
def _synth_wav(material: str) -> bytes:
    """Synthesize a soft, brief 16-bit mono PCM WAV buffer in memory."""
    durations = {"click": 0.045, "pop": 0.085, "pluck": 0.14, "brass": 0.34}
    dur = durations.get(material, 0.06)
    n = int(_SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / _SAMPLE_RATE
        if material == "click":
            env = math.exp(-t * 85.0)
            freq = 640.0 * math.exp(-t * 30.0) + 180.0
            s = math.sin(2.0 * math.pi * freq * t) * env * 0.16
        elif material == "pop":
            env = math.sin(min(1.0, t / 0.008) * math.pi * 0.5) * math.exp(-t * 36.0)
            freq = 280.0 + 340.0 * min(1.0, t / 0.045)
            s = math.sin(2.0 * math.pi * freq * t) * env * 0.18
        elif material == "pluck":
            env = math.sin(min(1.0, t / 0.005) * math.pi * 0.5) * math.exp(-t * 22.0)
            s = (math.sin(2.0 * math.pi * 523.25 * t) + 0.3 * math.sin(2.0 * math.pi * 1046.5 * t)) * env * 0.14
        else:  # brass chime
            env = math.sin(min(1.0, t / 0.006) * math.pi * 0.5) * math.exp(-t * 8.5)
            s = (
                0.55 * math.sin(2.0 * math.pi * 880.0 * t)
                + 0.25 * math.sin(2.0 * math.pi * 880.0 * 2.01 * t)
                + 0.12 * math.sin(2.0 * math.pi * 880.0 * 2.98 * t)
            ) * env * 0.16
        samples.append(max(-32767, min(32767, int(s * 32767))))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(_SAMPLE_RATE)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def play(material: str):
    """Play a subtle procedural tactile sound asynchronously when opt-in is active."""
    global _last_played
    if sys.platform != "win32" or not enabled():
        return
    now = time.monotonic()
    if now - _last_played < 0.04:
        return
    _last_played = now
    try:
        import winsound
        winsound.PlaySound(
            _synth_wav(material),
            winsound.SND_MEMORY | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
        )
    except Exception:
        pass
