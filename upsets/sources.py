from __future__ import annotations

import datetime
import html
import re
from datetime import date
from typing import Any, Optional

from .http import get_json, get_text
from .models import Game, PlayerLine, Poll, PollEntry, Team

API_BASE = "https://ncaa-api.henrygd.me"
WBCA_URL = "https://wbca.org/polls-ncaa-division-ii-coaches/"

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


class ParseError(Exception):
    pass


def _int_or_none(v: Any) -> Optional[int]:
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _team(t: dict) -> Team:
    names = t.get("names") or {}
    confs = t.get("conferences") or []
    conf = (confs[0].get("conferenceSeo") or "") if confs else ""
    return Team(
        seo=names.get("seo", ""),
        name=names.get("short", ""),
        score=_int_or_none(t.get("score")),
        winner=bool(t.get("winner")),
        conference=conf,
    )


def parse_scoreboard(data: dict, gender: str) -> list[Game]:
    games = []
    try:
        for item in data["games"]:
            g = item["game"]
            games.append(Game(
                game_id=str(g["gameID"]),
                gender=gender,
                home=_team(g["home"]),
                away=_team(g["away"]),
                state=g.get("gameState", ""),
                period=g.get("currentPeriod", ""),
                url=g.get("url", ""),
            ))
    except (KeyError, TypeError) as e:
        raise ParseError(f"unexpected scoreboard shape: {e!r}")
    return games


def _fmt(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}"


def parse_nabc(data: dict) -> Poll:
    try:
        m = re.search(r"([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2}),\s*(\d{4})", data["updated"])
        if not m or m.group(1).upper() not in _MONTHS:
            raise ParseError(f"cannot read NABC date from {data['updated']!r}")
        as_of = date(int(m.group(3)), _MONTHS[m.group(1).upper()], int(m.group(2)))
        entries = [
            PollEntry(int(r["RANK"]), re.sub(r"\s*\(\d+\)\s*$", "", r["SCHOOL (1ST VOTES)"]).strip())
            for r in data["data"]
        ]
        title = data.get("title", "NABC Coaches")
    except (KeyError, TypeError, ValueError) as e:
        raise ParseError(f"unexpected NABC shape: {e!r}")
    if not entries:
        raise ParseError("NABC poll has no entries")
    return Poll("men", title, as_of, entries,
                f"{API_BASE}/rankings/basketball-men/d2/nabc-coaches",
                f"NABC thru {_fmt(as_of)}")


def parse_wbca(html_text: str) -> Poll:
    table = re.search(r"<table.*?</table>", html_text, re.S | re.I)
    if not table:
        raise ParseError("WBCA page has no table")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), re.S | re.I)
    entries = []
    for row in rows:
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]
        if len(cells) < 2 or not cells[0].isdigit():
            continue  # header row
        name = re.sub(r"\s*\(\d+-\d+\)\s*$", "", cells[1]).strip()
        entries.append(PollEntry(int(cells[0]), name))
    if len(entries) < 20:
        raise ParseError(f"WBCA table has {len(entries)} rows; layout may have changed")
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", html_text)
    if not m:
        raise ParseError("WBCA release date not found")
    release = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    as_of = release - datetime.timedelta(days=1)
    return Poll("women", "WBCA Coaches", as_of, entries, WBCA_URL, f"WBCA {_fmt(release)}")


def parse_boxscore(data: dict) -> list[PlayerLine]:
    try:
        seo = {str(t["teamId"]): t["seoname"] for t in data["teams"]}
        out = []
        for tb in data["teamBoxscore"]:
            team_seo = seo[str(tb["teamId"])]
            for p in tb.get("playerStats", []):
                pts = _int_or_none(p.get("points"))
                if pts is None:
                    continue
                name = f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()
                out.append(PlayerLine(name, team_seo, pts))
    except (KeyError, TypeError) as e:
        raise ParseError(f"unexpected boxscore shape: {e!r}")
    return out


def fetch_scoreboard(gender: str, day: date) -> list[Game]:
    url = f"{API_BASE}/scoreboard/basketball-{gender}/d2/{day:%Y/%m/%d}/all-conf"
    return parse_scoreboard(get_json(url), gender)


def fetch_poll(gender: str) -> Poll:
    if gender == "men":
        return parse_nabc(get_json(f"{API_BASE}/rankings/basketball-men/d2/nabc-coaches"))
    return parse_wbca(get_text(WBCA_URL))


def fetch_boxscore(game_id: str) -> list[PlayerLine]:
    return parse_boxscore(get_json(f"{API_BASE}/game/{game_id}/boxscore"))
