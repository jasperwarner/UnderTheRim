from __future__ import annotations

import contextlib
import io
import json
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path

from upsets import sources
from upsets.http import FetchError
from upsets.main import run
from upsets.models import PlayerLine

FIX = Path(__file__).parent / "fixtures"
ROOT_ALIASES = Path(__file__).resolve().parent.parent / "aliases.json"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def make_fetch(men_board=True, women_board=True, men_poll=True, women_poll=True,
               boxscore=None):
    def scoreboard(gender, day):
        if (gender == "men" and not men_board) or (gender == "women" and not women_board):
            raise FetchError("down")
        return sources.parse_scoreboard(_load(f"scoreboard_{gender}_2026-11-21.json"), gender)

    def poll(gender):
        if gender == "men":
            if not men_poll:
                raise FetchError("down")
            return sources.parse_nabc(_load("nabc_2026-11-15.json"))
        if not women_poll:
            raise FetchError("down")
        return sources.parse_wbca((FIX / "wbca_2026-11-17.html").read_text(encoding="utf-8"))

    def box(game_id):
        if boxscore is None:
            return []
        if boxscore == "fail":
            raise FetchError("down")
        return boxscore

    return types.SimpleNamespace(fetch_scoreboard=scoreboard, fetch_poll=poll,
                                 fetch_boxscore=box)


class MainRunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "aliases.json").write_text(ROOT_ALIASES.read_text(encoding="utf-8"))
        self.addCleanup(self._tmp.cleanup)
        out = contextlib.redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def test_full_run_on_fixtures(self):
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertEqual(r.final_counts, {"men": 109, "women": 109})
        not_final = [w for w in r.warnings if w.startswith("Not final (men)")]
        self.assertEqual(len(not_final), 1)
        self.assertIn("Selma", not_final[0])
        self.assertIn("AUM", not_final[0])
        self.assertEqual(r.status, "Check data")
        self.assertEqual(r.polls_used, "Men NABC thru Nov 15 · Women WBCA Nov 17")

    def test_dry_run_writes_nothing(self):
        run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertFalse((self.root / "data").exists())

    def test_real_run_writes_data_and_publishes(self):
        class FakeNotion:
            def __init__(self):
                self.reports = []

            def publish(self, report):
                self.reports.append(report)
                return "https://notion.example/page"

        n = FakeNotion()
        r = run(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(), notion=n)
        self.assertEqual(n.reports, [r])
        saved = json.loads((self.root / "data" / "2026-11-21.json").read_text())
        self.assertEqual(saved["day"], "2026-11-21")
        self.assertTrue((self.root / "data" / "polls" / "men").is_dir())

    def test_missing_women_poll_warns(self):
        r = run(date(2026, 11, 21), self.root, dry_run=True,
                fetch=make_fetch(women_poll=False), notion=None)
        self.assertTrue(any("Women's poll couldn't be read today" in w for w in r.warnings))
        self.assertFalse(r.fatal)
        self.assertEqual(r.flags["women"], [])

    def test_both_scoreboards_down_is_fatal(self):
        r = run(date(2026, 11, 21), self.root, dry_run=True,
                fetch=make_fetch(men_board=False, women_board=False), notion=None)
        self.assertTrue(r.fatal)
        self.assertEqual(r.status, "Failed")
        self.assertIn("Men scoreboard couldn't be fetched.", r.warnings)

    def test_rerun_uses_later_poll_with_warning(self):
        r = run(date(2026, 11, 10), self.root, dry_run=True,
                fetch=make_fetch(), notion=None)
        self.assertTrue(any("ranks are from a poll released after this game" in w
                            for w in r.warnings))

    def test_stale_poll_warns(self):
        r = run(date(2026, 12, 1), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(any(w.startswith("Men poll is 16 days old.") for w in r.warnings))

    def test_failed_boxscore_warns(self):
        r = run(date(2026, 11, 21), self.root, dry_run=True,
                fetch=make_fetch(boxscore="fail"), notion=None)
        if r.flag_count:
            self.assertTrue(any(w.startswith("No box score for ") for w in r.warnings))

    def test_big_scorer_added(self):
        box = [PlayerLine("Big Guy", "x", 40)]
        r = run(date(2026, 11, 21), self.root, dry_run=True,
                fetch=make_fetch(boxscore=box), notion=None)
        for fl in r.flags["men"]:
            self.assertTrue(any("35+ pts: Big Guy 40" in t for t in fl.tags))

    def test_zero_games_in_season_warns(self):
        fetch = make_fetch()
        fetch.fetch_scoreboard = lambda g, d: []
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertIn("No men's games found for 2026-11-21 — verify on ncaa.com.", r.warnings)

    def test_offseason_zero_games_skips_publish(self):
        class Boom:
            def publish(self, report):
                raise AssertionError("should not publish")

        fetch = make_fetch()
        fetch.fetch_scoreboard = lambda g, d: []
        run(date(2026, 7, 4), self.root, dry_run=False, fetch=fetch, notion=Boom())
        self.assertFalse((self.root / "data" / "2026-07-04.json").exists())


if __name__ == "__main__":
    unittest.main()
