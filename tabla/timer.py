"""Durable device-local timer, independent of Qt's repaint interval."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone


class FocusTimer:
    def __init__(self, store, clock=time.time, monotonic=time.monotonic):
        self.store, self.clock, self.monotonic = store, clock, monotonic
        self.data = store.setting("active_timer") or self._new("Focus")
        self._anchor = None
        self._anchor_remaining = None
        if self.data.get("running"):
            self._anchor_remaining = max(0, self.data["deadline"] - self.clock())
            self._anchor = self.monotonic()

    def _new(self, mode):
        key, default = {"Focus": ("focus_minutes", 25), "Short break": ("short_minutes", 5),
                        "Long break": ("long_minutes", 15)}[mode]
        duration = int(self.store.setting(key, default)) * 60
        return {"mode": mode, "duration": duration, "remaining": duration, "running": False,
                "task": None, "session_id": str(uuid.uuid4()), "started_at": None}

    def persist(self):
        self.store.set_setting("active_timer", self.data)

    def remaining(self):
        if self.data.get("running"):
            return max(0, self._anchor_remaining - (self.monotonic() - self._anchor))
        return max(0, self.data["remaining"])

    def start(self):
        if self.data["running"]:
            return
        self._anchor_remaining = self.data["remaining"]
        self._anchor = self.monotonic()
        self.data.update(running=True, deadline=self.clock() + self._anchor_remaining)
        self.data["started_at"] = self.data.get("started_at") or datetime.now(timezone.utc).isoformat()
        self.persist()

    def pause(self):
        self.data["remaining"] = self.remaining()
        self.data["running"] = False
        self.persist()

    def record(self, completed=False):
        elapsed = self.data["duration"] - self.remaining()
        if self.data["mode"] == "Focus" and elapsed >= 1:
            task = self.store.get(self.data.get("task")) if self.data.get("task") else None
            self.store.save({"id": self.data["session_id"], "kind": "session",
                "title": task["title"] if task else "Open focus", "task": self.data.get("task"),
                "seconds": int(elapsed), "completed": completed, "date": datetime.now().date().isoformat(),
                "started_at": self.data["started_at"]})

    def switch(self, mode):
        task = self.data.get("task")
        self.record(False)
        self.data = self._new(mode)
        self.data["task"] = task
        self.persist()

    def finish_if_due(self):
        if not self.data["running"] or self.remaining() > 0:
            return False
        self.record(True)
        mode = self.data["mode"]
        task = self.data.get("task")
        if mode == "Focus":
            count = self.store.setting("completed_focus_count", 0) + 1
            self.store.set_setting("completed_focus_count", count)
            interval = int(self.store.setting("long_interval", 4))
            next_mode = "Long break" if count % interval == 0 else "Short break"
        else:
            next_mode = "Focus"
        self.data = self._new(next_mode)
        self.data["task"] = task
        self.persist()
        return mode
