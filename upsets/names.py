from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Optional

from upsets.models import Game, Poll, Team

NEAR_MISS_RATIO = 0.75
GENDER_KEYS = ("men", "women")


def normalize(name: str) -> str:
    s = name.lower()
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    s = s.replace("'", "")
    s = s.replace("&", " and ")
    s = re.sub(r"[-,.()]", " ", s)
    s = re.sub(r"\bstate\b", "st", s)
    return " ".join(s.split())


def _str_map(value, where: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValueError(f"{where} must map names to seo strings")
    return dict(value)


def _list_map(value, where: str) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        raise ValueError(f"{where} must be an object")
    out: dict[str, list[str]] = {}
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, list) \
                or not all(isinstance(s, str) for s in v):
            raise ValueError(f"{where} must map names to lists of seo strings")
        out[k] = list(v)
    return out


def load_aliases(path: Path) -> dict:
    """Read aliases.json.

    Shape: {"men": {poll name: seo}, "women": {poll name: seo},
            "not_same": {"men": {poll name: [seo, ...]}, "women": {...}}}.
    Raises ValueError (or OSError) if the file is missing or the shape is wrong.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("aliases.json must be an object")
    out: dict = {g: _str_map(data.get(g, {}), g) for g in GENDER_KEYS}
    not_same = data.get("not_same", {})
    if not isinstance(not_same, dict):
        raise ValueError("not_same must be an object")
    out["not_same"] = {g: _list_map(not_same.get(g, {}), f"not_same.{g}")
                       for g in GENDER_KEYS}
    return out


def build_rank_map(
    poll: Poll, games: list[Game], aliases: dict[str, str],
    not_same: Optional[dict[str, list[str]]] = None,
) -> tuple[dict[str, int], list[str]]:
    teams: dict[str, Team] = {}
    for g in games:
        for t in (g.home, g.away):
            if t.seo:
                teams.setdefault(t.seo, t)

    norm_aliases = {normalize(k): v for k, v in aliases.items()}
    norm_not_same: dict[str, set[str]] = {}
    for k, seos in (not_same or {}).items():
        norm_not_same.setdefault(normalize(k), set()).update(seos)

    rank_map: dict[str, int] = {}
    unmatched = []
    for entry in poll.entries:
        seo = _match(entry.name, teams, norm_aliases)
        if seo is None:
            unmatched.append(entry)
            continue
        rank_map[seo] = min(entry.rank, rank_map.get(seo, entry.rank))

    warnings = []
    for entry in unmatched:
        want = normalize(entry.name)
        skip = norm_not_same.get(want, set())
        best, best_ratio = None, 0.0
        for seo, t in teams.items():
            if seo in rank_map or seo in skip:
                continue
            ratio = max(
                difflib.SequenceMatcher(None, want, normalize(t.name)).ratio(),
                difflib.SequenceMatcher(None, want, seo.replace("-", " ")).ratio(),
            )
            if ratio > best_ratio:
                best, best_ratio = t, ratio
        if best is not None and best_ratio >= NEAR_MISS_RATIO:
            warnings.append(
                f'Possible name mismatch ({poll.gender}): poll "{entry.name}" looks similar '
                f'to scoreboard "{best.name}" ({best.seo}) — if they are the same school, '
                f'add an alias; if not, add them to not_same in aliases.json'
            )
    return rank_map, warnings


def _match(name: str, teams: dict[str, Team], norm_aliases: dict[str, str]):
    want = normalize(name)
    alias = norm_aliases.get(want)
    if alias is not None and alias in teams:
        return alias
    # No alias, or the alias points at a team not on this scoreboard (it may not
    # have played, or the alias may be a typo): fall back to normal matching.
    for seo, t in teams.items():
        if normalize(t.name) == want:
            return seo
    for seo in teams:
        if seo.replace("-", " ") == want:
            return seo
    return None
