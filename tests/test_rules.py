from __future__ import annotations

import unittest

from upsets.models import Flag, Game, PlayerLine, Team
from upsets.rules import add_big_scorers, boxscore_complete, flag_games


def g(home_seo, hs, away_seo, as_, period="FINAL", state="final", conf="gsc",
      home_conf=None, away_conf=None):
    home = Team(home_seo, home_seo, hs, (hs or 0) > (as_ or 0),
                conf if home_conf is None else home_conf)
    away = Team(away_seo, away_seo, as_, (as_ or 0) > (hs or 0),
                conf if away_conf is None else away_conf)
    return Game("1", "men", home, away, state, period, "/game/1")


class FlagGamesTest(unittest.TestCase):
    def test_ranked_loses_to_unranked(self):
        flags = flag_games([g("a", 71, "b", 68)], {"b": 7})
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].tags, ["Upset", "Close (3 pts)"])
        self.assertEqual(flags[0].headline, "Unranked a beat No. 7 b, 71-68")

    def test_rank_gap(self):
        flags = flag_games([g("a", 80, "b", 70)], {"a": 18, "b": 4})
        self.assertEqual(flags[0].tags, ["Big rank gap"])
        self.assertEqual(flag_games([g("a", 80, "b", 70)], {"a": 13, "b": 4}), [])

    def test_favorite_survives_ot(self):
        flags = flag_games([g("a", 70, "b", 68, period="FINAL - OT")], {"a": 5})
        self.assertEqual(flags[0].tags, ["Close (2 pts)", "Overtime"])
        self.assertEqual(flags[0].headline, "No. 5 a beat b, 70-68")

    def test_one_point_singular(self):
        flags = flag_games([g("a", 88, "b", 87)], {"a": 7})
        self.assertEqual(flags[0].tags, ["Close (1 pt)"])

    def test_unranked_close_not_flagged(self):
        self.assertEqual(flag_games([g("a", 60, "b", 59)], {}), [])

    def test_non_final_never_flagged(self):
        game = g("a", None, "b", None, period="", state="pre")
        self.assertEqual(flag_games([game], {"b": 1}), [])

    def test_tied_scores_skipped(self):
        self.assertEqual(flag_games([g("a", 60, "b", 60)], {"b": 1}), [])

    def test_non_d2_label(self):
        game = g("a", 70, "b", 60, home_conf="")
        flags = flag_games([game], {"b": 3})
        self.assertEqual(flags[0].tags[-1], "Non-D2 opponent")
        self.assertEqual(flags[0].tags, ["Upset", "Non-D2 opponent"])

    def test_non_d2_by_conference_list(self):
        d2 = {"gsc", "sac"}
        game = g("a", 70, "b", 60, home_conf="asun", away_conf="sac")
        flags = flag_games([game], {"b": 3}, d2)
        self.assertEqual(flags[0].tags, ["Upset", "Non-D2 opponent"])
        flags = flag_games([g("a", 70, "b", 60, away_conf="sac")], {"b": 3}, d2)
        self.assertEqual(flags[0].tags, ["Upset"])
        flags = flag_games([g("a", 70, "b", 60, home_conf="")], {"b": 3}, d2)
        self.assertEqual(flags[0].tags, ["Upset", "Non-D2 opponent"])

    def test_without_list_only_blank_is_non_d2(self):
        game = g("a", 70, "b", 60, home_conf="asun")
        self.assertEqual(flag_games([game], {"b": 3})[0].tags, ["Upset"])

    def test_real_conference_file(self):
        import json
        from pathlib import Path
        d2 = set(json.loads((Path(__file__).resolve().parent.parent
                             / "d2_conferences.json").read_text()))
        for non in ("acc", "asun", "america-east", "saa", "sciac", "diii-independent",
                    "nwc", "usa-south", "umac", ""):
            self.assertNotIn(non, d2)
        for yes in ("psac", "gliac", "gac", "dii-independent", "sac", "siac"):
            self.assertIn(yes, d2)
        game = g("queens-nc", 70, "b", 60, home_conf="asun", away_conf="sac")
        self.assertIn("Non-D2 opponent", flag_games([game], {"b": 3}, d2)[0].tags)

    def test_non_d2_alone_not_flagged(self):
        self.assertEqual(flag_games([g("a", 70, "b", 60, home_conf="")], {}), [])

    def test_order_preserved(self):
        games = [g("a", 71, "b", 68), g("c", 50, "d", 40), g("e", 80, "f", 70)]
        flags = flag_games(games, {"b": 7, "f": 2})
        self.assertEqual([f.game for f in flags], [games[0], games[2]])


class BoxscoreCompleteTest(unittest.TestCase):
    def test_complete(self):
        game = g("a", 71, "b", 68)
        self.assertTrue(boxscore_complete(game, [PlayerLine("x", "a", 70), PlayerLine("y", "a", 1),
                                                 PlayerLine("z", "b", 68)]))

    def test_sum_short(self):
        game = g("a", 71, "b", 68)
        self.assertFalse(boxscore_complete(game, [PlayerLine("x", "a", 44),
                                                  PlayerLine("z", "b", 68)]))

    def test_team_missing(self):
        game = g("a", 71, "b", 68)
        self.assertFalse(boxscore_complete(game, [PlayerLine("x", "a", 71)]))
        self.assertFalse(boxscore_complete(game, []))


class BigScorerTest(unittest.TestCase):
    def test_big_scorer(self):
        flag = Flag(g("a", 71, "b", 68), "h", ["Upset"])
        add_big_scorers(flag, [PlayerLine("Zeek Brown", "a", 38),
                               PlayerLine("X", "b", 34)])
        self.assertEqual(flag.tags[-1], "35+ pts: Zeek Brown 38 (a)")
        self.assertEqual(sum(t.startswith("35+") for t in flag.tags), 1)


if __name__ == "__main__":
    unittest.main()
