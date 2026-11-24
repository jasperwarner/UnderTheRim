from __future__ import annotations

import contextlib
import io
import json
import tempfile
import types
import unittest
from unittest import mock
from datetime import date
from pathlib import Path

from upsets import sources
from upsets.http import FetchError
from upsets import main as main_module
from upsets.main import main, run
from upsets.models import Game, PlayerLine, Poll, PollEntry, Team
from upsets.notion import NotionError
from upsets.polls_store import save_poll
from upsets.story import INCOMPLETE_LINE

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


def _team(seo, name, score, winner, conference):
    return Team(seo, name, score, winner, conference)


def d1_games(gender):
    """Synthetic D1 board: an unranked team beats AP No. 1, plus a dull game."""
    top = ("houston", "Houston") if gender == "men" else ("south-carolina", "South Carolina")
    upset = Game(f"d1-{gender}-1", gender,
                 home=_team(top[0], top[1], 65, False, "big-12"),
                 away=_team("little-u", "Little U", 70, True, "wac"),
                 state="final", period="FINAL", url=f"/game/d1-{gender}-1", division="d1")
    dull = Game(f"d1-{gender}-2", gender,
                home=_team("big-state", "Big State", 80, True, "big-12"),
                away=_team("small-state", "Small State", 60, False, "wac"),
                state="final", period="FINAL", url=f"/game/d1-{gender}-2", division="d1")
    return [upset, dull]


def make_fetch(men_board=True, women_board=True, men_poll=True, women_poll=True,
               boxscore=None, d1_men_board=True, d1_women_board=True,
               d1_men_poll=True, d1_women_poll=True):
    calls = []

    def scoreboard(gender, day, division="d2"):
        calls.append(("scoreboard", division, gender))
        if division == "d1":
            if (gender == "men" and not d1_men_board) or \
                    (gender == "women" and not d1_women_board):
                raise FetchError("down")
            return d1_games(gender)
        if (gender == "men" and not men_board) or (gender == "women" and not women_board):
            raise FetchError("down")
        return sources.parse_scoreboard(_load(f"scoreboard_{gender}_2026-11-21.json"), gender)

    def poll(gender, division="d2"):
        calls.append(("poll", division, gender))
        if division == "d1":
            if (gender == "men" and not d1_men_poll) or \
                    (gender == "women" and not d1_women_poll):
                raise FetchError("down")
            return sources.parse_ap(_load(f"ap_{gender}_2026-11-22.json"), gender)
        if gender == "men":
            if not men_poll:
                raise FetchError("down")
            return sources.parse_nabc(_load("nabc_2026-11-15.json"))
        if not women_poll:
            raise FetchError("down")
        return sources.parse_wbca((FIX / "wbca_2026-11-17.html").read_text(encoding="utf-8"))

    def box(game_id):
        calls.append(("boxscore", game_id))
        if boxscore is None:
            return []
        if boxscore == "fail":
            raise FetchError("down")
        return boxscore

    return types.SimpleNamespace(fetch_scoreboard=scoreboard, fetch_poll=poll,
                                 fetch_boxscore=box, calls=calls)


def run_d2(*args, **kwargs):
    """The run as it was before D1: Division II only."""
    return run(*args, divisions=("d2",), **kwargs)


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
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertEqual(r.final_counts, {("d2", "men"): 109, ("d2", "women"): 109})
        self.assertEqual(set(r.flags), {("d2", "men"), ("d2", "women")})
        self.assertEqual(set(r.games), {("d2", "men"), ("d2", "women")})
        not_final = [w for w in r.warnings if w.startswith("Not final (D2 men)")]
        self.assertEqual(len(not_final), 1)
        self.assertIn("Selma", not_final[0])
        self.assertIn("AUM", not_final[0])
        self.assertEqual(r.status, "Check data")
        self.assertEqual(r.polls_used, "D2: Men NABC thru Nov 15 · Women WBCA Nov 17")

    def test_dry_run_writes_nothing(self):
        run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertFalse((self.root / "data").exists())

    def test_real_run_writes_data_and_publishes(self):
        n = FakeNotion()
        r = run_d2(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(), notion=n)
        self.assertEqual(n.reports, [r])
        saved = json.loads((self.root / "data" / "2026-11-21.json").read_text())
        self.assertEqual(saved["day"], "2026-11-21")
        self.assertTrue((self.root / "data" / "polls" / "men").is_dir())

    def test_missing_women_poll_warns(self):
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True,
                fetch=make_fetch(women_poll=False), notion=None)
        self.assertTrue(any("Division II: Women's poll couldn't be read today" in w for w in r.warnings))
        self.assertFalse(r.fatal)
        self.assertEqual(r.flags[("d2", "women")], [])

    def test_both_scoreboards_down_is_fatal(self):
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True,
                fetch=make_fetch(men_board=False, women_board=False), notion=None)
        self.assertTrue(r.fatal)
        self.assertEqual(r.status, "Failed")
        self.assertIn("Division II: Men scoreboard couldn't be fetched.", r.warnings)

    def test_rerun_uses_later_poll_with_warning(self):
        r = run_d2(date(2026, 11, 10), self.root, dry_run=True,
                fetch=make_fetch(), notion=None)
        self.assertTrue(any("ranks are from a poll released after this game" in w
                            for w in r.warnings))

    def test_stale_poll_warns(self):
        r = run_d2(date(2026, 12, 1), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(any(w.startswith("Division II: Men poll is 16 days old.") for w in r.warnings))

    def test_failed_boxscore_warns(self):
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True,
                fetch=make_fetch(boxscore="fail"), notion=None)
        if r.flag_count:
            self.assertTrue(any(w.startswith("No box score for ") for w in r.warnings))

    def test_big_scorer_added(self):
        box = [PlayerLine("Big Guy", "x", 40)]
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True,
                fetch=make_fetch(boxscore=box), notion=None)
        for fl in r.flags[("d2", "men")]:
            self.assertTrue(any("35+ pts: Big Guy 40" in t for t in fl.tags))

    def test_zero_games_in_season_warns(self):
        fetch = make_fetch()
        fetch.fetch_scoreboard = lambda g, d, division="d2": []
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertIn("Division II: No men's games found for 2026-11-21 — verify on ncaa.com.", r.warnings)

    def test_offseason_zero_games_skips_publish(self):
        class Boom:
            def publish(self, report):
                raise AssertionError("should not publish")

        fetch = make_fetch()
        fetch.fetch_scoreboard = lambda g, d, division="d2": []
        run_d2(date(2026, 7, 4), self.root, dry_run=False, fetch=fetch, notion=Boom())
        self.assertFalse((self.root / "data" / "2026-07-04.json").exists())

    def test_missing_aliases_warns(self):
        (self.root / "aliases.json").unlink()
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(any(w.startswith("aliases.json couldn't be read") for w in r.warnings))
        self.assertEqual(r.status, "Check data")

    def test_invalid_aliases_json_warns(self):
        for bad in ("{not json", "[1, 2]"):
            (self.root / "aliases.json").write_text(bad)
            r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
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
        fetch.fetch_scoreboard = lambda g, d, division="d2": games if g == "men" else []
        r = run_d2(date(2026, 7, 4), self.root, dry_run=False, fetch=fetch, notion=FakeNotion())
        self.assertEqual(FakeNotion.published, 1)
        self.assertTrue(any(w.startswith("Not final (D2 men)") for w in r.warnings))
        self.assertTrue((self.root / "data" / "2026-07-04.json").exists())

    def test_fatal_run_publishes_failed_page(self):
        n = FakeNotion()
        r = run_d2(date(2026, 11, 21), self.root, dry_run=False,
                fetch=make_fetch(men_board=False, women_board=False), notion=n)
        self.assertEqual(r.status, "Failed")
        self.assertEqual([x.status for x in n.reports], ["Failed"])

    def test_both_polls_fail_is_fatal(self):
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True,
                fetch=make_fetch(men_poll=False, women_poll=False), notion=None)
        self.assertTrue(r.fatal)
        self.assertEqual(r.status, "Failed")

    def test_fresh_poll_beats_older_saved_poll(self):
        save_poll(Poll("men", "NABC Coaches", date(2026, 11, 8),
                       [PollEntry(1, "Somebody Else")], "src", "NABC thru Nov 8"), self.root)
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(r.polls_used.startswith("D2: Men NABC thru Nov 15"))

    def test_corrupt_saved_poll_warns_and_is_ignored(self):
        d = self.root / "data" / "polls" / "men"
        d.mkdir(parents=True)
        (d / "2026-11-20.json").write_text("{not json")
        (d / "2026-11-19.json").write_text(json.dumps({"gender": "men", "entries": 5}))
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        bad = [w for w in r.warnings if w.startswith("Saved men's poll")]
        self.assertEqual(len(bad), 2, r.warnings)
        self.assertTrue(r.polls_used.startswith("D2: Men NABC thru Nov 15"))
        self.assertFalse(r.fatal)

    def test_unexpected_boxscore_error_only_warns(self):
        fetch = make_fetch()
        fetch.fetch_boxscore = lambda gid: (_ for _ in ()).throw(RuntimeError("weird"))
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertGreater(r.flag_count, 0)
        self.assertEqual(sum(w.startswith("No box score for ") for w in r.warnings),
                         r.flag_count)

    def test_incomplete_boxscore_warns(self):
        # Default fake box score is empty: every flagged game is incomplete.
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
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
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertGreater(r.flag_count, 0)
        self.assertFalse(any(w.startswith("Box score incomplete") for w in r.warnings))

    def test_daily_json_has_raw_games(self):
        run_d2(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(), notion=None)
        saved = json.loads((self.root / "data" / "2026-11-21.json").read_text())
        self.assertEqual(len(saved["games"]["d2"]["men"]), 110)
        self.assertEqual(len(saved["games"]["d2"]["women"]), 109)
        g = saved["games"]["d2"]["men"][0]
        self.assertEqual(set(g), {"id", "gameState", "currentPeriod", "home", "away"})
        self.assertEqual(set(g["home"]), {"seo", "name", "score", "conferenceSeo"})

    def test_missing_d2_conferences_warns_and_falls_back(self):
        (self.root / "d2_conferences.json").unlink()
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
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
            run_d2(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(),
                notion=Recorder())
        self.assertIn("Upsets for 2026-11-21", printed[0])


D2_MEN_FLAGS = [
    ("No. 15 Minnesota St. beat Northern Mich., 79-77", ["Close (2 pts)"]),
    ("Unranked Cedarville beat No. 25 Lincoln Memorial, 76-74", ["Upset", "Close (2 pts)"]),
    ("No. 7 West Liberty beat Shepherd, 88-87", ["Close (1 pt)"]),
    ("Unranked St. Cloud St. beat No. 20 Lake Superior St., 76-62", ["Upset"]),
    ("No. 12 Okla. Baptist beat Emporia St., 87-85", ["Close (2 pts)"]),
    ("Unranked Minn. Duluth beat No. 19 Michigan Tech, 80-76", ["Upset"]),
    ("Unranked Sioux Falls beat No. 8 Black Hills St., 71-54", ["Upset"]),
    ("No. 3 DBU beat Henderson St., 89-82", ["Overtime"]),
]
D2_WOMEN_FLAGS = [
    ("No. 22 Fairmont St. beat Bloomsburg, 81-79", ["Close (2 pts)", "Overtime"]),
    ("Unranked Maryville (MO) beat No. 16 Concordia-St. Paul, 77-70", ["Upset"]),
    ("Unranked North Georgia beat No. 8 Carson-Newman, 62-53", ["Upset"]),
]
BOTH_DAY = date(2026, 11, 23)  # after the D1 AP polls (Nov 22) and the D2 polls


def _flags(r, key):
    return [(f.headline, f.tags) for f in r.flags[key]]


class TwoDivisionRunTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "aliases.json").write_text(ROOT_ALIASES.read_text(encoding="utf-8"))
        (self.root / "d2_conferences.json").write_text(ROOT_D2.read_text(encoding="utf-8"))
        (self.root / "d1_conferences.json").write_text(json.dumps(["big-12", "wac"]))
        self.addCleanup(self._tmp.cleanup)
        out = contextlib.redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def test_both_divisions_flag_and_appear(self):
        r = run(BOTH_DAY, self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertEqual(set(r.flags), {("d1", "men"), ("d1", "women"),
                                        ("d2", "men"), ("d2", "women")})
        self.assertEqual(_flags(r, ("d1", "men")),
                         [("Unranked Little U beat No. 1 Houston, 70-65", ["Upset"])])
        self.assertEqual(_flags(r, ("d1", "women")),
                         [("Unranked Little U beat No. 1 South Carolina, 70-65", ["Upset"])])
        self.assertEqual(_flags(r, ("d2", "men")), D2_MEN_FLAGS)
        self.assertEqual(_flags(r, ("d2", "women")), D2_WOMEN_FLAGS)
        for (division, _), flags in r.flags.items():
            for f in flags:
                self.assertEqual(f.division, division)
                self.assertEqual(f.game.division, division)
        self.assertEqual(r.final_counts, {("d1", "men"): 2, ("d1", "women"): 2,
                                          ("d2", "men"): 109, ("d2", "women"): 109})
        self.assertEqual(r.polls_used,
                         "D1: Men AP thru Nov 22 · Women AP thru Nov 22"
                         " | D2: Men NABC thru Nov 15 · Women WBCA Nov 17")
        self.assertFalse(r.fatal)

    def test_d1_flag_gets_story_with_poll_record(self):
        r = run(BOTH_DAY, self.root, dry_run=True, fetch=make_fetch(), notion=None)
        f = r.flags[("d1", "men")][0]
        self.assertEqual(f.story, "Big story")  # unranked over No. 1, plus D1
        self.assertEqual(f.facts[1], "Houston: No. 1, 6-0")
        self.assertEqual(f.facts[-1], INCOMPLETE_LINE)

    def test_d1_scoreboard_down_keeps_d2_flags(self):
        n = FakeNotion()
        r = run(BOTH_DAY, self.root, dry_run=False, notion=n,
                fetch=make_fetch(d1_men_board=False, d1_women_board=False))
        self.assertEqual(r.status, "Failed")
        self.assertIn("Division I: Men scoreboard couldn't be fetched.", r.warnings)
        self.assertIn("Division I: Women scoreboard couldn't be fetched.", r.warnings)
        self.assertEqual(_flags(r, ("d2", "men")), D2_MEN_FLAGS)
        self.assertEqual(_flags(r, ("d2", "women")), D2_WOMEN_FLAGS)
        self.assertEqual(r.flags[("d1", "men")], [])
        self.assertEqual(n.reports, [r])
        self.assertIn("D1: Men n/a · Women n/a | D2: Men NABC", r.polls_used)

    def test_one_d1_scoreboard_down_is_fatal_but_rest_publish(self):
        r = run(BOTH_DAY, self.root, dry_run=True, notion=None,
                fetch=make_fetch(d1_men_board=False))
        self.assertTrue(r.fatal)
        self.assertEqual(len(r.flags[("d1", "women")]), 1)
        self.assertEqual(_flags(r, ("d2", "men")), D2_MEN_FLAGS)

    def test_d2_scoreboard_down_keeps_d1_flags(self):
        r = run(BOTH_DAY, self.root, dry_run=True, notion=None,
                fetch=make_fetch(men_board=False, women_board=False))
        self.assertEqual(r.status, "Failed")
        self.assertIn("Division II: Men scoreboard couldn't be fetched.", r.warnings)
        self.assertIn("Division II: Women scoreboard couldn't be fetched.", r.warnings)
        self.assertFalse(any(w.startswith("Division I:") and "scoreboard" in w
                             for w in r.warnings))
        self.assertEqual(len(r.flags[("d1", "men")]), 1)
        self.assertEqual(len(r.flags[("d1", "women")]), 1)

    def test_d1_poll_missing_skips_d1_ranked_rules_only(self):
        r = run(BOTH_DAY, self.root, dry_run=True, notion=None,
                fetch=make_fetch(d1_men_poll=False))
        self.assertIn("Division I: Men's poll couldn't be read today — "
                      "men's ranked rules skipped.", r.warnings)
        self.assertEqual(r.flags[("d1", "men")], [])
        self.assertEqual(len(r.flags[("d1", "women")]), 1)
        self.assertEqual(_flags(r, ("d2", "men")), D2_MEN_FLAGS)
        self.assertFalse(r.fatal)
        self.assertTrue(r.polls_used.startswith("D1: Men none · Women AP thru Nov 22 | "))

    def test_some_polls_missing_is_not_fatal_but_all_is(self):
        r = run(BOTH_DAY, self.root, dry_run=True, notion=None,
                fetch=make_fetch(men_poll=False, women_poll=False))
        self.assertFalse(r.fatal)
        r = run(BOTH_DAY, self.root, dry_run=True, notion=None,
                fetch=make_fetch(men_poll=False, women_poll=False,
                                 d1_men_poll=False, d1_women_poll=False))
        self.assertTrue(r.fatal)

    def _write_aliases(self, mutate):
        data = json.loads(ROOT_ALIASES.read_text(encoding="utf-8"))
        mutate(data)
        (self.root / "aliases.json").write_text(json.dumps(data), encoding="utf-8")

    def test_bad_d1_aliases_do_not_wipe_d2_aliases(self):
        bad_shapes = (lambda d: d.__setitem__("d1", {"not_same": {"men": {"X": "not-a-list"}}}),
                      lambda d: d.__setitem__("d1", ["not", "an", "object"]))
        for mutate in bad_shapes:
            self._write_aliases(mutate)
            r = run(BOTH_DAY, self.root, dry_run=True, fetch=make_fetch(), notion=None)
            d1_warnings = [w for w in r.warnings if w.startswith("Division I aliases")]
            self.assertEqual(len(d1_warnings), 1, r.warnings)
            self.assertIn("D1 name matching may miss ranked teams.", d1_warnings[0])
            self.assertFalse(any(w.startswith("aliases.json couldn't") for w in r.warnings))
            # D2's real aliases still work: same flags and no extra D2 name warnings
            self.assertEqual(_flags(r, ("d2", "men")), D2_MEN_FLAGS)
            self.assertEqual(_flags(r, ("d2", "women")), D2_WOMEN_FLAGS)
            self.assertEqual(len(r.flags[("d1", "men")]), 1)
            self.assertEqual(r.status, "Check data")

    def test_bad_d2_aliases_still_run_d1(self):
        self._write_aliases(lambda d: d.__setitem__("men", {"A": 1}))
        r = run(BOTH_DAY, self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(any(w.startswith("aliases.json couldn't be read (ValueError)")
                            for w in r.warnings))
        self.assertFalse(any(w.startswith("Division I aliases") for w in r.warnings))
        self.assertEqual(len(r.flags[("d1", "men")]), 1)
        self.assertEqual(len(r.flags[("d1", "women")]), 1)

    def test_real_run_saves_d1_poll_and_roster(self):
        run(BOTH_DAY, self.root, dry_run=False, fetch=make_fetch(), notion=FakeNotion())
        self.assertTrue((self.root / "data" / "polls" / "d1" / "men" / "2026-11-22.json")
                        .is_file())
        self.assertTrue((self.root / "data" / "polls" / "d1" / "women" / "2026-11-22.json")
                        .is_file())
        d1 = json.loads((self.root / "data" / "teams_d1.json").read_text())
        self.assertEqual(d1["men"]["little-u"], "Little U")
        self.assertIn("south-carolina", d1["women"])
        d2 = json.loads((self.root / "data" / "teams.json").read_text())
        self.assertIn("ala-huntsville", d2["men"])
        self.assertNotIn("little-u", d2["men"])

    def test_dry_run_saves_no_d1_poll_or_roster(self):
        run(BOTH_DAY, self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertFalse((self.root / "data" / "polls" / "d1").exists())
        self.assertFalse((self.root / "data" / "teams_d1.json").exists())

    def test_d2_only_reproduces_old_run(self):
        fetch = make_fetch()
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertEqual(set(r.flags), {("d2", "men"), ("d2", "women")})
        self.assertEqual(_flags(r, ("d2", "men")), D2_MEN_FLAGS)
        self.assertEqual(_flags(r, ("d2", "women")), D2_WOMEN_FLAGS)
        self.assertEqual(r.polls_used, "D2: Men NABC thru Nov 15 · Women WBCA Nov 17")
        self.assertFalse(any(c[1] == "d1" for c in fetch.calls if c[0] != "boxscore"))
        self.assertFalse(any("d1_conferences" in w for w in r.warnings))

    def test_only_expected_fetches(self):
        fetch = make_fetch()
        r = run(BOTH_DAY, self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertEqual([c for c in fetch.calls if c[0] != "boxscore"], [
            ("scoreboard", "d1", "men"), ("poll", "d1", "men"),
            ("scoreboard", "d1", "women"), ("poll", "d1", "women"),
            ("scoreboard", "d2", "men"), ("poll", "d2", "men"),
            ("scoreboard", "d2", "women"), ("poll", "d2", "women")])
        flagged = sorted(f.game.game_id for v in r.flags.values() for f in v)
        self.assertEqual(sorted(c[1] for c in fetch.calls if c[0] == "boxscore"), flagged)

    def test_story_label_set_after_big_scorer_tag(self):
        def find(r):
            return next(f for f in r.flags[("d2", "men")] if "St. Cloud" in f.headline)
        plain = find(run_d2(date(2026, 11, 21), self.root, dry_run=True,
                            fetch=make_fetch(), notion=None))
        self.assertEqual(plain.story, "")
        self.assertEqual(plain.story_points, 3)
        box = [PlayerLine("Big Guy", "st-cloud-st", 35)]
        lifted = find(run_d2(date(2026, 11, 21), self.root, dry_run=True,
                             fetch=make_fetch(boxscore=box), notion=None))
        self.assertIn("35+ pts: Big Guy 35 (st-cloud-st)", lifted.tags)
        self.assertEqual(lifted.story_points, 4)
        self.assertEqual(lifted.story, "Strong story")

    def test_failed_boxscore_still_rates_story(self):
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True,
                   fetch=make_fetch(boxscore="fail"), notion=None)
        f = next(f for f in r.flags[("d2", "men")] if "Sioux Falls" in f.headline)
        self.assertEqual(f.story, "Strong story")
        self.assertEqual(f.facts[-1], INCOMPLETE_LINE)

    def test_missing_d1_conferences_warns_and_falls_back(self):
        (self.root / "d1_conferences.json").unlink()
        r = run(BOTH_DAY, self.root, dry_run=True, fetch=make_fetch(), notion=None)
        bad = [w for w in r.warnings if w.startswith("d1_conferences.json couldn't be read")]
        self.assertEqual(len(bad), 1, r.warnings)
        self.assertIn("Non-D1 opponent", bad[0])
        self.assertEqual(len(r.flags[("d1", "men")]), 1)
        self.assertFalse(r.fatal)

    def test_unreadable_d1_conferences_warns(self):
        (self.root / "d1_conferences.json").write_text("{nope")
        r = run(BOTH_DAY, self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(any(w.startswith("d1_conferences.json couldn't be read (")
                            for w in r.warnings))

    def test_d1_conference_list_tags_outsiders(self):
        (self.root / "d1_conferences.json").write_text(json.dumps(["big-12"]))
        r = run(BOTH_DAY, self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertIn("Non-D1 opponent", r.flags[("d1", "men")][0].tags)
        self.assertFalse(any("d1_conferences" in w for w in r.warnings))

    def test_d1_not_final_warning_names_division(self):
        fetch = make_fetch()
        board = fetch.fetch_scoreboard

        def scoreboard(gender, day, division="d2"):
            games = board(gender, day, division)
            if division == "d1" and gender == "men":
                games[1].state = "live"
            return games
        fetch.fetch_scoreboard = scoreboard
        r = run(BOTH_DAY, self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertIn("Not final (D1 men): Small State at Big State — live.", r.warnings)

    def test_zero_d1_games_warning_names_division(self):
        fetch = make_fetch()
        board = fetch.fetch_scoreboard
        fetch.fetch_scoreboard = lambda g, d, division="d2": (
            [] if division == "d1" else board(g, d, division))
        r = run(BOTH_DAY, self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertIn("Division I: No men's games found for 2026-11-23 — verify on ncaa.com.",
                      r.warnings)


    def _flag_games_failing_for(self, division, exc):
        real = main_module.flag_games

        def fake(games, ranks, conferences, div):
            if div == division:
                raise exc
            return real(games, ranks, conferences, div)
        return mock.patch("upsets.main.flag_games", fake)

    def test_d1_slot_crash_keeps_d2_flags(self):
        with self._flag_games_failing_for("d1", RuntimeError("bad rank data\nmore")):
            r = run(BOTH_DAY, self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertEqual(r.status, "Failed")
        self.assertEqual(r.flags[("d1", "men")], [])
        self.assertEqual(r.flags[("d1", "women")], [])
        self.assertEqual(_flags(r, ("d2", "men")), D2_MEN_FLAGS)
        self.assertEqual(_flags(r, ("d2", "women")), D2_WOMEN_FLAGS)
        self.assertIn("Division I: Men couldn't be checked — unexpected error: "
                      "RuntimeError: bad rank data. Other divisions' results are still shown.",
                      r.warnings)
        self.assertTrue(any(w.startswith("Division I: Women couldn't be checked")
                            for w in r.warnings))
        self.assertTrue(r.polls_used.startswith("D1: Men AP thru Nov 22 · Women AP"))

    def test_d2_slot_crash_keeps_d1_flags(self):
        n = FakeNotion()
        with self._flag_games_failing_for("d2", ValueError("odd")):
            r = run(BOTH_DAY, self.root, dry_run=False, fetch=make_fetch(), notion=n)
        self.assertEqual(r.status, "Failed")
        self.assertEqual(n.reports, [r])
        self.assertEqual(len(r.flags[("d1", "men")]), 1)
        self.assertEqual(len(r.flags[("d1", "women")]), 1)
        self.assertEqual(r.flags[("d2", "men")], [])
        self.assertTrue(any(w.startswith("Division II: Men couldn't be checked — "
                                         "unexpected error: ValueError: odd")
                            for w in r.warnings))
        # The crashed slots add nothing to their roster; D1's still saves.
        self.assertFalse((self.root / "data" / "teams.json").exists()
                         and json.loads((self.root / "data" / "teams.json").read_text())
                         ["men"])
        d1 = json.loads((self.root / "data" / "teams_d1.json").read_text())
        self.assertIn("little-u", d1["men"])

    def test_slot_crash_in_scoreboard_fetch_is_contained(self):
        fetch = make_fetch()
        board = fetch.fetch_scoreboard

        def scoreboard(gender, day, division="d2"):
            if division == "d1" and gender == "women":
                raise KeyError("games")
            return board(gender, day, division)
        fetch.fetch_scoreboard = scoreboard
        r = run(BOTH_DAY, self.root, dry_run=True, fetch=fetch, notion=None)
        self.assertTrue(r.fatal)
        self.assertEqual(len(r.flags[("d1", "men")]), 1)
        self.assertEqual(_flags(r, ("d2", "men")), D2_MEN_FLAGS)
        self.assertIn("D1: Men AP thru Nov 22 · Women n/a | D2:", r.polls_used)

    def test_keyboard_interrupt_in_slot_is_not_swallowed(self):
        with self._flag_games_failing_for("d1", KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                run(BOTH_DAY, self.root, dry_run=True, fetch=make_fetch(), notion=None)

    def test_slot_crash_message_hides_secrets(self):
        out, err = io.StringIO(), io.StringIO()
        n = FakeNotion()
        with self._flag_games_failing_for("d1", RuntimeError("tok secret_tok_123 db_456")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(["--date", BOTH_DAY.isoformat()], fetch=make_fetch(), root=self.root,
                      notion_factory=lambda token, db: n, env=FAKE_ENV)
        self.assertEqual(rc, 1)
        r = n.reports[0]
        self.assertEqual(_flags(r, ("d2", "men")), D2_MEN_FLAGS)
        self.assertIn("Division I: Men couldn't be checked — unexpected error: "
                      "RuntimeError: tok *** ***. Other divisions' results are still shown.",
                      r.warnings)
        text = out.getvalue() + err.getvalue() + "\n".join(r.warnings)
        self.assertNotIn("secret_tok_123", text)
        self.assertNotIn("db_456", text)


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
        # A crash outside any one division's checks (here: loading the rosters).
        fetch = make_fetch()

        def boom(*args, **kwargs):
            raise RuntimeError("kaboom secret_tok_123 here\nsecond line")
        n = FakeNotion()
        with mock.patch("upsets.main.load_roster", boom):
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
        n = FakeNotion(fail=NotionError("Notion 503: down"))
        with mock.patch("upsets.main.load_roster", lambda *a, **k: 1 / 0):
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
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertEqual(len(self._gvsu_warnings(r)), 1)

    def test_known_team_off_today_gets_no_warning(self):
        self._aliases_without_not_same()
        (self.root / "data").mkdir()
        (self.root / "data" / "teams.json").write_text(json.dumps(
            {"men": {}, "women": {"grand-valley-st": "Grand Valley State"}}), encoding="utf-8")
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertEqual(self._gvsu_warnings(r), [])

    def test_real_run_saves_roster(self):
        run_d2(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(), notion=FakeNotion())
        saved = json.loads((self.root / "data" / "teams.json").read_text())
        self.assertEqual(saved["men"]["ala-huntsville"], "UAH")
        self.assertIn("fort-valley-st", saved["women"])

    def test_dry_run_does_not_touch_roster(self):
        run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertFalse((self.root / "data" / "teams.json").exists())

    def test_corrupt_roster_warns_and_run_continues(self):
        (self.root / "data").mkdir()
        (self.root / "data" / "teams.json").write_text("{nope", encoding="utf-8")
        r = run_d2(date(2026, 11, 21), self.root, dry_run=True, fetch=make_fetch(), notion=None)
        self.assertTrue(any("teams.json couldn't be read" in w for w in r.warnings))
        self.assertFalse(r.fatal)

    def test_roster_grows_across_runs(self):
        run_d2(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(), notion=FakeNotion())
        first = json.loads((self.root / "data" / "teams.json").read_text())
        run_d2(date(2026, 11, 21), self.root, dry_run=False, fetch=make_fetch(), notion=FakeNotion())
        self.assertEqual(json.loads((self.root / "data" / "teams.json").read_text()), first)

    def test_dry_run_returns_0_without_notion(self):
        def no_factory(token, db):
            raise AssertionError("no Notion in dry run")
        rc = main(["--date", "2026-11-21", "--dry-run"], fetch=make_fetch(), root=self.root,
                  notion_factory=no_factory, env={})
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
