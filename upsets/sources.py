from __future__ import annotations

import datetime
import html
import re
from datetime import date
from typing import Any, Optional

from .http import get_json, get_text
from .models import Game, ParseError, PlayerLine, Poll, PollEntry, Team

API_BASE = "https://ncaa-api.henrygd.me"
WBCA_URL = "https://wbca.org/polls-ncaa-division-ii-coaches/"

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


MIN_POLL_ENTRIES = 25

_RANK_RE = re.compile(r"^T?-?\s*(\d{1,3})\s*T?$", re.I)


def _rank(cell: Any) -> Optional[int]:
    """'7' -> 7; ties like 'T-24', 'T24', '24T' -> 24; anything else -> None."""
    m = _RANK_RE.match(str(cell).strip())
    return int(m.group(1)) if m else None


def _check_poll(entries: list[PollEntry], what: str) -> None:
    if any(not e.name for e in entries):
        raise ParseError(f"{what} has a blank school name")
    if len(entries) < MIN_POLL_ENTRIES:
        raise ParseError(f"{what} has {len(entries)} teams (expected at least "
                         f"{MIN_POLL_ENTRIES}); layout may have changed")
    if entries[0].rank != 1 or min(e.rank for e in entries) != 1:
        raise ParseError(f"{what} ranks don't start at 1; layout may have changed")


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


def _str(v: Any) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        raise TypeError(f"expected text, got {type(v).__name__}")
    return v


def parse_scoreboard(data: dict, gender: str, division: str = "d2") -> list[Game]:
    games = []
    try:
        for item in data["games"]:
            g = item["game"]
            game = Game(
                game_id=str(g["gameID"]),
                gender=gender,
                home=_team(g["home"]),
                away=_team(g["away"]),
                state=_str(g.get("gameState", "")),
                period=_str(g.get("currentPeriod", "")),
                url=_str(g.get("url", "")),
                division=division,
            )
            for t in (game.home, game.away):
                t.seo, t.name, t.conference = _str(t.seo), _str(t.name), _str(t.conference)
            games.append(game)
    except Exception as e:
        raise ParseError(f"unexpected scoreboard shape: {type(e).__name__}: {e}")
    return games


def _fmt(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}"


def parse_nabc(data: dict) -> Poll:
    try:
        m = re.search(r"([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2}),\s*(\d{4})", data["updated"])
        if not m or m.group(1).upper() not in _MONTHS:
            raise ParseError(f"cannot read NABC date from {data['updated']!r}")
        as_of = date(int(m.group(3)), _MONTHS[m.group(1).upper()], int(m.group(2)))
        entries = []
        for r in data["data"]:
            rank = _rank(r["RANK"])
            if rank is None:
                raise ParseError(f"unreadable NABC rank {r['RANK']!r}")
            # The column was "SCHOOL (1ST VOTES)" until Nov 2026, now "SCHOOL".
            raw = r["SCHOOL"] if "SCHOOL" in r else r["SCHOOL (1ST VOTES)"]
            school = re.sub(r"\s*\(\d+\)\s*$", "", _str(raw)).strip()
            entries.append(PollEntry(rank, school))
        title = _str(data.get("title", "NABC Coaches")) or "NABC Coaches"
    except ParseError:
        raise
    except Exception as e:
        raise ParseError(f"unexpected NABC shape: {type(e).__name__}: {e}")
    _check_poll(entries, "NABC poll")
    return Poll("men", title, as_of, entries,
                f"{API_BASE}/rankings/basketball-men/d2/nabc-coaches",
                f"NABC thru {_fmt(as_of)}")


def parse_ap(data: dict, gender: str) -> Poll:
    try:
        m = re.search(r"([A-Za-z]{3})[A-Za-z]*\.?\s+(\d{1,2}),\s*(\d{4})", data["updated"])
        if not m or m.group(1).upper() not in _MONTHS:
            raise ParseError(f"cannot read AP date from {data['updated']!r}")
        as_of = date(int(m.group(3)), _MONTHS[m.group(1).upper()], int(m.group(2)))
        entries = []
        for r in data["data"]:
            rank = _rank(r["RANK"])
            if rank is None:
                raise ParseError(f"unreadable AP rank {r['RANK']!r}")
            # Strip only a trailing vote count like " (55)"; "Miami (FL)" stays whole.
            school = re.sub(r"\s*\(\d+\)\s*$", "", _str(r["SCHOOL"])).strip()
            entries.append(PollEntry(rank, school, _str(r.get("RECORD", "")).strip()))
        title = _str(data.get("title", "AP Top 25")) or "AP Top 25"
    except ParseError:
        raise
    except Exception as e:
        raise ParseError(f"unexpected AP shape: {type(e).__name__}: {e}")
    _check_poll(entries, "AP poll")
    return Poll(gender, title, as_of, entries, _ap_url(gender), f"AP thru {_fmt(as_of)}",
                "d1")


def _ap_url(gender: str) -> str:
    return f"{API_BASE}/rankings/basketball-{gender}/d1/associated-press"


def parse_wbca(html_text: str) -> Poll:
    try:
        return _parse_wbca(html_text)
    except ParseError:
        raise
    except Exception as e:
        raise ParseError(f"unexpected WBCA page: {type(e).__name__}: {e}")


def _parse_wbca(html_text: str) -> Poll:
    table = re.search(r"<table.*?</table>", html_text, re.S | re.I)
    if not table:
        raise ParseError("WBCA page has no table")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table.group(0), re.S | re.I)
    entries = []
    for row in rows:
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]
        if len(cells) < 2 or not re.search(r"\d", cells[0]):
            continue  # header row ("Rank", "School (record)", ...)
        rank = _rank(cells[0])
        if rank is None:
            raise ParseError(f"unreadable WBCA rank {cells[0]!r}")
        name = re.sub(r"\s*\(\d+-\d+\)\s*$", "", cells[1]).strip()
        entries.append(PollEntry(rank, name))
    _check_poll(entries, "WBCA poll")
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", html_text)
    if not m:
        raise ParseError("WBCA release date not found")
    release = date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    as_of = release - datetime.timedelta(days=1)
    return Poll("women", "WBCA Coaches", as_of, entries, WBCA_URL, f"WBCA {_fmt(release)}")


def parse_boxscore(data: dict) -> list[PlayerLine]:
    try:
        seo = {str(t["teamId"]): _str(t["seoname"]) for t in data["teams"]}
        out = []
        for tb in data["teamBoxscore"]:
            team_seo = seo[str(tb["teamId"])]
            for p in tb.get("playerStats") or []:
                pts = _int_or_none(p.get("points"))
                if pts is None:
                    continue
                name = f"{p.get('firstName') or ''} {p.get('lastName') or ''}".strip()
                out.append(PlayerLine(name, team_seo, pts))
    except Exception as e:
        raise ParseError(f"unexpected boxscore shape: {type(e).__name__}: {e}")
    return out


def fetch_scoreboard(gender: str, day: date, division: str = "d2") -> list[Game]:
    url = f"{API_BASE}/scoreboard/basketball-{gender}/{division}/{day:%Y/%m/%d}/all-conf"
    return parse_scoreboard(get_json(url), gender, division)


def fetch_poll(gender: str, division: str = "d2") -> Poll:
    if division == "d1":
        return parse_ap(get_json(_ap_url(gender)), gender)
    if gender == "men":
        return parse_nabc(get_json(f"{API_BASE}/rankings/basketball-men/d2/nabc-coaches"))
    return parse_wbca(get_text(WBCA_URL))


def fetch_boxscore(game_id: str) -> list[PlayerLine]:
    return parse_boxscore(get_json(f"{API_BASE}/game/{game_id}/boxscore"))
