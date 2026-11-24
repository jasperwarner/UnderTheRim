from __future__ import annotations

import datetime
import json
import unittest

from upsets.models import Flag, Game, Team
from upsets.report import Report, to_json, to_notion_blocks, to_text


def make_flag(gender="men"):
    home = Team("a", "A", 71, True, "gsc")
    away = Team("b", "B", 68, False, "gsc")
    game = Game("1", gender, home, away, "final", "FINAL", "/game/1")
    return Flag(game, "Unranked A beat No. 7 B, 71-68", ["Upset", "Close (3 pts)"])


def make_report(flags=None, warnings=None, fatal=False):
    return Report(
        day=datetime.date(2026, 11, 22),
        flags=flags if flags is not None else {"men": [], "women": []},
        warnings=warnings or [],
        final_counts={"men": 110, "women": 98},
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
        blocks = to_notion_blocks(make_report({"men": [f], "women": []}))
        items = [b for b in blocks if b["type"] == "bulleted_list_item"]
        self.assertEqual(len(items), 1)
        rt = items[0]["bulleted_list_item"]["rich_text"]
        self.assertEqual(rt[0]["text"]["content"], "Upset · Close (3 pts) — " + f.headline + " ")
        self.assertEqual(rt[1]["text"]["content"], "ncaa.com ↗")
        self.assertEqual(rt[1]["text"]["link"]["url"], f.game.link)
        self.assertEqual(block_text(blocks[0]), "Men's")
        self.assertIn("No flags.", [block_text(b) for b in blocks])

    def test_warnings_first(self):
        blocks = to_notion_blocks(make_report(warnings=["w1"]))
        self.assertEqual(blocks[0]["type"], "heading_2")
        self.assertEqual(block_text(blocks[0]), "⚠️ Data warnings")
        self.assertEqual(blocks[1]["type"], "bulleted_list_item")
        self.assertEqual(block_text(blocks[1]), "w1")
        self.assertTrue(block_text(blocks[2]).startswith("No upsets yesterday"))

    def test_json_round_trippable(self):
        r = make_report({"men": [make_flag()], "women": []}, warnings=["w"])
        d = json.loads(json.dumps(to_json(r)))
        for k in ("status", "flags", "warnings", "final_counts", "day",
                  "flag_count", "polls_used", "fatal"):
            self.assertIn(k, d)
        self.assertEqual(d["day"], "2026-11-22")
        self.assertEqual(d["flag_count"], 1)
        fl = d["flags"][0]
        self.assertEqual(fl["gender"], "men")
        self.assertEqual(fl["link"], "https://www.ncaa.com/game/1")
        self.assertEqual(fl["home"], {"seo": "a", "score": 71})
        self.assertEqual(fl["away"], {"seo": "b", "score": 68})

    def test_text(self):
        t = to_text(make_report({"men": [make_flag()], "women": []}, warnings=["w1"]))
        self.assertIn("- Upset · Close (3 pts) — Unranked A beat No. 7 B, 71-68  https://www.ncaa.com/game/1", t)
        self.assertLess(t.index("w1"), t.index("Men's"))


if __name__ == "__main__":
    unittest.main()
