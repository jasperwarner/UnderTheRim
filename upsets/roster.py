from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from upsets.models import Game

GENDERS = ("men", "women")


def roster_path(root: Path, division: str = "d2") -> Path:
    name = "teams.json" if division == "d2" else f"teams_{division}.json"
    return Path(root) / "data" / name


def empty_roster() -> dict[str, dict[str, str]]:
    return {g: {} for g in GENDERS}


def load_roster(root: Path, warnings: Optional[list] = None,
                division: str = "d2") -> dict[str, dict[str, str]]:
    """Every team seen on a scoreboard this season: {gender: {seo: name}}.

    A missing file is normal (first run) and gives an empty roster. An unreadable one
    also gives an empty roster, plus a warning: the effect is more name warnings,
    never fewer.
    """
    path = roster_path(root, division)
    if not path.exists():
        return empty_roster()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        out = {}
        for g in GENDERS:
            m = data.get(g, {})
            if not isinstance(m, dict) or not all(
                    isinstance(k, str) and isinstance(v, str) for k, v in m.items()):
                raise ValueError(f"{g} must map team ids to names")
            out[g] = dict(m)
        return out
    except (OSError, ValueError, AttributeError) as e:
        if warnings is not None:
            warnings.append(f"data/{path.name} couldn't be read ({type(e).__name__}) — "
                            "name warnings may be noisier than usual.")
        return empty_roster()


def add_games(roster: dict, gender: str, games: list[Game]) -> int:
    """Add every team on these games to the roster. Returns how many were new."""
    new = 0
    for g in games:
        for t in (g.home, g.away):
            if not t.seo:
                continue
            if t.seo not in roster[gender]:
                new += 1
            roster[gender][t.seo] = t.name  # the newest name wins
    return new


def save_roster(roster: dict, root: Path, division: str = "d2") -> Path:
    path = roster_path(root, division)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {g: dict(sorted(roster[g].items())) for g in GENDERS}
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
