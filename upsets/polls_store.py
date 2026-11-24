from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from upsets.models import ParseError, Poll


def _poll_dir(gender: str, root: Path) -> Path:
    return root / "data" / "polls" / gender


def save_poll(poll: Poll, root: Path) -> Path:
    directory = _poll_dir(poll.gender, root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{poll.as_of.isoformat()}.json"
    path.write_text(json.dumps(poll.to_json(), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def poll_for(gender: str, game_day: date, root: Path,
             warnings: Optional[list] = None) -> Optional[Poll]:
    """Newest readable saved poll with as_of strictly before game_day, or None.

    A saved file that can't be read is skipped (with a warning appended to
    `warnings` when given) and the next older one is tried.
    """
    directory = _poll_dir(gender, root)
    if not directory.is_dir():
        return None
    candidates = []
    for path in directory.glob("*.json"):
        try:
            as_of = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if as_of < game_day:
            candidates.append((as_of, path))
    for _, path in sorted(candidates, reverse=True):
        try:
            return Poll.from_json(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, ParseError) as e:
            if warnings is not None:
                warnings.append(f"Saved {gender}'s poll {path.name} couldn't be read "
                                f"({type(e).__name__}) — ignored it.")
    return None
