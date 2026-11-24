from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

from upsets.models import PollEntry
from upsets.sources import (ParseError, parse_boxscore, parse_nabc,
                            parse_scoreboard, parse_wbca)

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


if __name__ == "__main__":
    unittest.main()
