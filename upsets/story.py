from __future__ import annotations

from upsets.models import Flag, PlayerLine, Team
from upsets.rules import boxscore_complete

STRONG_AT = 4
BIG_AT = 6

INCOMPLETE_LINE = "Box score incomplete — top scorers not shown."


def _loser_rank_points(rank: int) -> int:
    if rank <= 5:
        return 3
    if rank <= 10:
        return 2
    if rank <= 25:
        return 1
    return 0


def story_points(flag: Flag) -> int:
    """Rules-based story strength for a flag; reads only fields already on it."""
    points = 0
    if flag.winner_rank is None and flag.loser_rank is not None:
        points += 2
    if flag.loser_rank is not None:
        points += _loser_rank_points(flag.loser_rank)
    tags = flag.tags
    if "Big rank gap" in tags:
        points += 1
    if any(t.startswith("Close") for t in tags):
        points += 1
    if "Overtime" in tags:
        points += 1
    if any(t.startswith("35+ pts") for t in tags):
        points += 1
    if flag.division == "d1":
        points += 1
    return points


def _team_line(team: Team, rank, records: dict[str, str]) -> str:
    text = f"{team.name}: " + (f"No. {rank}" if rank is not None else "unranked")
    record = records.get(team.seo)
    if record:
        text += f", {record}"
    return text


def _top_scorer_line(team: Team, players: list[PlayerLine]) -> str:
    lines = [p for p in players if p.team_seo == team.seo]
    best = max(p.points for p in lines)
    top = [p for p in lines if p.points == best]
    if len(top) == 1:
        return f"Top scorer, {team.name}: {top[0].name} ({best})"
    return f"Top scorers, {team.name}: {' and '.join(p.name for p in top)} ({best} each)"


def _facts(flag: Flag, records: dict[str, str], players: list[PlayerLine]) -> list[str]:
    game = flag.game
    if game.home.score > game.away.score:
        winner, loser = game.home, game.away
    else:
        winner, loser = game.away, game.home
    margin = winner.score - loser.score
    facts = [
        _team_line(winner, flag.winner_rank, records),
        _team_line(loser, flag.loser_rank, records),
        f"Final: {winner.name} {winner.score}-{loser.score} "
        f"({margin}-point win)",
    ]
    if game.overtime:
        facts.append("The game went to overtime.")
    if players and boxscore_complete(game, players):
        facts.append(_top_scorer_line(winner, players))
        facts.append(_top_scorer_line(loser, players))
    else:
        facts.append(INCOMPLETE_LINE)
    return facts


def rate_story(flag: Flag, records: dict[str, str], players: list[PlayerLine]) -> None:
    """Set story_points, story label and facts. Call after add_big_scorers."""
    flag.story_points = story_points(flag)
    if flag.story_points >= BIG_AT:
        flag.story = "Big story"
    elif flag.story_points >= STRONG_AT:
        flag.story = "Strong story"
    else:
        flag.story = ""
    flag.facts = _facts(flag, records, players) if flag.story else []
