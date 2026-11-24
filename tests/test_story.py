from __future__ import annotations

import unittest

from upsets.models import Flag, Game, PlayerLine, Team
from upsets.rules import add_big_scorers, flag_games
from upsets.story import BIG_AT, STRONG_AT, rate_story, story_points


def g(home_seo, hs, away_seo, as_, period="FINAL", conf="x"):
    home = Team(home_seo, home_seo.upper(), hs, hs > as_, conf)
    away = Team(away_seo, away_seo.upper(), as_, as_ > hs, conf)
    return Game("1", "men", home, away, "final", period, "/game/1")


def direct(tags=(), winner_rank=None, loser_rank=None, division="d2"):
    return Flag(g("a", 70, "b", 60), "h", list(tags), division=division,
                winner_rank=winner_rank, loser_rank=loser_rank)


class StoryTest(unittest.TestCase):
    def test_constants(self):
        self.assertEqual((STRONG_AT, BIG_AT), (4, 6))

    def test_big_story(self):
        game = g("a", 80, "b", 75, period="FINAL - 2OT")
        flag = flag_games([game], {"b": 3}, None, division="d1")[0]
        rate_story(flag, {}, [])
        self.assertEqual(flag.story_points, 7)  # 2 + 3 + 1 (OT) + 1 (D1)
        self.assertEqual(flag.story, "Big story")

    def test_strong_story(self):
        flag = flag_games([g("a", 70, "b", 68)], {"b": 8})[0]
        rate_story(flag, {}, [])
        self.assertEqual(flag.story_points, 5)  # 2 + 2 + 1 (close)
        self.assertEqual(flag.story, "Strong story")

    def test_boundaries(self):
        cases = [
            (direct(loser_rank=12), 3, ""),
            (direct(loser_rank=8), 4, "Strong story"),
            (direct(["Overtime"], loser_rank=8), 5, "Strong story"),
            (direct(["Overtime"], loser_rank=3), 6, "Big story"),
        ]
        for flag, points, label in cases:
            rate_story(flag, {}, [])
            self.assertEqual((flag.story_points, flag.story), (points, label))

    def test_rank_bands_and_other_points(self):
        self.assertEqual(story_points(direct(loser_rank=5)), 5)
        self.assertEqual(story_points(direct(loser_rank=6)), 4)
        self.assertEqual(story_points(direct(loser_rank=10)), 4)
        self.assertEqual(story_points(direct(loser_rank=11)), 3)
        self.assertEqual(story_points(direct(loser_rank=25)), 3)
        # ranked winner: no unranked-winner bonus, loser band still applies
        self.assertEqual(story_points(direct(["Big rank gap"], winner_rank=18, loser_rank=4)), 4)
        self.assertEqual(story_points(direct(["Close (2 pts)"], winner_rank=5)), 1)
        self.assertEqual(story_points(direct(division="d1")), 1)

    def test_35_points_can_lift_label(self):
        game = g("a", 80, "b", 70)
        flag = flag_games([game], {"b": 12})[0]
        rate_story(flag, {}, [])
        self.assertEqual((flag.story_points, flag.story), (3, ""))
        players = [PlayerLine("Zeek Brown", "a", 38), PlayerLine("Q", "a", 42),
                   PlayerLine("R", "b", 70)]
        add_big_scorers(flag, players)
        rate_story(flag, {}, players)
        self.assertEqual((flag.story_points, flag.story), (4, "Strong story"))

    def test_facts_use_poll_records_and_scorers(self):
        game = g("a", 70, "b", 60)
        flag = flag_games([game], {"b": 3})[0]
        players = [PlayerLine("Zeek Brown", "a", 40), PlayerLine("Amy Lee", "a", 30),
                   PlayerLine("Cal Ray", "b", 35), PlayerLine("Dee Fox", "b", 25)]
        rate_story(flag, {"a": "6-0"}, players)
        text = "\n".join(flag.facts)
        self.assertTrue(flag.story)
        self.assertIn("6-0", text)
        self.assertIn("70-60", text)
        self.assertIn("Zeek Brown", text)
        self.assertIn("Cal Ray", text)
        self.assertNotIn("Amy Lee", text)
        self.assertIn("unranked", text)
        self.assertIn("No. 3", text)
        self.assertNotIn("Box score incomplete", text)

    def test_tied_top_scorers_all_named(self):
        flag = flag_games([g("a", 70, "b", 60)], {"b": 3})[0]
        players = [PlayerLine("Zeek Brown", "a", 35), PlayerLine("Amy Lee", "a", 35),
                   PlayerLine("Cal Ray", "b", 60)]
        rate_story(flag, {}, players)
        text = "\n".join(flag.facts)
        self.assertIn("Zeek Brown", text)
        self.assertIn("Amy Lee", text)

    def test_missing_record_is_omitted(self):
        flag = flag_games([g("a", 70, "b", 60)], {"b": 3})[0]
        rate_story(flag, {"b": "9-1"}, [])
        text = "\n".join(flag.facts)
        self.assertIn("9-1", text)
        self.assertNotIn("None", text)
        self.assertNotIn("()", text)

    def test_overtime_fact(self):
        flag = flag_games([g("a", 80, "b", 70, period="FINAL - OT")], {"b": 3})[0]
        rate_story(flag, {}, [])
        self.assertTrue(any("overtime" in f.lower() for f in flag.facts))

    def test_incomplete_box_score_hides_scorers(self):
        flag = flag_games([g("a", 70, "b", 60)], {"b": 3})[0]
        players = [PlayerLine("Zeek Brown", "a", 40), PlayerLine("Cal Ray", "b", 35)]
        rate_story(flag, {}, players)
        self.assertIn("Box score incomplete — top scorers not shown.", flag.facts)
        text = "\n".join(flag.facts)
        self.assertNotIn("Zeek Brown", text)
        self.assertNotIn("Cal Ray", text)

    def test_no_players_is_incomplete(self):
        flag = flag_games([g("a", 70, "b", 60)], {"b": 3})[0]
        rate_story(flag, {}, [])
        self.assertEqual(flag.facts.count("Box score incomplete — top scorers not shown."), 1)

    def test_unlabeled_has_no_facts(self):
        flag = direct(loser_rank=12)
        rate_story(flag, {"a": "6-0"}, [PlayerLine("Zeek Brown", "a", 70),
                                        PlayerLine("Cal Ray", "b", 60)])
        self.assertEqual(flag.story, "")
        self.assertEqual(flag.facts, [])

    def test_rerating_resets_facts(self):
        flag = direct(["Overtime"], loser_rank=3)
        rate_story(flag, {}, [])
        self.assertTrue(flag.facts)
        flag.tags.remove("Overtime")
        flag.loser_rank = 12
        rate_story(flag, {}, [])
        self.assertEqual((flag.story, flag.facts), ("", []))


if __name__ == "__main__":
    unittest.main()
