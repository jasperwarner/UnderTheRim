from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from upsets.models import Game, Poll, Team

NEAR_MISS_RATIO = 0.75


def normalize(name: str) -> str:
    s = name.lower()
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    s = s.replace("'", "")
    s = s.replace("&", " and ")
    s = re.sub(r"[-,.()]", " ", s)
    s = re.sub(r"\bstate\b", "st", s)
    return " ".join(s.split())


def load_aliases(path: Path) -> dict[str, dict[str, str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {"men": dict(data.get("men", {})), "women": dict(data.get("women", {}))}


def build_rank_map(
    poll: Poll, games: list[Game], aliases: dict[str, str]
) -> tuple[dict[str, int], list[str]]:
    teams: dict[str, Team] = {}
    for g in games:
        for t in (g.home, g.away):
            teams.setdefault(t.seo, t)

    rank_map: dict[str, int] = {}
    unmatched = []
    for entry in poll.entries:
        seo = _match(entry.name, teams, aliases)
        if seo is None:
            if entry.name not in aliases:
                unmatched.append(entry)
            continue
        rank_map[seo] = min(entry.rank, rank_map.get(seo, entry.rank))

    warnings = []
    for entry in unmatched:
        want = normalize(entry.name)
        best, best_ratio = None, 0.0
        for seo, t in teams.items():
            if seo in rank_map:
                continue
            ratio = difflib.SequenceMatcher(None, want, normalize(t.name)).ratio()
            if ratio > best_ratio:
                best, best_ratio = t, ratio
        if best is not None and best_ratio >= NEAR_MISS_RATIO:
            warnings.append(
                f'Possible name mismatch ({poll.gender}): poll "{entry.name}" '
                f'vs scoreboard "{best.name}" ({best.seo}) — add to aliases.json'
            )
    return rank_map, warnings


def _match(name: str, teams: dict[str, Team], aliases: dict[str, str]):
    alias = aliases.get(name)
    if alias is not None:
        return alias if alias in teams else None
    want = normalize(name)
    for seo, t in teams.items():
        if normalize(t.name) == want:
            return seo
    for seo in teams:
        if seo.replace("-", " ") == want:
            return seo
    return None
