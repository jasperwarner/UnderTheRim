from __future__ import annotations

import datetime
import json
import unittest

from upsets.models import Flag, Game, Team
from upsets.report import Report, to_json, to_notion_blocks, to_text


def make_flag(gender="men", division="d2", game_id="1", story="", facts=None):
    home = Team("a", "A", 71, True, "gsc")
    away = Team("b", "B", 68, False, "gsc")
    game = Game(game_id, gender, home, away, "final", "FINAL", "/game/" + game_id,
                division=division)
    return Flag(game, "Unranked A beat No. 7 B, 71-68", ["Upset", "Close (3 pts)"],
                division=division, story=story, facts=list(facts or []))


D2_EMPTY = {("d2", "men"): [], ("d2", "women"): []}
BOTH_EMPTY = {("d1", "men"): [], ("d1", "women"): [], ("d2", "men"): [], ("d2", "women"): []}


def make_report(flags=None, warnings=None, fatal=False, final_counts=None):
    return Report(
        day=datetime.date(2026, 11, 22),
        flags=flags if flags is not None else dict(D2_EMPTY),
        warnings=warnings or [],
        final_counts=final_counts or {("d2", "men"): 110, ("d2", "women"): 98},
        polls_used="saved 2026-11-17",
        fatal=fatal,
    )


def block_text(b):
    return "".join(t["text"]["content"] for t in b[b["type"]]["rich_text"])


class ReportTest(unittest.TestCase):
    def test_status(self):
        self.assertEqual(make_report().status, "OK")
        self.assertEqual(make_report(warnings=["x"]).status, "Check data")
        self.assertEqual(make_report(warnings=["x"], fatal=True).status, "Failed")

    def test_blocks_zero_flags(self):
        blocks = to_notion_blocks(make_report())
        self.assertTrue(block_text(blocks[0]).startswith(
            "No upsets yesterday — 110 men's and 98 women's games checked."))
        self.assertEqual(block_text(blocks[-1]), "Men: 110 final games checked · Women: 98")

    def test_blocks_flag_has_link(self):
        f = make_flag()
        blocks = to_notion_blocks(make_report({("d2", "men"): [f], ("d2", "women"): []}))
        items = [b for b in blocks if b["type"] == "bulleted_list_item"]
        self.assertEqual(len(items), 1)
        rt = items[0]["bulleted_list_item"]["rich_text"]
        self.assertEqual(rt[0]["text"]["content"], "Upset · Close (3 pts) — " + f.headline + " ")
        self.assertEqual(rt[1]["text"]["content"], "ncaa.com ↗")
        self.assertEqual(rt[1]["text"]["link"]["url"], f.game.link)
        self.assertEqual((blocks[0]["type"], block_text(blocks[0])), ("heading_2", "Division II"))
        self.assertEqual((blocks[1]["type"], block_text(blocks[1])), ("heading_3", "Men's"))
        self.assertIn("No flags.", [block_text(b) for b in blocks])

    def test_warnings_first(self):
        blocks = to_notion_blocks(make_report(warnings=["w1"]))
        self.assertEqual(blocks[0]["type"], "heading_2")
        self.assertEqual(block_text(blocks[0]), "⚠️ Data warnings")
        self.assertEqual(blocks[1]["type"], "bulleted_list_item")
        self.assertEqual(block_text(blocks[1]), "w1")
        self.assertTrue(block_text(blocks[2]).startswith("No upsets yesterday"))

    def test_json_round_trippable(self):
        r = make_report({("d2", "men"): [make_flag()], ("d2", "women"): []}, warnings=["w"])
        d = json.loads(json.dumps(to_json(r)))
        for k in ("status", "flags", "warnings", "final_counts", "day",
                  "flag_count", "polls_used", "fatal", "games"):
            self.assertIn(k, d)
        self.assertEqual(d["day"], "2026-11-22")
        self.assertEqual(d["flag_count"], 1)
        fl = d["flags"][0]
        self.assertEqual(fl["gender"], "men")
        self.assertEqual(fl["link"], "https://www.ncaa.com/game/1")
        self.assertEqual(fl["home"], {"seo": "a", "score": 71})
        self.assertEqual(fl["away"], {"seo": "b", "score": 68})
        self.assertEqual(fl["division"], "d2")
        self.assertEqual(d["final_counts"], {"d2": {"men": 110, "women": 98}})

    def test_text(self):
        t = to_text(make_report({("d2", "men"): [make_flag()], ("d2", "women"): []},
                                warnings=["w1"]))
        self.assertIn("- Upset · Close (3 pts) — Unranked A beat No. 7 B, 71-68  https://www.ncaa.com/game/1", t)
        self.assertLess(t.index("w1"), t.index("Men's"))
        self.assertIn("\nPolls used: saved 2026-11-17", t)
        self.assertTrue(t.startswith("Upsets for 2026-11-22 — Check data\n"))
        self.assertIn("\nMen: 110 final games checked · Women: 98\n", t)

    def test_json_has_games_per_gender(self):
        f = make_flag()
        r = make_report({("d2", "men"): [f], ("d2", "women"): []})
        r.games = {("d2", "men"): [f.game], ("d2", "women"): []}
        d = json.loads(json.dumps(to_json(r)))
        self.assertEqual(list(d["games"]), ["d2"])
        self.assertEqual(d["games"]["d2"]["women"], [])
        self.assertEqual(d["games"]["d2"]["men"], [{
            "id": "1", "gameState": "final", "currentPeriod": "FINAL",
            "home": {"seo": "a", "name": "A", "score": 71, "conferenceSeo": "gsc"},
            "away": {"seo": "b", "name": "B", "score": 68, "conferenceSeo": "gsc"},
        }])



def texts(blocks):
    return [(b["type"], block_text(b)) for b in blocks]


class DivisionTest(unittest.TestCase):
    def both(self):
        return make_report(
            {("d1", "men"): [make_flag(division="d1", game_id="9")], ("d1", "women"): [],
             ("d2", "men"): [make_flag()], ("d2", "women"): []},
            final_counts={("d1", "men"): 150, ("d1", "women"): 140,
                          ("d2", "men"): 110, ("d2", "women"): 98})

    def test_d2_only_shows_only_division_ii(self):
        r = make_report()
        t = to_text(r)
        self.assertIn("Division II", t)
        self.assertNotIn("Division I\n", t)
        heads = [x for x in texts(to_notion_blocks(r)) if x[0] == "heading_2"]
        self.assertEqual(heads, [("heading_2", "Division II")])

    def test_both_divisions_d1_first(self):
        r = self.both()
        heads = [x for x in texts(to_notion_blocks(r)) if x[0].startswith("heading")]
        self.assertEqual(heads, [
            ("heading_2", "Division I"), ("heading_3", "Men's"), ("heading_3", "Women's"),
            ("heading_2", "Division II"), ("heading_3", "Men's"), ("heading_3", "Women's"),
        ])
        t = to_text(r)
        self.assertLess(t.index("Division I\n"), t.index("Division II\n"))
        self.assertIn("https://www.ncaa.com/game/9", t[t.index("Division I\n"):t.index("Division II\n")])
        self.assertIn("https://www.ncaa.com/game/1", t[t.index("Division II\n"):])

    def test_both_divisions_footer(self):
        r = self.both()
        footer = ("Division I — Men: 150 final games checked · Women: 140"
                  " · Division II — Men: 110 final games checked · Women: 98")
        self.assertEqual(block_text(to_notion_blocks(r)[-1]), footer)
        self.assertIn("\n" + footer + "\n", to_text(r))

    def test_no_upsets_counts_across_divisions(self):
        r = make_report(dict(BOTH_EMPTY),
                        final_counts={("d1", "men"): 150, ("d1", "women"): 140,
                                      ("d2", "men"): 110, ("d2", "women"): 98})
        line = "No upsets yesterday — 260 men's and 238 women's games checked."
        self.assertEqual(block_text(to_notion_blocks(r)[0]), line)
        self.assertIn(line, to_text(r))

    def test_labeled_flag_shows_label_and_facts(self):
        f = make_flag(story="Big story", facts=["A: unranked", "Final: 71-68 (3 pts)"])
        r = make_report({("d2", "men"): [f], ("d2", "women"): []})
        blocks = to_notion_blocks(r)
        i = next(n for n, b in enumerate(blocks) if b["type"] == "bulleted_list_item")
        rt = blocks[i]["bulleted_list_item"]["rich_text"]
        self.assertEqual(rt[0]["text"]["content"],
                         "Big story · Upset · Close (3 pts) — " + f.headline + " ")
        self.assertEqual(rt[1]["text"]["link"]["url"], f.game.link)
        self.assertEqual(texts(blocks[i + 1:i + 3]),
                         [("paragraph", "A: unranked"), ("paragraph", "Final: 71-68 (3 pts)")])
        t = to_text(r)
        self.assertIn("- Big story · Upset · Close (3 pts) — " + f.headline
                      + "  https://www.ncaa.com/game/1\n    A: unranked\n"
                      "    Final: 71-68 (3 pts)\n", t)

    def test_strong_story_label(self):
        f = make_flag(story="Strong story", facts=["x"])
        t = to_text(make_report({("d2", "men"): [f], ("d2", "women"): []}))
        self.assertIn("- Strong story · Upset", t)

    def test_unlabeled_flag_shows_no_label_or_facts(self):
        f = make_flag(facts=["should not show"])
        r = make_report({("d2", "men"): [f], ("d2", "women"): []})
        t = to_text(r)
        self.assertNotIn("story", t)
        self.assertNotIn("should not show", t)
        blocks = to_notion_blocks(r)
        self.assertNotIn("should not show", [block_text(b) for b in blocks])
        i = next(n for n, b in enumerate(blocks) if b["type"] == "bulleted_list_item")
        self.assertEqual(block_text(blocks[i + 1]), "Women's")

    def test_json_flag_and_grouping(self):
        f = make_flag(division="d1", story="Strong story", facts=["f1"])
        f.winner_rank, f.loser_rank, f.story_points = None, 7, 5
        r = make_report({("d1", "men"): [f], ("d1", "women"): [],
                         ("d2", "men"): [make_flag()], ("d2", "women"): []},
                        final_counts={("d1", "men"): 3, ("d1", "women"): 2,
                                      ("d2", "men"): 1, ("d2", "women"): 0})
        r.games = {("d1", "men"): [f.game], ("d1", "women"): [],
                   ("d2", "men"): [], ("d2", "women"): []}
        d = json.loads(json.dumps(to_json(r)))
        self.assertEqual(d["final_counts"], {"d1": {"men": 3, "women": 2},
                                             "d2": {"men": 1, "women": 0}})
        self.assertEqual(list(d["games"]), ["d1", "d2"])
        self.assertEqual(len(d["games"]["d1"]["men"]), 1)
        self.assertEqual([x["division"] for x in d["flags"]], ["d1", "d2"])
        fl = d["flags"][0]
        self.assertEqual({k: fl[k] for k in ("story", "story_points", "facts",
                                              "winner_rank", "loser_rank")},
                         {"story": "Strong story", "story_points": 5, "facts": ["f1"],
                          "winner_rank": None, "loser_rank": 7})
        self.assertEqual(d["flags"][1]["story"], "")
        self.assertEqual(d["flags"][1]["facts"], [])
        self.assertEqual(d["flag_count"], 2)


if __name__ == "__main__":
    unittest.main()
