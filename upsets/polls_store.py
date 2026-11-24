from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

from upsets.models import Poll


def _poll_dir(gender: str, root: Path) -> Path:
    return root / "data" / "polls" / gender


def save_poll(poll: Poll, root: Path) -> Path:
    directory = _poll_dir(poll.gender, root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{poll.as_of.isoformat()}.json"
    path.write_text(json.dumps(poll.to_json(), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def poll_for(gender: str, game_day: date, root: Path) -> Optional[Poll]:
    """Newest saved poll with as_of strictly before game_day, or None."""
    directory = _poll_dir(gender, root)
    if not directory.is_dir():
        return None
    best = None
    for path in directory.glob("*.json"):
        try:
            as_of = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if as_of < game_day and (best is None or as_of > best[0]):
            best = (as_of, path)
    if best is None:
        return None
    return Poll.from_json(json.loads(best[1].read_text(encoding="utf-8")))
