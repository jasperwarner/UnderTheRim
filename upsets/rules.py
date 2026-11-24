from __future__ import annotations

from typing import Collection, Optional

from upsets.models import Flag, Game, PlayerLine, Team


def _label(team: Team, rank: Optional[int]) -> str:
    return f"No. {rank} {team.name}" if rank is not None else team.name


def _in_division(team: Team, conferences: Optional[Collection[str]]) -> bool:
    if conferences is None:  # no conference list available: old rule
        return team.conference != ""
    return team.conference in conferences


def close_tag(margin: int) -> str:
    return "Close (1 pt)" if margin == 1 else f"Close ({margin} pts)"


def _flag_game(game: Game, ranks: dict[str, int],
               conferences: Optional[Collection[str]], division: str) -> Optional[Flag]:
    if not game.is_final:
        return None
    hs, as_ = game.home.score, game.away.score
    if hs == as_:
        return None
    winner, loser = (game.home, game.away) if hs > as_ else (game.away, game.home)
    w_score, l_score = max(hs, as_), min(hs, as_)
    r_w, r_l = ranks.get(winner.seo), ranks.get(loser.seo)
    margin = w_score - l_score
    any_ranked = r_w is not None or r_l is not None

    tags: list[str] = []
    w_label = _label(winner, r_w)
    if r_l is not None and r_w is None:
        tags.append("Upset")
        w_label = "Unranked " + w_label
    if r_w is not None and r_l is not None and r_w - r_l >= 10:
        tags.append("Big rank gap")
    if any_ranked and margin <= 3:
        tags.append(close_tag(margin))
    if any_ranked and game.overtime:
        tags.append("Overtime")
    if not tags:
        return None
    if not _in_division(game.home, conferences) or not _in_division(game.away, conferences):
        tags.append("Non-D1 opponent" if division == "d1" else "Non-D2 opponent")
    headline = f"{w_label} beat {_label(loser, r_l)}, {w_score}-{l_score}"
    return Flag(game=game, headline=headline, tags=tags, division=division,
                winner_rank=r_w, loser_rank=r_l)


def flag_games(games: list[Game], ranks: dict[str, int],
               conferences: Optional[Collection[str]] = None,
               division: str = "d2") -> list[Flag]:
    """Flag notable final games.

    `conferences` is the set of conference seos that count as `division`
    ("d2" or "d1"); a team in any other conference (or none) is a
    "Non-D2 opponent" / "Non-D1 opponent". When it is None, only a blank
    conference counts as outside the division.
    """
    flags = (_flag_game(game, ranks, conferences, division) for game in games)
    return [f for f in flags if f is not None]


def add_big_scorers(flag: Flag, players: list[PlayerLine]) -> None:
    for p in players:
        if p.points >= 35:
            flag.tags.append(f"35+ pts: {p.name} {p.points} ({p.team_seo})")


def boxscore_complete(game: Game, players: list[PlayerLine]) -> bool:
    """True when, for both teams, the listed players' points add up to the final score."""
    for team in (game.home, game.away):
        lines = [p for p in players if p.team_seo == team.seo]
        if not lines or sum(p.points for p in lines) != team.score:
            return False
    return True
