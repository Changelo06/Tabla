import tempfile
import unittest
from pathlib import Path
from tabla.storage import Store
from tabla.timer import FocusTimer


class Clock:
    value = 10000.0
    def __call__(self):
        return self.value


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "data.sqlite3")
        self.clock = Clock()
        self.timer = FocusTimer(self.store, self.clock, self.clock)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_pause_and_reopen_keep_remaining(self):
        self.timer.start()
        self.clock.value += 17
        self.timer.pause()
        self.clock.value += 100
        restored = FocusTimer(self.store, self.clock, self.clock)
        self.assertEqual(restored.remaining(), 1483)
        restored.start()
        self.clock.value += 3
        self.assertEqual(restored.remaining(), 1480)

    def test_running_timer_recovers_elapsed_time_after_restart(self):
        self.timer.start()
        self.clock.value += 30
        restored = FocusTimer(self.store, self.clock, self.clock)
        self.assertEqual(restored.remaining(), 1470)

    def test_completion_is_idempotent_and_does_not_complete_task(self):
        task = self.store.save({"kind": "task", "title": "Writing", "status": "In progress"})
        self.timer.data["task"] = task["id"]
        self.timer.start()
        self.clock.value += 1501
        self.assertEqual(self.timer.finish_if_due(), "Focus")
        self.assertFalse(self.timer.finish_if_due())
        self.assertEqual(self.store.get(task["id"])["status"], "In progress")
        sessions = self.store.records("session")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["seconds"], 1500)
        self.assertTrue(sessions[0]["completed"])
        self.assertEqual(self.timer.data["mode"], "Short break")

    def test_interrupted_session_recorded_once_per_id(self):
        self.timer.start()
        self.clock.value += 12
        self.timer.pause()
        self.timer.record()
        self.timer.record()
        self.assertEqual(len(self.store.records("session")), 1)
        self.assertFalse(self.store.records("session")[0]["completed"])


if __name__ == "__main__":
    unittest.main()
