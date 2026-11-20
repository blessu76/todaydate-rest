"""publish_next helpers: queue order, date/time stamping, en+ko editions. No git, no network."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import publish_next  # noqa: E402

SAMPLE = '---\ntitle: T\ndescription: D\nslug: s\nlang: en\n---\n\nBody\n'


class StampTest(unittest.TestCase):
    def test_inserts_date_and_time_after_title(self):
        out = publish_next.stamp(SAMPLE, "2026-11-21", "14:05")
        self.assertIn('title: T\ndate: 2026-11-21\ntime: "14:05"\ndescription: D', out)
        self.assertTrue(out.endswith("\n---\n\nBody\n"))

    def test_replaces_existing_date_and_time(self):
        text = SAMPLE.replace("title: T\n", 'title: T\ndate: 2000-01-01\ntime: "01:01"\n')
        out = publish_next.stamp(text, "2026-11-21", "14:05")
        self.assertEqual(out.count("date:"), 1)
        self.assertNotIn("2000-01-01", out)
        self.assertIn('time: "14:05"', out)


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.q = tempfile.mkdtemp()
        for name in ("02-b", "01-a", "notes", ".published"):
            os.makedirs(os.path.join(self.q, name))

    def test_front_of_queue_is_lowest_number(self):
        self.assertEqual(publish_next.next_folder(self.q), "01-a")

    def test_empty_queue_returns_none(self):
        empty = tempfile.mkdtemp()
        self.assertIsNone(publish_next.next_folder(empty))

    def test_editions_need_en_and_ko(self):
        folder = os.path.join(self.q, "01-a")
        Path(folder, "en.md").write_text(SAMPLE, encoding="utf-8")
        with self.assertRaises(FileNotFoundError):
            publish_next.editions(folder)
        Path(folder, "ko.md").write_text(SAMPLE.replace("lang: en", "lang: ko"), encoding="utf-8")
        self.assertEqual([lang for lang, _ in publish_next.editions(folder)], ["en", "ko"])


if __name__ == "__main__":
    unittest.main()
