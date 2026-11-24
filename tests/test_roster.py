from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from upsets.models import Game, Team
from upsets.roster import add_games, empty_roster, load_roster, roster_path, save_roster


def team(seo, name):
    return Team(seo=seo, name=name, score=None, winner=False, conference="")


def game(a, b):
    return Game("1", "men", a, b, "pre", "", "/x")


class RosterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_missing_file_is_empty_without_warning(self):
        warnings = []
        self.assertEqual(load_roster(self.root, warnings), empty_roster())
        self.assertEqual(warnings, [])

    def test_roundtrip(self):
        r = empty_roster()
        add_games(r, "men", [game(team("b-seo", "B"), team("a-seo", "A"))])
        add_games(r, "women", [game(team("c-seo", "C"), team("d-seo", "D"))])
        save_roster(r, self.root)
        self.assertEqual(load_roster(self.root, []), r)
        text = roster_path(self.root).read_text(encoding="utf-8")
        self.assertLess(text.index("a-seo"), text.index("b-seo"))  # sorted, tidy diffs

    def test_add_games_merges_latest_name_and_skips_blank_seo(self):
        r = empty_roster()
        r["men"]["nova-southeastern"] = "Nova Southeastern"
        added = add_games(r, "men", [game(team("nova-southeastern", "Nova Southeastern Univ"),
                                          team("", "Shawnee State"))])
        self.assertEqual(r["men"], {"nova-southeastern": "Nova Southeastern Univ"})
        self.assertEqual(added, 0)

    def test_add_games_counts_new_teams(self):
        r = empty_roster()
        self.assertEqual(add_games(r, "men", [game(team("a", "A"), team("b", "B"))]), 2)
        self.assertEqual(add_games(r, "men", [game(team("a", "A"), team("c", "C"))]), 1)

    def test_corrupt_file_warns_and_is_empty(self):
        path = roster_path(self.root)
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        warnings = []
        self.assertEqual(load_roster(self.root, warnings), empty_roster())
        self.assertEqual(len(warnings), 1)
        self.assertIn("teams.json", warnings[0])

    def test_wrong_shape_warns_and_is_empty(self):
        path = roster_path(self.root)
        path.parent.mkdir(parents=True)
        for bad in ([], {"men": []}, {"men": {"a": 1}}):
            path.write_text(json.dumps(bad), encoding="utf-8")
            warnings = []
            self.assertEqual(load_roster(self.root, warnings), empty_roster(), bad)
            self.assertEqual(len(warnings), 1, bad)

    def test_roster_paths_by_division(self):
        self.assertEqual(roster_path(self.root), self.root / "data" / "teams.json")
        self.assertEqual(roster_path(self.root, "d2"), self.root / "data" / "teams.json")
        self.assertEqual(roster_path(self.root, "d1"), self.root / "data" / "teams_d1.json")

    def test_d1_roster_is_separate_from_d2(self):
        d2 = empty_roster()
        add_games(d2, "men", [game(team("a-seo", "A"), team("b-seo", "B"))])
        d1 = empty_roster()
        add_games(d1, "men", [game(team("uconn", "UConn"), team("duke", "Duke"))])
        save_roster(d2, self.root)
        save_roster(d1, self.root, "d1")
        self.assertEqual(load_roster(self.root, []), d2)
        self.assertEqual(load_roster(self.root, [], "d1"), d1)
        self.assertNotIn("uconn", load_roster(self.root, [])["men"])

    def test_d1_missing_file_is_empty_without_warning(self):
        save_roster(empty_roster(), self.root)  # only D2's file exists
        warnings = []
        self.assertEqual(load_roster(self.root, warnings, "d1"), empty_roster())
        self.assertEqual(warnings, [])

    def test_d1_corrupt_file_warning_names_its_file(self):
        path = roster_path(self.root, "d1")
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        warnings = []
        self.assertEqual(load_roster(self.root, warnings, "d1"), empty_roster())
        self.assertEqual(len(warnings), 1)
        self.assertIn("teams_d1.json", warnings[0])


if __name__ == "__main__":
    unittest.main()
