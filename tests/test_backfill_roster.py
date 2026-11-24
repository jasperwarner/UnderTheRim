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


def team(seo, name, conference=""):
    return Team(seo=seo, name=name, score=None, winner=False, conference=conference)


def fake(boards, fail_days=(), confs=None, calls=None):
    confs = confs or {}

    def scoreboard(gender, day, division="d2"):
        if calls is not None:
            calls.append((gender, day, division))
        if day in fail_days:
            raise FetchError("down")
        return [Game("1", gender, team(a, a.upper(), confs.get(a, "")),
                     team(b, b.upper(), confs.get(b, "")), "final", "", "/x")
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

    def read_division(self, division):
        return json.loads(roster_path(self.root, division).read_text())

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

    def test_division_d1_fetches_d1_and_writes_teams_d1_only(self):
        calls = []
        boards = {("men", date(2026, 11, 1)): [("a", "b")]}
        failures = backfill(date(2026, 11, 1), date(2026, 11, 1), self.root, dry_run=False,
                            fetch=fake(boards, calls=calls), division="d1")
        self.assertEqual(failures, 0)
        self.assertEqual({c[2] for c in calls}, {"d1"})
        self.assertEqual(sorted(self.read_division("d1")["men"]), ["a", "b"])
        self.assertFalse(roster_path(self.root).exists())

    def test_cli_division_d1_writes_teams_d1_only(self):
        calls = []
        code = main(["--division", "d1", "--from", "2026-11-01", "--to", "2026-11-01"],
                    fetch=fake({("women", date(2026, 11, 1)): [("x", "y")]}, calls=calls),
                    root=self.root)
        self.assertEqual(code, 0)
        self.assertEqual({c[2] for c in calls}, {"d1"})
        self.assertEqual(sorted(self.read_division("d1")["women"]), ["x", "y"])
        self.assertFalse(roster_path(self.root).exists())

    def test_default_division_is_d2_and_unchanged(self):
        for argv in (["--from", "2026-11-01", "--to", "2026-11-01"],
                     ["--division", "d2", "--from", "2026-11-01", "--to", "2026-11-01"]):
            calls = []
            main(argv, fetch=fake({("men", date(2026, 11, 1)): [("a", "b")]}, calls=calls),
                 root=self.root)
            self.assertEqual({c[2] for c in calls}, {"d2"})
            self.assertEqual(sorted(self.read()["men"]), ["a", "b"])
            self.assertFalse(roster_path(self.root, "d1").exists())

    def test_prints_conference_table_with_distinct_team_counts(self):
        day = date(2026, 11, 1)
        boards = {("men", day): [("a", "b"), ("a", "c"), ("d", "e")],
                  ("women", day): [("a", "b")]}  # same teams again must not double count
        confs = {"a": "big", "b": "big", "c": "small", "d": "small", "e": ""}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            backfill(day, day, self.root, dry_run=True, fetch=fake(boards, confs=confs),
                     division="d1")
        out = buf.getvalue()
        self.assertIn("Conference seos seen", out)
        self.assertRegex(out, r"(?m)^\s+big\s+2$")
        self.assertRegex(out, r"(?m)^\s+small\s+2$")
        self.assertRegex(out, r"(?m)^\s+\(none\)\s+1$")

    def test_ok_range_exits_0(self):
        self.assertEqual(main(["--from", "2026-11-01", "--to", "2026-11-01"],
                              fetch=fake({}), root=self.root), 0)


class ConferenceFilesTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent

    def load(self, name):
        return json.loads((self.ROOT / name).read_text(encoding="utf-8"))

    def test_d1_conferences_is_a_sorted_list_of_non_empty_strings(self):
        d1 = self.load("d1_conferences.json")
        self.assertIsInstance(d1, list)
        self.assertTrue(d1)
        self.assertTrue(all(isinstance(c, str) and c.strip() for c in d1))
        self.assertEqual(d1, sorted(d1))
        self.assertEqual(len(d1), len(set(d1)))

    def test_d1_and_d2_conferences_share_nothing(self):
        self.assertEqual(set(self.load("d1_conferences.json"))
                         & set(self.load("d2_conferences.json")), set())


if __name__ == "__main__":
    unittest.main()
