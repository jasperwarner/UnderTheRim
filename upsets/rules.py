from __future__ import annotations

from typing import Optional

from upsets.models import Flag, Game, PlayerLine, Team


def _label(team: Team, rank: Optional[int]) -> str:
    return f"No. {rank} {team.name}" if rank is not None else team.name


def _flag_game(game: Game, ranks: dict[str, int]) -> Optional[Flag]:
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
        tags.append(f"Close ({margin} pts)")
    if any_ranked and game.overtime:
        tags.append("Overtime")
    if not tags:
        return None
    if game.home.conference == "" or game.away.conference == "":
        tags.append("Non-D2 opponent")
    headline = f"{w_label} beat {_label(loser, r_l)}, {w_score}-{l_score}"
    return Flag(game=game, headline=headline, tags=tags)


def flag_games(games: list[Game], ranks: dict[str, int]) -> list[Flag]:
    flags = (_flag_game(game, ranks) for game in games)
    return [f for f in flags if f is not None]


def add_big_scorers(flag: Flag, players: list[PlayerLine]) -> None:
    for p in players:
        if p.points >= 35:
            flag.tags.append(f"35+ pts: {p.name} {p.points} ({p.team_seo})")
