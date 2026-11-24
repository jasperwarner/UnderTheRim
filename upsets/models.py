from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Optional


class ParseError(Exception):
    """Data from a source (or a saved file) was not in the shape we expect."""


@dataclass
class Team:
    seo: str
    name: str
    score: Optional[int]
    winner: bool
    conference: str  # "" means not a D2 conference


@dataclass
class Game:
    game_id: str
    gender: str
    home: Team
    away: Team
    state: str
    period: str
    url: str
    division: str = "d2"

    @property
    def is_final(self) -> bool:
        return (
            self.state == "final"
            and self.home.score is not None
            and self.away.score is not None
        )

    @property
    def overtime(self) -> bool:
        return "OT" in self.period

    @property
    def link(self) -> str:
        return "https://www.ncaa.com" + self.url


@dataclass
class PollEntry:
    rank: int
    name: str
    record: str = ""


@dataclass
class Poll:
    gender: str
    title: str
    as_of: datetime.date  # games dated after this are measured against the poll
    entries: list[PollEntry]
    source: str
    label: str
    division: str = "d2"

    def to_json(self) -> dict[str, Any]:
        return {
            "gender": self.gender,
            "title": self.title,
            "as_of": self.as_of.isoformat(),
            "entries": [
                {"rank": e.rank, "name": e.name, **({"record": e.record} if e.record else {})}
                for e in self.entries
            ],
            "source": self.source,
            "label": self.label,
            "division": self.division,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Poll":
        try:
            fields = {k: d[k] for k in ("gender", "title", "source", "label")}
            if not all(isinstance(v, str) for v in fields.values()):
                raise ValueError("text fields must be strings")
            division = d.get("division", "d2")
            if not isinstance(division, str):
                raise ValueError("division must be a string")
            entries = []
            for e in d["entries"]:
                record = e.get("record", "")
                if (not isinstance(e["name"], str) or isinstance(e["rank"], bool)
                        or not isinstance(record, str)):
                    raise ValueError("bad poll entry")
                entries.append(PollEntry(int(e["rank"]), e["name"], record))
            if not entries:
                raise ValueError("no entries")
            return cls(as_of=datetime.date.fromisoformat(d["as_of"]), entries=entries,
                       division=division, **fields)
        except Exception as e:
            raise ParseError(f"unexpected saved poll shape: {type(e).__name__}: {e}")


@dataclass
class PlayerLine:
    name: str
    team_seo: str
    points: int


@dataclass
class Flag:
    game: Game
    headline: str
    tags: list[str] = field(default_factory=list)
