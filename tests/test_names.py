from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from upsets.models import Game, Poll, PollEntry, Team
from upsets.names import build_rank_map, load_aliases, normalize
from upsets.sources import parse_nabc, parse_scoreboard, parse_wbca

FIX = Path(__file__).parent / "fixtures"
ALIASES = Path(__file__).parent.parent / "aliases.json"


def jload(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def team(seo, name):
    return Team(seo=seo, name=name, score=None, winner=False, conference="")


def game(*teams):
    return Game("1", "men", teams[0], teams[1], "pre", "", "/x")


def poll(*entries, gender="men"):
    return Poll(gender, "t", date(2026, 11, 15),
                [PollEntry(r, n) for r, n in entries], "src", "label")


class NamesTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("Grand Valley State"), "grand valley st")
        self.assertEqual(normalize("Grand Valley St."), "grand valley st")
        self.assertEqual(normalize("Texas Woman’s"), "texas womans")

    def test_matches_real_fixture(self):
        p = parse_nabc(jload("nabc_2026-11-15.json"))
        games = parse_scoreboard(jload("scoreboard_men_2026-11-21.json"), "men")
        rank_map, _ = build_rank_map(p, games, {})
        self.assertEqual(rank_map["gannon"], 1)
        self.assertEqual(rank_map["cal-st-east-bay"], 2)

    def test_alias_used(self):
        p = parse_wbca((FIX / "wbca_2026-11-17.html").read_text(encoding="utf-8"))
        games = parse_scoreboard(jload("scoreboard_women_2026-11-21.json"), "women")
        aliases = load_aliases(ALIASES)["women"]
        rank_map, _ = build_rank_map(p, games, aliases)
        self.assertEqual(rank_map["winston-salem"], 7)

    def test_near_miss_warns(self):
        g = [game(team("cal-st-east-bay", "Cal St. East Bay"), team("other", "Zzz"))]
        rank_map, warnings = build_rank_map(poll((1, "Cal State Eastbay")), g, {})
        self.assertEqual(rank_map, {})
        self.assertEqual(len(warnings), 1)
        self.assertIn("Cal State Eastbay", warnings[0])
        self.assertIn("cal-st-east-bay", warnings[0])
        self.assertIn("(men)", warnings[0])

    def test_absent_team_no_warning(self):
        g = [game(team("a", "Alpha Univ"), team("b", "Bravo Tech"))]
        rank_map, warnings = build_rank_map(poll((1, "Quincy")), g, {})
        self.assertEqual((rank_map, warnings), ({}, []))

    def test_matched_team_not_near_miss_candidate(self):
        g = [game(team("grand-valley-st", "Grand Valley St."), team("z", "Zzz"))]
        rank_map, warnings = build_rank_map(
            poll((1, "Grand Valley State"), (2, "Grand Valley St")), g, {})
        self.assertEqual(rank_map, {"grand-valley-st": 1})
        self.assertEqual(warnings, [])

    def test_seo_match(self):
        g = [game(team("grand-valley-st", "GVSU"), team("z", "Zzz"))]
        rank_map, _ = build_rank_map(poll((3, "Grand Valley State")), g, {})
        self.assertEqual(rank_map, {"grand-valley-st": 3})


if __name__ == "__main__":
    unittest.main()
