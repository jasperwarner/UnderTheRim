from __future__ import annotations

import unittest

from upsets.models import Flag, Game, PlayerLine, Team
from upsets.rules import add_big_scorers, flag_games


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

    def test_non_d2_alone_not_flagged(self):
        self.assertEqual(flag_games([g("a", 70, "b", 60, home_conf="")], {}), [])

    def test_order_preserved(self):
        games = [g("a", 71, "b", 68), g("c", 50, "d", 40), g("e", 80, "f", 70)]
        flags = flag_games(games, {"b": 7, "f": 2})
        self.assertEqual([f.game for f in flags], [games[0], games[2]])


class BigScorerTest(unittest.TestCase):
    def test_big_scorer(self):
        flag = Flag(g("a", 71, "b", 68), "h", ["Upset"])
        add_big_scorers(flag, [PlayerLine("Zeek Brown", "a", 38),
                               PlayerLine("X", "b", 34)])
        self.assertEqual(flag.tags[-1], "35+ pts: Zeek Brown 38 (a)")
        self.assertEqual(sum(t.startswith("35+") for t in flag.tags), 1)


if __name__ == "__main__":
    unittest.main()
