from __future__ import annotations

import json
import tempfile
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

    def test_near_miss_uses_seo_form(self):
        g = [game(team("ala-huntsville", "UAH"), team("z", "Zzz"))]
        rank_map, warnings = build_rank_map(poll((9, "Alabama Huntsville")), g, {})
        self.assertEqual(rank_map, {})
        self.assertEqual(len(warnings), 1)
        self.assertIn('"UAH" (ala-huntsville)', warnings[0])

    def test_near_miss_wording_says_may_differ(self):
        g = [game(team("ala-huntsville", "UAH"), team("z", "Zzz"))]
        _, warnings = build_rank_map(poll((9, "Alabama Huntsville")), g, {})
        self.assertIn("looks similar to", warnings[0])
        self.assertIn("if they are the same school, add an alias; "
                      "if not, add them to not_same in aliases.json", warnings[0])

    def test_real_aliases_match_uah(self):
        al = load_aliases(ALIASES)
        g = [game(team("ala-huntsville", "UAH"), team("z", "Zzz"))]
        self.assertEqual(build_rank_map(poll((9, "Alabama Huntsville")), g, al["men"])[0],
                         {"ala-huntsville": 9})
        self.assertEqual(build_rank_map(poll((10, "Alabama-Huntsville"), gender="women"),
                                        g, al["women"])[0],
                         {"ala-huntsville": 10})

    def test_not_same_suppresses_near_miss(self):
        g = [game(team("fort-valley-st", "Fort Valley St."), team("z", "Zzz"))]
        p = poll((1, "Grand Valley State"), gender="women")
        _, warnings = build_rank_map(p, g, {}, {"Grand Valley State": ["fort-valley-st"]})
        self.assertEqual(warnings, [])
        _, warnings = build_rank_map(p, g, {}, {})
        self.assertEqual(len(warnings), 1)
        self.assertIn("Fort Valley St.", warnings[0])

    def test_not_same_only_skips_listed_pair(self):
        g = [game(team("fort-valley-st", "Fort Valley St."), team("grand-valley", "Grand Valley"))]
        _, warnings = build_rank_map(poll((1, "Grand Valley State")), g,
                                     {}, {"Grand Valley State": ["fort-valley-st"]})
        self.assertEqual(len(warnings), 1)
        self.assertIn("(grand-valley)", warnings[0])

    def test_typo_alias_falls_through_to_near_miss(self):
        g = [game(team("ala-huntsville", "UAH"), team("z", "Zzz"))]
        rank_map, warnings = build_rank_map(poll((9, "Alabama Huntsville")), g,
                                            {"Alabama Huntsville": "ala-hunstville"})
        self.assertEqual(rank_map, {})
        self.assertEqual(len(warnings), 1)
        self.assertIn("ala-huntsville", warnings[0])

    def test_alias_to_absent_team_falls_through_to_name_match(self):
        g = [game(team("grand-valley-st", "Grand Valley St."), team("z", "Zzz"))]
        rank_map, _ = build_rank_map(poll((1, "Grand Valley State")), g,
                                     {"Grand Valley State": "gvsu-typo"})
        self.assertEqual(rank_map, {"grand-valley-st": 1})

    def test_alias_key_apostrophe_insensitive(self):
        g = [game(team("twu", "Texas Woman's U"), team("z", "Zzz"))]
        rank_map, _ = build_rank_map(poll((12, "Texas Woman’s")), g,
                                     {"Texas Woman's": "twu"})
        self.assertEqual(rank_map, {"twu": 12})
        rank_map, _ = build_rank_map(poll((12, "Texas Woman's")), g,
                                     {"Texas Woman’s": "twu"})
        self.assertEqual(rank_map, {"twu": 12})

    def test_blank_seo_team_ignored(self):
        g = [game(team("", "Shawnee State "), team("gannon", "Gannon"))]
        rank_map, warnings = build_rank_map(poll((1, "Gannon"), (2, "Shawnee State")), g, {})
        self.assertEqual(rank_map, {"gannon": 1})
        self.assertEqual(warnings, [])

    def test_real_fixtures_no_near_miss_with_real_aliases(self):
        al = load_aliases(ALIASES)
        men = build_rank_map(parse_nabc(jload("nabc_2026-11-15.json")),
                             parse_scoreboard(jload("scoreboard_men_2026-11-21.json"), "men"),
                             al["men"], al["not_same"]["men"])
        women = build_rank_map(parse_wbca((FIX / "wbca_2026-11-17.html").read_text(encoding="utf-8")),
                               parse_scoreboard(jload("scoreboard_women_2026-11-21.json"), "women"),
                               al["women"], al["not_same"]["women"])
        self.assertEqual(men[1] + women[1], [])
        self.assertEqual(men[0]["ala-huntsville"], 9)
        self.assertEqual(women[0]["ala-huntsville"], 10)


class LoadAliasesTest(unittest.TestCase):
    def _load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "aliases.json"
            path.write_text(text, encoding="utf-8")
            return load_aliases(path)

    def test_shape(self):
        al = self._load(json.dumps({"men": {"A": "a"}, "women": {},
                                    "not_same": {"women": {"B": ["c"]}}}))
        self.assertEqual(al["men"], {"A": "a"})
        self.assertEqual(al["women"], {})
        self.assertEqual(al["not_same"], {"men": {}, "women": {"B": ["c"]}})

    def test_old_shape_without_not_same(self):
        al = self._load(json.dumps({"men": {"A": "a"}, "women": {"B": "b"}}))
        self.assertEqual(al["not_same"], {"men": {}, "women": {}})

    def test_bad_shapes_raise_value_error(self):
        for bad in ([1, 2], {"men": [1]}, {"men": {"A": 1}},
                    {"not_same": {"men": {"A": "a"}}}, {"not_same": []}):
            with self.assertRaises(ValueError, msg=bad):
                self._load(json.dumps(bad))

    def test_real_file_loads(self):
        al = load_aliases(ALIASES)
        self.assertEqual(al["not_same"]["women"]["Grand Valley State"], ["fort-valley-st"])


if __name__ == "__main__":
    unittest.main()
