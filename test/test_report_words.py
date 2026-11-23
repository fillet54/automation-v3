"""Small pieces of a report's wording, and where its caches live"""

import tempfile
import unittest
from pathlib import Path

from automationv3.documents.report import ran_on
from automationv3.documents.run import elapsed, seconds_since
from automationv3.web.context import cache_dir


class TestRanOn(unittest.TestCase):
    def test_says_how_the_latest_run_came_out(self):
        row = {"latest": {"outcome": "fail"}, "outdated": {"lm": "LUM131"}}
        self.assertEqual(ran_on(row), "fail on lm LUM131")

    def test_a_run_without_an_outcome_ran(self):
        for latest in ({"outcome": None}, None):
            with self.subTest(latest):
                self.assertEqual(ran_on({"latest": latest, "outdated": {"lm": "LUM131"}}),
                                 "ran on lm LUM131")


class TestElapsed(unittest.TestCase):
    def test_running_times(self):
        self.assertEqual([elapsed(s) for s in (0, 7.9, 65, 3725)], ["0 s", "7 s", "1:05", "1:02:05"])

    def test_seconds_since(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 22, 10, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(seconds_since("2026-11-22T10:00:00+00:00", now), 30)
        self.assertEqual(seconds_since("2026-11-22T10:00:00", now), 30)  # no zone: UTC
        self.assertIsNone(seconds_since("soon", now))


class TestCacheDir(unittest.TestCase):
    def test_an_absolute_folder_is_used_without_a_database(self):
        folder = Path(tempfile.gettempdir()) / "a-mirror"
        for db in (None, ":memory:", "/srv/automation/db.sqlite"):
            with self.subTest(db):
                self.assertEqual(cache_dir({"DB_PATH": db}, "MIRROR_PATH", str(folder)), folder)

    def test_a_relative_folder_is_beside_the_database(self):
        self.assertEqual(cache_dir({"DB_PATH": "/srv/a/db.sqlite"}, "K", "mirror"),
                         Path("/srv/a/mirror"))
