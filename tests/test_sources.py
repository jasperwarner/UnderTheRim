from __future__ import annotations

import copy
import json
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from upsets.models import Poll, PollEntry
from upsets.sources import (ParseError, _check_poll, fetch_poll, fetch_scoreboard,
                            parse_ap, parse_boxscore, parse_nabc, parse_scoreboard,
                            parse_wbca)

FIX = Path(__file__).parent / "fixtures"


def jload(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class SourcesTest(unittest.TestCase):
    def setUp(self):
        self.games = parse_scoreboard(jload("scoreboard_men_2026-11-21.json"), "men")
        self.by_id = {g.game_id: g for g in self.games}

    def test_men_scoreboard_counts(self):
        self.assertEqual(len(self.games), 110)
        self.assertEqual(sum(g.is_final for g in self.games), 109)
        self.assertEqual(sum(g.overtime for g in self.games), 4)

    def test_game_fields(self):
        # The brief's game 6677046 (neb-kearney 78, regis-co 69) is not in the
        # scoreboard fixture (it only appears as a box score), so use a real
        # game that is.
        g = self.by_id["6665366"]
        self.assertEqual(g.home.seo, "cal-poly-pomona")
        self.assertEqual(g.home.score, 63)
        self.assertFalse(g.home.winner)
        self.assertEqual(g.home.conference, "ccaa")
        self.assertEqual(g.away.seo, "hawaii-pacific")
        self.assertEqual(g.away.score, 69)
        self.assertTrue(g.away.winner)
        self.assertEqual(g.period, "FINAL")
        self.assertEqual(g.link, "https://www.ncaa.com/game/6665366")

    def test_blank_score_is_not_final(self):
        g = self.by_id["6679563"]
        self.assertFalse(g.is_final)
        self.assertIsNone(g.home.score)
        self.assertIsNone(g.away.score)

    def test_non_d2_conference_blank(self):
        g = self.by_id["6679563"]
        self.assertEqual(g.away.seo, "selma")
        self.assertEqual(g.away.conference, "")

    def test_nabc(self):
        p = parse_nabc(jload("nabc_2026-11-15.json"))
        self.assertEqual(len(p.entries), 25)
        self.assertEqual(p.entries[0], PollEntry(1, "Gannon"))
        self.assertEqual(p.as_of, date(2026, 11, 15))
        self.assertEqual(p.label, "NABC thru Nov 15")
        self.assertFalse(any("(" in e.name for e in p.entries))

    def test_wbca(self):
        p = parse_wbca((FIX / "wbca_2026-11-17.html").read_text(encoding="utf-8"))
        self.assertEqual(len(p.entries), 25)
        self.assertEqual(p.entries[0], PollEntry(1, "Grand Valley State"))
        self.assertEqual({e.rank: e.name for e in p.entries}[3], "Indiana, PA")
        self.assertEqual(p.as_of, date(2026, 11, 16))
        self.assertEqual(p.label, "WBCA Nov 17")

    def test_wbca_without_table_raises(self):
        with self.assertRaises(ParseError):
            parse_wbca("<html>nothing</html>")

    def test_wbca_wrong_row_count_raises(self):
        rows = "".join(f"<tr><td>{i}</td><td>Team{i} (1-0)</td></tr>" for i in range(1, 4))
        with self.assertRaises(ParseError):
            parse_wbca(f"<table><tr><td>Rank</td><td>School</td></tr>{rows}</table> 11/17/2026")

    def test_boxscore(self):
        lines = parse_boxscore(jload("boxscore_6677046.json"))
        self.assertTrue(lines)
        self.assertTrue({l.team_seo for l in lines} <= {"neb-kearney", "regis-co"})
        self.assertEqual(max(l.points for l in lines), 19)


    def test_empty_day_response_is_zero_games(self):
        # Exact body the live API returned for men's D2 on 2026-08-01 (HTTP 200).
        body = {"inputMD5Sum": "d751713988987e9331980363e24189ce",
                "instanceId": "d41d8cd98f00b204e9800998ecf8427e",
                "updated_at": "2026-11-24 02:32:30", "games": []}
        self.assertEqual(parse_scoreboard(body, "men"), [])


def nabc_with(ranks):
    d = jload("nabc_2026-11-15.json")
    d["data"] = [dict(d["data"][0], RANK=r, **{"SCHOOL (1ST VOTES)": f"Team {i}"})
                 for i, r in enumerate(ranks)]
    return d


def wbca_with(ranks, header=True):
    head = "<tr><td>Rank</td><td>School (record)</td></tr>" if header else ""
    rows = "".join(f"<tr><td>{r}</td><td>Team{i} (1-0)</td></tr>" for i, r in enumerate(ranks))
    return f"<p>11/17/2026</p><table>{head}{rows}</table>"


TOP25 = [str(i) for i in range(1, 26)]


class PollTiesAndSanityTest(unittest.TestCase):
    def test_nabc_ties(self):
        ranks = TOP25[:22] + ["T-23", "T23", "23T"]
        p = parse_nabc(nabc_with(ranks))
        self.assertEqual([e.rank for e in p.entries][-3:], [23, 23, 23])

    def test_wbca_ties(self):
        ranks = TOP25[:22] + ["T-23", "T23", "23T"]
        p = parse_wbca(wbca_with(ranks))
        self.assertEqual([e.rank for e in p.entries][-3:], [23, 23, 23])
        self.assertEqual(len(p.entries), 25)

    def test_wbca_unreadable_rank_is_error_not_skipped(self):
        with self.assertRaises(ParseError):
            parse_wbca(wbca_with(TOP25[:24] + ["25?x"]))

    def test_wbca_header_rows_skipped(self):
        html_text = wbca_with(TOP25).replace(
            "</table>", "<tr><td>Others receiving votes</td><td>-</td></tr></table>")
        self.assertEqual(len(parse_wbca(html_text).entries), 25)

    def test_too_few_entries_raise(self):
        with self.assertRaises(ParseError):
            parse_nabc(nabc_with(TOP25[:24]))
        with self.assertRaises(ParseError):
            parse_wbca(wbca_with(TOP25[:24]))

    def test_must_start_at_1(self):
        shifted = [str(i) for i in range(2, 27)]
        with self.assertRaises(ParseError):
            parse_nabc(nabc_with(shifted))
        with self.assertRaises(ParseError):
            parse_wbca(wbca_with(shifted))


class ParserRobustnessTest(unittest.TestCase):
    def assertParseError(self, fn, *args):
        with self.assertRaises(ParseError):
            fn(*args)

    def test_scoreboard_bad_shapes(self):
        good = jload("scoreboard_men_2026-11-21.json")
        bad_team = copy.deepcopy(good)
        bad_team["games"][0]["game"]["home"]["conferences"] = ["x"]
        bad_name = copy.deepcopy(good)
        bad_name["games"][0]["game"]["home"]["names"]["short"] = 5
        for data in ([], {"games": None}, {"games": [1]}, {"games": [{"game": []}]},
                     bad_team, bad_name, "text"):
            self.assertParseError(parse_scoreboard, data, "men")

    def test_nabc_bad_shapes(self):
        good = jload("nabc_2026-11-15.json")
        bad_date = dict(good, updated="Through Games NOV. 45, 2026")
        bad_rank = copy.deepcopy(good)
        bad_rank["data"][0]["RANK"] = "one"
        bad_school = copy.deepcopy(good)
        bad_school["data"][0]["SCHOOL (1ST VOTES)"] = None
        for data in ([], {"updated": 5}, dict(good, data=None), bad_date, bad_rank,
                     bad_school, "text"):
            self.assertParseError(parse_nabc, data)

    def test_wbca_bad_inputs(self):
        good = (FIX / "wbca_2026-11-17.html").read_text(encoding="utf-8")
        self.assertParseError(parse_wbca, None)
        self.assertParseError(parse_wbca, good.replace("11/17/2026", "13/45/2026"))

    def test_boxscore_bad_shapes(self):
        good = jload("boxscore_6677046.json")
        bad_player = copy.deepcopy(good)
        bad_player["teamBoxscore"][0]["playerStats"] = ["x"]
        bad_team = copy.deepcopy(good)
        bad_team["teamBoxscore"][0]["teamId"] = "nope"
        for data in ([], {"teams": None}, bad_player, bad_team, "text"):
            self.assertParseError(parse_boxscore, data)

    def test_full_boxscore_fixture_sums_to_score(self):
        lines = parse_boxscore(jload("boxscore_6665635.json"))
        totals = {}
        for l in lines:
            totals[l.team_seo] = totals.get(l.team_seo, 0) + l.points
        self.assertEqual(totals, {"minn-st-mankato": 79, "northern-mich": 77})


class ParseApTest(unittest.TestCase):
    def test_men_poll(self):
        p = parse_ap(jload("ap_men_2026-11-22.json"), "men")
        self.assertEqual(len(p.entries), 25)
        self.assertEqual(p.entries[0], PollEntry(1, "Houston", "6-0"))
        self.assertEqual(p.gender, "men")
        self.assertEqual(p.as_of, date(2026, 11, 22))
        self.assertEqual(p.label, "AP thru Nov 22")
        self.assertEqual(p.division, "d1")
        self.assertEqual(p.entries[0].record, "6-0")
        self.assertEqual(p.source,
                         "https://ncaa-api.henrygd.me/rankings/basketball-men/d1/associated-press")

    def test_women_poll(self):
        p = parse_ap(jload("ap_women_2026-11-22.json"), "women")
        self.assertEqual(len(p.entries), 25)
        self.assertEqual(p.entries[0].name, "South Carolina")
        self.assertEqual(p.division, "d1")
        self.assertTrue(p.source.endswith("/rankings/basketball-women/d1/associated-press"))

    def test_school_with_parenthesis_kept(self):
        names = {e.name for e in parse_ap(jload("ap_men_2026-11-22.json"), "men").entries}
        self.assertIn("Miami (FL)", names)
        self.assertIn("Houston", names)
        self.assertNotIn("Houston (55)", names)
        d = jload("ap_men_2026-11-22.json")
        d["data"][0]["SCHOOL"] = "Miami (FL) (12)"
        self.assertEqual(parse_ap(d, "men").entries[0].name, "Miami (FL)")

    def test_ap_bad_shape_raises_parse_error(self):
        good = jload("ap_men_2026-11-22.json")
        bad_date = dict(good, updated="Through Games NOV. 45, 2026")
        bad_rank = copy.deepcopy(good)
        bad_rank["data"][0]["RANK"] = "one"
        bad_school = copy.deepcopy(good)
        bad_school["data"][0]["SCHOOL"] = None
        bad_record = copy.deepcopy(good)
        bad_record["data"][0]["RECORD"] = 6
        for data in ([], {"updated": 5}, dict(good, data=None), bad_date, bad_rank,
                     bad_school, bad_record, "text"):
            with self.assertRaises(ParseError):
                parse_ap(data, "men")

    def test_ap_too_few_entries_raises(self):
        d = jload("ap_men_2026-11-22.json")
        d["data"] = d["data"][:24]
        with self.assertRaises(ParseError):
            parse_ap(d, "men")
        with self.assertRaises(ParseError):
            _check_poll([PollEntry(i, f"T{i}") for i in range(1, 25)], "AP poll")


class ParseScoreboardDivisionTest(unittest.TestCase):
    def test_d1_division_set(self):
        games = parse_scoreboard(jload("scoreboard_d1_men_2026-11-23.json"), "men", "d1")
        self.assertEqual(len(games), 46)
        self.assertTrue(all(g.division == "d1" for g in games))

    def test_d2_division_is_default(self):
        games = parse_scoreboard(jload("scoreboard_men_2026-11-21.json"), "men")
        self.assertTrue(games)
        self.assertTrue(all(g.division == "d2" for g in games))


class PollJsonTest(unittest.TestCase):
    def test_old_saved_poll_still_loads(self):
        old = {"gender": "men", "title": "NABC Coaches", "as_of": "2026-11-15",
               "entries": [{"rank": 1, "name": "Gannon"}],
               "source": "x", "label": "NABC thru Nov 15"}
        p = Poll.from_json(old)
        self.assertEqual(p.division, "d2")
        self.assertEqual(p.entries[0].record, "")
        self.assertEqual(p.entries[0], PollEntry(1, "Gannon"))

    def test_d2_json_has_no_record_key(self):
        p = Poll("men", "t", date(2026, 11, 15), [PollEntry(1, "Gannon")], "x", "l")
        out = p.to_json()
        self.assertEqual(out["division"], "d2")
        self.assertEqual(out["entries"], [{"rank": 1, "name": "Gannon"}])

    def test_d1_round_trip_keeps_division_and_record(self):
        p = parse_ap(jload("ap_men_2026-11-22.json"), "men")
        again = Poll.from_json(json.loads(json.dumps(p.to_json())))
        self.assertEqual(again, p)
        self.assertEqual(again.division, "d1")
        self.assertEqual(again.entries[0].record, "6-0")

    def test_non_string_record_is_parse_error(self):
        d = parse_ap(jload("ap_men_2026-11-22.json"), "men").to_json()
        d["entries"][0]["record"] = 6
        with self.assertRaises(ParseError):
            Poll.from_json(d)
        d = parse_ap(jload("ap_men_2026-11-22.json"), "men").to_json()
        d["division"] = 1
        with self.assertRaises(ParseError):
            Poll.from_json(d)


class FetchUrlTest(unittest.TestCase):
    def test_d1_scoreboard_url(self):
        with mock.patch("upsets.sources.get_json", return_value={"games": []}) as gj:
            self.assertEqual(fetch_scoreboard("men", date(2026, 11, 23), "d1"), [])
        gj.assert_called_once_with(
            "https://ncaa-api.henrygd.me/scoreboard/basketball-men/d1/2026/11/23/all-conf")

    def test_d2_scoreboard_url_unchanged(self):
        with mock.patch("upsets.sources.get_json", return_value={"games": []}) as gj:
            fetch_scoreboard("women", date(2026, 11, 23))
        gj.assert_called_once_with(
            "https://ncaa-api.henrygd.me/scoreboard/basketball-women/d2/2026/11/23/all-conf")

    def test_d1_women_poll_url(self):
        with mock.patch("upsets.sources.get_json",
                        return_value=jload("ap_women_2026-11-22.json")) as gj:
            p = fetch_poll("women", "d1")
        gj.assert_called_once_with(
            "https://ncaa-api.henrygd.me/rankings/basketball-women/d1/associated-press")
        self.assertEqual(p.division, "d1")

    def test_d2_men_poll_url_unchanged(self):
        with mock.patch("upsets.sources.get_json",
                        return_value=jload("nabc_2026-11-15.json")) as gj:
            fetch_poll("men")
        gj.assert_called_once_with(
            "https://ncaa-api.henrygd.me/rankings/basketball-men/d2/nabc-coaches")


if __name__ == "__main__":
    unittest.main()
