from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Optional


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


@dataclass
class Poll:
    gender: str
    title: str
    as_of: datetime.date  # games dated after this are measured against the poll
    entries: list[PollEntry]
    source: str
    label: str

    def to_json(self) -> dict[str, Any]:
        return {
            "gender": self.gender,
            "title": self.title,
            "as_of": self.as_of.isoformat(),
            "entries": [{"rank": e.rank, "name": e.name} for e in self.entries],
            "source": self.source,
            "label": self.label,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Poll":
        return cls(
            gender=d["gender"],
            title=d["title"],
            as_of=datetime.date.fromisoformat(d["as_of"]),
            entries=[PollEntry(int(e["rank"]), e["name"]) for e in d["entries"]],
            source=d["source"],
            label=d["label"],
        )


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
