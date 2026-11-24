from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any, Optional

from upsets.models import Flag

GENDERS = (("men", "Men's"), ("women", "Women's"))


@dataclass
class Report:
    day: datetime.date
    flags: dict[str, list[Flag]]
    warnings: list[str]
    final_counts: dict[str, int]
    polls_used: str
    fatal: bool = False

    @property
    def status(self) -> str:
        if self.fatal:
            return "Failed"
        return "Check data" if self.warnings else "OK"

    @property
    def flag_count(self) -> int:
        return sum(len(v) for v in self.flags.values())


def _no_upsets_line(r: Report) -> str:
    return (
        "No upsets yesterday — "
        f"{r.final_counts.get('men', 0)} men's and "
        f"{r.final_counts.get('women', 0)} women's games checked."
    )


def _footer(r: Report) -> str:
    return (
        f"Men: {r.final_counts.get('men', 0)} final games checked"
        f" · Women: {r.final_counts.get('women', 0)}"
    )


def to_text(r: Report) -> str:
    lines = [f"D2 upsets for {r.day.isoformat()} — {r.status}"]
    if r.warnings:
        lines += ["", "⚠️ Data warnings"] + [f"- {w}" for w in r.warnings]
    if r.flag_count == 0:
        lines += ["", _no_upsets_line(r)]
    for key, title in GENDERS:
        lines += ["", title]
        flags = r.flags.get(key, [])
        if not flags:
            lines.append("No flags.")
        for f in flags:
            lines.append(f"- {' · '.join(f.tags)} — {f.headline}  {f.game.link}")
    lines += ["", _footer(r)]
    return "\n".join(lines)


def to_json(r: Report) -> dict[str, Any]:
    flags = []
    for key, _ in GENDERS:
        for f in r.flags.get(key, []):
            g = f.game
            flags.append({
                "gender": g.gender,
                "game_id": g.game_id,
                "headline": f.headline,
                "tags": list(f.tags),
                "link": g.link,
                "home": {"seo": g.home.seo, "score": g.home.score},
                "away": {"seo": g.away.seo, "score": g.away.score},
            })
    return {
        "day": r.day.isoformat(),
        "status": r.status,
        "flag_count": r.flag_count,
        "polls_used": r.polls_used,
        "warnings": list(r.warnings),
        "final_counts": dict(r.final_counts),
        "fatal": r.fatal,
        "flags": flags,
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
    for key, title in GENDERS:
        blocks.append(_block("heading_2", [_text(title)]))
        flags = r.flags.get(key, [])
        if not flags:
            blocks.append(_block("paragraph", [_text("No flags.")]))
        for f in flags:
            blocks.append(_block("bulleted_list_item", [
                _text(f"{' · '.join(f.tags)} — {f.headline} "),
                _text("ncaa.com ↗", f.game.link),
            ]))
    blocks.append(_block("paragraph", [_text(_footer(r))]))
    return blocks
