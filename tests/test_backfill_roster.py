from __future__ import annotations

import contextlib
import io
import json
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path

from upsets.backfill_roster import backfill, main
from upsets.http import FetchError
from upsets.models import Game, Team
from upsets.roster import roster_path


def team(seo, name):
    return Team(seo=seo, name=name, score=None, winner=False, conference="")


def fake(boards, fail_days=()):
    def scoreboard(gender, day):
        if day in fail_days:
            raise FetchError("down")
        return [Game("1", gender, team(a, a.upper()), team(b, b.upper()), "final", "", "/x")
                for a, b in boards.get((gender, day), [])]
    return types.SimpleNamespace(fetch_scoreboard=scoreboard)


class BackfillTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        out = contextlib.redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def read(self):
        return json.loads(roster_path(self.root).read_text())

    def test_collects_teams_from_every_day_and_gender(self):
        boards = {("men", date(2026, 11, 1)): [("a", "b")],
                  ("men", date(2026, 11, 2)): [("c", "a")],
                  ("women", date(2026, 11, 2)): [("w1", "w2")]}
        failures = backfill(date(2026, 11, 1), date(2026, 11, 2), self.root,
                            dry_run=False, fetch=fake(boards))
        self.assertEqual(failures, 0)
        self.assertEqual(sorted(self.read()["men"]), ["a", "b", "c"])
        self.assertEqual(sorted(self.read()["women"]), ["w1", "w2"])

    def test_dry_run_saves_nothing(self):
        backfill(date(2026, 11, 1), date(2026, 11, 1), self.root, dry_run=True,
                 fetch=fake({("men", date(2026, 11, 1)): [("a", "b")]}))
        self.assertFalse(roster_path(self.root).exists())

    def test_existing_names_win(self):
        roster_path(self.root).parent.mkdir(parents=True)
        roster_path(self.root).write_text(json.dumps(
            {"men": {"a": "Newer Name"}, "women": {}}), encoding="utf-8")
        backfill(date(2026, 11, 1), date(2026, 11, 1), self.root, dry_run=False,
                 fetch=fake({("men", date(2026, 11, 1)): [("a", "b")]}))
        self.assertEqual(self.read()["men"]["a"], "Newer Name")
        self.assertEqual(self.read()["men"]["b"], "B")

    def test_failed_days_are_counted_and_main_exits_1(self):
        f = fake({}, fail_days={date(2026, 11, 2)})
        self.assertEqual(backfill(date(2026, 11, 1), date(2026, 11, 2), self.root,
                                  dry_run=True, fetch=f), 2)
        code = main(["--from", "2026-11-01", "--to", "2026-11-02", "--dry-run"],
                    fetch=f, root=self.root)
        self.assertEqual(code, 1)

    def test_bad_range_exits_1(self):
        self.assertEqual(main(["--from", "2026-11-05", "--to", "2026-11-01"],
                              fetch=fake({}), root=self.root), 1)

    def test_ok_range_exits_0(self):
        self.assertEqual(main(["--from", "2026-11-01", "--to", "2026-11-01"],
                              fetch=fake({}), root=self.root), 0)


if __name__ == "__main__":
    unittest.main()
