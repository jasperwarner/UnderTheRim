from __future__ import annotations

from typing import Collection, Optional

from upsets.models import Flag, Game, PlayerLine, Team


def _label(team: Team, rank: Optional[int]) -> str:
    return f"No. {rank} {team.name}" if rank is not None else team.name


def _is_d2(team: Team, d2_conferences: Optional[Collection[str]]) -> bool:
    if d2_conferences is None:  # no conference list available: old rule
        return team.conference != ""
    return team.conference in d2_conferences


def close_tag(margin: int) -> str:
    return "Close (1 pt)" if margin == 1 else f"Close ({margin} pts)"


def _flag_game(game: Game, ranks: dict[str, int],
               d2_conferences: Optional[Collection[str]]) -> Optional[Flag]:
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
    if not _is_d2(game.home, d2_conferences) or not _is_d2(game.away, d2_conferences):
        tags.append("Non-D2 opponent")
    headline = f"{w_label} beat {_label(loser, r_l)}, {w_score}-{l_score}"
    return Flag(game=game, headline=headline, tags=tags)


def flag_games(games: list[Game], ranks: dict[str, int],
               d2_conferences: Optional[Collection[str]] = None) -> list[Flag]:
    """Flag notable final games.

    `d2_conferences` is the set of conference seos that count as Division II;
    a team in any other conference (or none) is a "Non-D2 opponent". When it
    is None, only a blank conference counts as non-D2.
    """
    flags = (_flag_game(game, ranks, d2_conferences) for game in games)
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
