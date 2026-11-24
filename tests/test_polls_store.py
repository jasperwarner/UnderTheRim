from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from upsets.models import Poll, PollEntry
from upsets.polls_store import poll_for, save_poll


def make_poll(as_of, gender="men"):
    return Poll(gender, "Coaches Poll", as_of,
                [PollEntry(1, "Queens (NC)"), PollEntry(2, "St. Mary’s")],
                "test", "Week test")


class PollsStoreTest(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            poll = make_poll(date(2026, 11, 22))
            path = save_poll(poll, root)
            self.assertEqual(path, root / "data" / "polls" / "men" / "2026-11-22.json")
            self.assertEqual(poll_for("men", date(2026, 11, 23), root), poll)

    def test_poll_for_picks_newest_before(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_poll(make_poll(date(2026, 11, 15)), root)
            save_poll(make_poll(date(2026, 11, 22)), root)
            self.assertEqual(poll_for("men", date(2026, 11, 21), root).as_of, date(2026, 11, 15))
            self.assertEqual(poll_for("men", date(2026, 11, 23), root).as_of, date(2026, 11, 22))
            self.assertIsNone(poll_for("men", date(2026, 11, 15), root))

    def test_corrupt_newest_file_skipped_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_poll(make_poll(date(2026, 11, 15)), root)
            (root / "data" / "polls" / "men" / "2026-11-22.json").write_text("{oops")
            warnings = []
            p = poll_for("men", date(2026, 11, 23), root, warnings)
            self.assertEqual(p.as_of, date(2026, 11, 15))
            self.assertEqual(len(warnings), 1)
            self.assertIn("2026-11-22.json", warnings[0])

    def test_wrong_types_in_saved_poll_skipped(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d = root / "data" / "polls" / "men"
            d.mkdir(parents=True)
            good = make_poll(date(2026, 11, 22)).to_json()
            for i, bad in enumerate([dict(good, as_of="not a date"),
                                     dict(good, entries=[{"rank": "x", "name": "A"}]),
                                     dict(good, entries=[{"rank": 1, "name": 7}]),
                                     dict(good, title=None), dict(good, entries=[]),
                                     [1, 2]]):
                (d / "2026-11-22.json").write_text(json.dumps(bad))
                warnings = []
                self.assertIsNone(poll_for("men", date(2026, 11, 23), root, warnings), i)
                self.assertEqual(len(warnings), 1, i)

    def test_missing_directory_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(poll_for("women", date(2026, 11, 23), Path(tmp)))


if __name__ == "__main__":
    unittest.main()
