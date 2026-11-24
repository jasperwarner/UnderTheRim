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
from upsets.main import main, run
from upsets.models import PlayerLine, Poll, PollEntry
from upsets.notion import NotionError
from upsets.polls_store import save_poll

FIX = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parent.parent
ROOT_ALIASES = REPO / "aliases.json"
ROOT_D2 = REPO / "d2_conferences.json"
FAKE_ENV = {"NOTION_TOKEN": "secret_tok_123", "NOTION_DATABASE_ID": "db_456"}


class FakeNotion:
    def __init__(self, fail=None):
        self.reports = []
        self.fail = fail

    def publish(self, report):
        self.reports.append(report)
        if self.fail is not None:
            raise self.fail
        return "https://notion.example/page"


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
        (self.root / "d2_conferences.json").write_text(ROOT_D2.read_text(encoding="utf-8"))
        self.addCleanup(self._tmp.cleanup)
        out = contextlib.redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def test_full_run_on_fixtures(self):
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertEqual(r.final_counts, {("d2", "men"): 109, ("d2", "women"): 109})
        self.assertEqual(set(r.flags), {("d2", "men"), ("d2", "women")})
        self.assertEqual(set(r.games), {("d2", "men"), ("d2", "women")})
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
        self.assertEqual(r.flags[("d2", "women")], [])

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
        for fl in r.flags[("d2", "men")]:
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

    def test_missing_aliases_warns(self):
        (self.root / "aliases.json").unlink()
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(any(w.startswith("aliases.json couldn't be read") for w in r.warnings))
        self.assertEqual(r.status, "Check data")

    def test_invalid_aliases_json_warns(self):
        for bad in ("{not json", "[1, 2]"):
            (self.root / "aliases.json").write_text(bad)
            r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
            self.assertTrue(any(w.startswith("aliases.json couldn't be read")
                                for w in r.warnings), bad)

    def test_offseason_non_final_games_still_publish(self):
        class FakeNotion:
            published = 0

            def publish(self, report):
                FakeNotion.published += 1
                return "u"

        fetch = make_fetch()
        games = sources.parse_scoreboard(_load("scoreboard_men_2026-11-21.json"), "men")[:1]
        games[0].state = "pre"
        fetch.fetch_scoreboard = lambda g, d: games if g == "men" else []
        r = run(date(2026, 7, 4), self.root, dry_run=False, fetch=fetch, notion=FakeNotion())
        self.assertEqual(FakeNotion.published, 1)
        self.assertTrue(any(w.startswith("Not final (men)") for w in r.warnings))
        self.assertTrue((self.root / "data" / "2026-07-04.json").exists())

    def test_fatal_run_publishes_failed_page(self):
        n = FakeNotion()
        r = run(date(2026, 11, 21), self.root, dry_run=False,
                fetch=make_fetch(men_board=False, women_board=False), notion=n)
        self.assertEqual(r.status, "Failed")
        self.assertEqual([x.status for x in n.reports], ["Failed"])

    def test_both_polls_fail_is_fatal(self):
        r = run(date(2026, 11, 21), self.root, dry_run=True,
                fetch=make_fetch(men_poll=False, women_poll=False), notion=None)
        self.assertTrue(r.fatal)
        self.assertEqual(r.status, "Failed")

    def test_fresh_poll_beats_older_saved_poll(self):
        save_poll(Poll("men", "NABC Coaches", date(2026, 11, 8),
                       [PollEntry(1, "Somebody Else")], "src", "NABC thru Nov 8"), self.root)
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(r.polls_used.startswith("Men NABC thru Nov 15"))

    def test_corrupt_saved_poll_warns_and_is_ignored(self):
        d = self.root / "data" / "polls" / "men"
        d.mkdir(parents=True)
        (d / "2026-11-20.json").write_text("{not json")
        (d / "2026-11-19.json").write_text(json.dumps({"gender": "men", "entries": 5}))
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        bad = [w for w in r.warnings if w.startswith("Saved men's poll")]
        self.assertEqual(len(bad), 2, r.warnings)
        self.assertTrue(r.polls_used.startswith("Men NABC thru Nov 15"))
        self.assertFalse(r.fatal)

    def test_unexpected_boxscore_error_only_warns(self):
        fetch = make_fetch()
        fetch.fetch_boxscore = lambda gid: (_ for _ in ()).throw(RuntimeError("weird"))
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertGreater(r.flag_count, 0)
        self.assertEqual(sum(w.startswith("No box score for ") for w in r.warnings),
                         r.flag_count)

    def test_incomplete_boxscore_warns(self):
        # Default fake box score is empty: every flagged game is incomplete.
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        inc = [w for w in r.warnings if w.startswith("Box score incomplete for ")]
        self.assertEqual(len(inc), r.flag_count)
        self.assertTrue(all(w.endswith("— 35+ check may have missed someone") for w in inc))
        self.assertTrue(all("https://www.ncaa.com/game/" in w for w in inc))

    def test_complete_boxscore_no_warning(self):
        fetch = make_fetch()

        def box(game_id):
            g = next(x for gender in ("men", "women")
                     for x in sources.parse_scoreboard(
                         _load(f"scoreboard_{gender}_2026-11-21.json"), gender)
                     if x.game_id == game_id)
            return [PlayerLine("H", g.home.seo, g.home.score),
                    PlayerLine("A", g.away.seo, g.away.score)]
        fetch.fetch_boxscore = box
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertGreater(r.flag_count, 0)
        self.assertFalse(any(w.startswith("Box score incomplete") for w in r.warnings))

    def test_daily_json_has_raw_games(self):
        run(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(), notion=None)
        saved = json.loads((self.root / "data" / "2026-11-21.json").read_text())
        self.assertEqual(len(saved["games"]["d2"]["men"]), 110)
        self.assertEqual(len(saved["games"]["d2"]["women"]), 109)
        g = saved["games"]["d2"]["men"][0]
        self.assertEqual(set(g), {"id", "gameState", "currentPeriod", "home", "away"})
        self.assertEqual(set(g["home"]), {"seo", "name", "score", "conferenceSeo"})

    def test_missing_d2_conferences_warns_and_falls_back(self):
        (self.root / "d2_conferences.json").unlink()
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(any(w.startswith("d2_conferences.json couldn't be read")
                            for w in r.warnings))

    def test_report_printed_before_notion_publish(self):
        printed = []

        class Recorder:
            def publish(self, report):
                printed.append(out.getvalue())
                return "u"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            run(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(),
                notion=Recorder())
        self.assertIn("Upsets for 2026-11-21", printed[0])


class MainEntryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "aliases.json").write_text(ROOT_ALIASES.read_text(encoding="utf-8"))
        (self.root / "d2_conferences.json").write_text(ROOT_D2.read_text(encoding="utf-8"))
        self.addCleanup(self._tmp.cleanup)
        self.out = io.StringIO()
        self.err = io.StringIO()
        for cm in (contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.err)):
            cm.__enter__()
            self.addCleanup(cm.__exit__, None, None, None)

    def _main(self, fetch, notion, date_arg="2026-11-21"):
        return main(["--date", date_arg], fetch=fetch, root=self.root,
                    notion_factory=lambda token, db: notion, env=FAKE_ENV)

    def test_ok_and_check_data_return_0(self):
        n = FakeNotion()
        self.assertEqual(self._main(make_fetch(), n), 0)
        self.assertEqual(n.reports[0].status, "Check data")

    def test_fatal_returns_1(self):
        n = FakeNotion()
        self.assertEqual(self._main(make_fetch(men_board=False, women_board=False), n), 1)
        self.assertEqual(n.reports[0].status, "Failed")

    def test_unexpected_crash_returns_1_and_publishes(self):
        fetch = make_fetch()

        def boom(gender, day):
            raise RuntimeError("kaboom secret_tok_123 here\nsecond line")
        fetch.fetch_scoreboard = boom
        n = FakeNotion()
        self.assertEqual(self._main(fetch, n), 1)
        self.assertEqual(len(n.reports), 1)
        r = n.reports[0]
        self.assertEqual(r.status, "Failed")
        self.assertEqual(r.warnings, ["Program crashed: RuntimeError: kaboom *** here"])
        self.assertEqual(r.flags, {("d2", "men"): [], ("d2", "women"): []})
        self.assertIn("Division II", self.out.getvalue())
        self.assertIn("Program crashed: RuntimeError", self.out.getvalue())
        self.assertNotIn("secret_tok_123", self.out.getvalue() + self.err.getvalue())

    def test_crash_with_notion_down_still_returns_1(self):
        fetch = make_fetch()
        fetch.fetch_scoreboard = lambda g, d: 1 / 0
        n = FakeNotion(fail=NotionError("Notion 503: down"))
        self.assertEqual(self._main(fetch, n), 1)
        self.assertIn("Program crashed: ZeroDivisionError", self.out.getvalue())

    def test_notion_failure_returns_1_after_printing(self):
        n = FakeNotion(fail=NotionError("Notion 400: bad"))
        self.assertEqual(self._main(make_fetch(), n), 1)
        self.assertIn("Upsets for 2026-11-21", self.out.getvalue())
        self.assertIn("could not publish to Notion", self.err.getvalue())

    def test_missing_env_returns_1(self):
        rc = main(["--date", "2026-11-21"], fetch=make_fetch(), root=self.root, env={})
        self.assertEqual(rc, 1)

    def _aliases_without_not_same(self):
        data = json.loads(ROOT_ALIASES.read_text(encoding="utf-8"))
        data["not_same"] = {"men": {}, "women": {}}
        (self.root / "aliases.json").write_text(json.dumps(data), encoding="utf-8")

    def _gvsu_warnings(self, r):
        return [w for w in r.warnings if "Grand Valley State" in w]

    def test_without_roster_look_alike_warns(self):
        self._aliases_without_not_same()
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertEqual(len(self._gvsu_warnings(r)), 1)

    def test_known_team_off_today_gets_no_warning(self):
        self._aliases_without_not_same()
        (self.root / "data").mkdir()
        (self.root / "data" / "teams.json").write_text(json.dumps(
            {"men": {}, "women": {"grand-valley-st": "Grand Valley State"}}), encoding="utf-8")
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertEqual(self._gvsu_warnings(r), [])

    def test_real_run_saves_roster(self):
        run(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(), notion=FakeNotion())
        saved = json.loads((self.root / "data" / "teams.json").read_text())
        self.assertEqual(saved["men"]["ala-huntsville"], "UAH")
        self.assertIn("fort-valley-st", saved["women"])

    def test_dry_run_does_not_touch_roster(self):
        run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertFalse((self.root / "data" / "teams.json").exists())

    def test_corrupt_roster_warns_and_run_continues(self):
        (self.root / "data").mkdir()
        (self.root / "data" / "teams.json").write_text("{nope", encoding="utf-8")
        r = run(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(any("teams.json couldn't be read" in w for w in r.warnings))
        self.assertFalse(r.fatal)

    def test_roster_grows_across_runs(self):
        run(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(), notion=FakeNotion())
        first = json.loads((self.root / "data" / "teams.json").read_text())
        run(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(), notion=FakeNotion())
        self.assertEqual(json.loads((self.root / "data" / "teams.json").read_text()), first)

    def test_dry_run_returns_0_without_notion(self):
        def no_factory(token, db):
            raise AssertionError("no Notion in dry run")
        rc = main(["--date", "2026-11-21", "--dry-run"], fetch=make_fetch(), root=self.root,
                  notion_factory=no_factory, env={})
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
