"""journal_gate scheduling: time picks, date rollover, the future-date guard, and one run. No launchd, no git."""
import json
import os
import random
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import journal_gate as g  # noqa: E402

KST = ZoneInfo("Asia/Seoul")


class PickTest(unittest.TestCase):
    def test_time_in_window_and_hour_differs_from_prev(self):
        rng = random.Random(1)
        for _ in range(200):
            t = g.pick_time("14:30", rng)
            self.assertTrue(g.valid_time(t), t)
            self.assertNotEqual(t[:2], "14")

    def test_valid_time(self):
        self.assertTrue(g.valid_time("12:00"))
        self.assertTrue(g.valid_time("17:59"))
        self.assertFalse(g.valid_time("18:00"))
        self.assertFalse(g.valid_time("9:5"))
        self.assertFalse(g.valid_time("99:99"))


class RollTest(unittest.TestCase):
    def test_future_slot_is_left_alone(self):
        slot = {"date": "2026-11-21", "time": "14:00", "published": False}
        self.assertIs(g.roll(slot, "2026-11-20"), slot)

    def test_same_day_is_kept(self):
        slot = {"date": "2026-11-21", "time": "14:00", "published": True}
        self.assertIs(g.roll(slot, "2026-11-21"), slot)

    def test_new_day_rolls_and_uses_next_time(self):
        slot = {"date": "2026-11-21", "time": "14:00", "published": True,
                "next_date": "2026-11-22", "next_time": "16:20"}
        out = g.roll(slot, "2026-11-22")
        self.assertEqual((out["date"], out["time"], out["published"]), ("2026-11-22", "16:20", False))
        self.assertEqual(out["prev_time"], "14:00")


class RunTest(unittest.TestCase):
    def setUp(self):
        self.q = tempfile.mkdtemp()
        self.path = os.path.join(self.q, "slot.json")

    def write(self, slot):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(slot, f)

    def test_waits_before_scheduled_date(self):
        self.write({"date": "2026-11-21", "time": "12:30", "published": False})
        calls = []
        r = g.run(datetime(2026, 11, 20, 13, 0, tzinfo=KST), queue=self.q, publish=lambda *a: calls.append(a) or True)
        self.assertEqual(r, "wait")
        self.assertEqual(calls, [])

    def test_publishes_when_due_and_marks_published(self):
        self.write({"date": "2026-11-21", "time": "12:30", "published": False})
        calls = []
        r = g.run(datetime(2026, 11, 21, 12, 45, tzinfo=KST), queue=self.q,
                  publish=lambda *a: calls.append(a) or True, rng=random.Random(3))
        self.assertEqual(r, "published")
        self.assertEqual(calls[0][:2], ("2026-11-21", "12:45"))
        with open(self.path, encoding="utf-8") as f:
            self.assertTrue(json.load(f)["published"])

    def test_failed_publish_keeps_state(self):
        self.write({"date": "2026-11-21", "time": "12:30", "published": False})
        r = g.run(datetime(2026, 11, 21, 12, 45, tzinfo=KST), queue=self.q, publish=lambda *a: False)
        self.assertEqual(r, "failed")
        with open(self.path, encoding="utf-8") as f:
            self.assertFalse(json.load(f)["published"])


if __name__ == "__main__":
    unittest.main()
