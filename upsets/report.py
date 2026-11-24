from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Optional

from upsets.models import Flag, Game, Team

GENDERS = (("men", "Men's"), ("women", "Women's"))
SECTIONS = (("d1", "Division I"), ("d2", "Division II"))

Key = tuple  # (division, gender), e.g. ("d2", "men")


@dataclass
class Report:
    day: datetime.date
    flags: dict[Key, list[Flag]]
    warnings: list[str]
    final_counts: dict[Key, int]
    polls_used: str
    fatal: bool = False
    games: dict[Key, list[Game]] = field(default_factory=dict)
    # (division, gender) slots that were not fully checked: their scoreboard couldn't be
    # fetched, they crashed, or their poll was missing. Shown as "Not checked", never as
    # "No flags.", and left out of the "games checked" counts.
    unchecked: set = field(default_factory=set)
    # The part of `unchecked` that did read its scoreboard but skipped the ranked-team rules.
    ranked_skipped: set = field(default_factory=set)

    @property
    def status(self) -> str:
        if self.fatal:
            return "Failed"
        return "Check data" if self.warnings else "OK"

    @property
    def flag_count(self) -> int:
        return sum(len(v) for v in self.flags.values())


def _divisions(r: Report) -> list[tuple[str, str]]:
    """The (division, title) sections to show: those with keys in `flags`, D1 first."""
    present = {key[0] for key in r.flags}
    return [(d, title) for d, title in SECTIONS if d in present]


def _count(r: Report, division: str, gender: str) -> int:
    return r.final_counts.get((division, gender), 0)


NOT_CHECKED = "Not checked — see warnings above."
RANKED_SKIPPED = "Ranked-team checks skipped (no poll) — see warnings above."


def _slot_note(r: Report, division: str, gender: str) -> Optional[str]:
    key = (division, gender)
    if key not in r.unchecked:
        return None
    return RANKED_SKIPPED if key in r.ranked_skipped else NOT_CHECKED


def _checked_total(r: Report, gender: str) -> int:
    return sum(_count(r, d, gender) for d, _ in _divisions(r) if (d, gender) not in r.unchecked)


def _no_upsets_line(r: Report) -> str:
    left_out = [f"{title} {poss.lower()}" for d, title in _divisions(r)
                for g, poss in GENDERS if (d, g) in r.unchecked]
    if not left_out:
        return (f"No upsets yesterday — {_checked_total(r, 'men')} men's and "
                f"{_checked_total(r, 'women')} women's games checked.")
    slots = [(d, g) for d, _ in _divisions(r) for g, _ in GENDERS]
    if all(k in r.unchecked for k in slots):
        return "Nothing could be checked — see warnings above."
    return (f"No upsets in the games that were checked — {_checked_total(r, 'men')} men's and "
            f"{_checked_total(r, 'women')} women's games checked. "
            f"Not checked: {', '.join(left_out)}.")


def _footer_part(r: Report, division: str, gender: str, suffix: str) -> str:
    note = _slot_note(r, division, gender)
    if note is None:
        return f"{_count(r, division, gender)}{suffix}"
    return "ranked checks skipped" if note == RANKED_SKIPPED else "not checked"


def _footer(r: Report) -> str:
    divs = _divisions(r)
    parts = []
    for d, title in divs:
        part = (f"Men: {_footer_part(r, d, 'men', ' final games checked')}"
                f" · Women: {_footer_part(r, d, 'women', '')}")
        parts.append(part if len(divs) == 1 else f"{title} — {part}")
    return " · ".join(parts)


def _flag_line(f: Flag) -> str:
    label = [f.story] if f.story else []
    return f"{' · '.join(label + list(f.tags))} — {f.headline}"


def _facts(f: Flag) -> list[str]:
    return list(f.facts) if f.story else []


def to_text(r: Report) -> str:
    lines = [f"Upsets for {r.day.isoformat()} — {r.status}"]
    if r.warnings:
        lines += ["", "⚠️ Data warnings"] + [f"- {w}" for w in r.warnings]
    if r.flag_count == 0:
        lines += ["", _no_upsets_line(r)]
    for division, div_title in _divisions(r):
        lines += ["", div_title]
        for gender, title in GENDERS:
            lines += ["", title]
            flags = r.flags.get((division, gender), [])
            note = _slot_note(r, division, gender)
            if not flags and note is None:
                lines.append("No flags.")
            for f in flags:
                lines.append(f"- {_flag_line(f)}  {f.game.link}")
                lines += [f"    {fact}" for fact in _facts(f)]
            if note is not None:
                lines.append(note)
    lines += ["", _footer(r), f"Polls used: {r.polls_used}"]
    return "\n".join(lines)


def _team_json(t: Team) -> dict[str, Any]:
    return {"seo": t.seo, "name": t.name, "score": t.score, "conferenceSeo": t.conference}


def _game_json(g: Game) -> dict[str, Any]:
    return {
        "id": g.game_id,
        "gameState": g.state,
        "currentPeriod": g.period,
        "home": _team_json(g.home),
        "away": _team_json(g.away),
    }


def _json_divisions(r: Report) -> list[str]:
    present = {key[0] for key in list(r.flags) + list(r.final_counts) + list(r.games)}
    return [d for d, _ in SECTIONS if d in present]


def to_json(r: Report) -> dict[str, Any]:
    divisions = _json_divisions(r)
    flags = []
    for division in divisions:
        for gender, _ in GENDERS:
            for f in r.flags.get((division, gender), []):
                g = f.game
                flags.append({
                    "division": division,
                    "gender": g.gender,
                    "game_id": g.game_id,
                    "headline": f.headline,
                    "tags": list(f.tags),
                    "link": g.link,
                    "home": {"seo": g.home.seo, "score": g.home.score},
                    "away": {"seo": g.away.seo, "score": g.away.score},
                    "winner_rank": f.winner_rank,
                    "loser_rank": f.loser_rank,
                    "story": f.story,
                    "story_points": f.story_points,
                    "facts": list(f.facts),
                })
    return {
        "day": r.day.isoformat(),
        "status": r.status,
        "flag_count": r.flag_count,
        "polls_used": r.polls_used,
        "warnings": list(r.warnings),
        "final_counts": {d: {g: _count(r, d, g) for g, _ in GENDERS} for d in divisions},
        "fatal": r.fatal,
        "unchecked": sorted(f"{d}-{g}" for d, g in r.unchecked),
        "flags": flags,
        "games": {d: {g: [_game_json(x) for x in r.games.get((d, g), [])] for g, _ in GENDERS}
                  for d in divisions},
    }


def _text(content: str, link: Optional[str] = None) -> dict[str, Any]:
    t: dict[str, Any] = {"content": content}
    if link:
        t["link"] = {"url": link}
    return {"type": "text", "text": t}


def _block(kind: str, rich_text: list[dict[str, Any]]) -> dict[str, Any]:
    return {"object": "block", "type": kind, kind: {"rich_text": rich_text}}


def to_notion_blocks(r: Report) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if r.warnings:
        blocks.append(_block("heading_2", [_text("⚠️ Data warnings")]))
        blocks += [_block("bulleted_list_item", [_text(w)]) for w in r.warnings]
    if r.flag_count == 0:
        blocks.append(_block("paragraph", [_text(_no_upsets_line(r))]))
    for division, div_title in _divisions(r):
        blocks.append(_block("heading_2", [_text(div_title)]))
        for gender, title in GENDERS:
            blocks.append(_block("heading_3", [_text(title)]))
            flags = r.flags.get((division, gender), [])
            note = _slot_note(r, division, gender)
            if not flags and note is None:
                blocks.append(_block("paragraph", [_text("No flags.")]))
            for f in flags:
                blocks.append(_block("bulleted_list_item", [
                    _text(f"{_flag_line(f)} "),
                    _text("ncaa.com ↗", f.game.link),
                ]))
                blocks += [_block("paragraph", [_text(fact)]) for fact in _facts(f)]
            if note is not None:
                blocks.append(_block("paragraph", [_text(note)]))
    blocks.append(_block("paragraph", [_text(_footer(r))]))
    return blocks
