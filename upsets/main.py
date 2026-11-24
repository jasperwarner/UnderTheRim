from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from . import sources
from .http import FetchError
from .models import Poll
from .names import build_rank_map, load_aliases
from .notion import NotionClient
from .polls_store import poll_for, save_poll
from .report import Report, to_json, to_text
from .rules import add_big_scorers, flag_games
from .sources import ParseError

GENDERS = ("men", "women")
IN_SEASON_MONTHS = (11, 12, 1, 2, 3)
FAR_FUTURE = date(9999, 12, 31)


def _safe_aliases(root: Path, warnings: list) -> dict:
    try:
        return load_aliases(root / "aliases.json")
    except (OSError, ValueError, AttributeError, TypeError) as e:
        reason = type(e).__name__
        warnings.append(f"aliases.json couldn't be read ({reason}) — "
                        "name matching may miss ranked teams.")
        return {"men": {}, "women": {}, "not_same": {"men": {}, "women": {}}}


def _pick_poll(gender, day, root, fetched, warnings):
    """Newest poll released strictly before `day`, from saved polls and today's fetch."""
    saved = poll_for(gender, day, root)
    usable_fetched = fetched if fetched is not None and fetched.as_of < day else None
    if usable_fetched is not None and (saved is None or usable_fetched.as_of > saved.as_of):
        return usable_fetched
    if saved is not None:
        return saved
    if fetched is not None:
        warnings.append(
            f"{gender.capitalize()}: ranks are from a poll released after this game "
            f"({fetched.as_of})."
        )
        return fetched
    return None


def run(day: date, root: Path, *, dry_run: bool, fetch=sources,
        notion: Optional[NotionClient] = None) -> Report:
    root = Path(root)
    warnings: list[str] = []
    aliases = _safe_aliases(root, warnings)
    flags: dict[str, list] = {g: [] for g in GENDERS}
    final_counts = {g: 0 for g in GENDERS}
    polls_used: dict[str, str] = {}
    fatal = False
    scoreboards_down = 0
    total_games = 0
    polls_missing = 0

    for gender in GENDERS:
        cap, low = gender.capitalize(), gender
        poss = "Men's" if gender == "men" else "Women's"
        try:
            games = fetch.fetch_scoreboard(gender, day)
        except (FetchError, ParseError):
            fatal = True
            scoreboards_down += 1
            warnings.append(f"{cap} scoreboard couldn't be fetched.")
            polls_used[gender] = f"{cap} n/a"
            continue

        fetched: Optional[Poll] = None
        save_warning = None
        try:
            fetched = fetch.fetch_poll(gender)
        except (FetchError, ParseError):
            fetched = None
        if fetched is not None and not dry_run:
            try:
                save_poll(fetched, root)
            except OSError:
                save_warning = f"{cap} poll couldn't be saved."

        poll = _pick_poll(gender, day, root, fetched, warnings)
        if poll is None:
            polls_missing += 1
            warnings.append(f"{poss} poll couldn't be read today — {low}'s ranked rules skipped.")
            polls_used[gender] = f"{cap} none"
        else:
            if fetched is None:
                warnings.append(f"{poss} poll couldn't be refreshed today — using the saved poll.")
            saved_newest = poll_for(gender, FAR_FUTURE, root)
            newest = max([p.as_of for p in (saved_newest, fetched) if p is not None])
            label = f"{cap} {poll.label}"
            if day.month == 3 and poll.as_of == newest:
                label += " (final poll)"
            polls_used[gender] = label
            season_end = date(day.year if day.month < 7 else day.year + 1, 3, 1)
            age = (day - poll.as_of).days
            if day < season_end and age > 9:
                warnings.append(f"{cap} poll is {age} days old.")
        if save_warning:
            warnings.append(save_warning)

        if not games and day.month in IN_SEASON_MONTHS:
            warnings.append(f"No {low}'s games found for {day} — verify on ncaa.com.")
        total_games += len(games)
        final_counts[gender] = sum(1 for g in games if g.is_final)
        for g in games:
            if not g.is_final:
                warnings.append(
                    f"Not final ({low}): {g.away.name} at {g.home.name} — {g.state or 'unknown'}."
                )

        ranks: dict[str, int] = {}
        if poll is not None:
            ranks, name_warnings = build_rank_map(poll, games, aliases[gender],
                                                  aliases["not_same"][gender])
            warnings.extend(name_warnings)
        gender_flags = flag_games(games, ranks)
        for flag in gender_flags:
            try:
                add_big_scorers(flag, fetch.fetch_boxscore(flag.game.game_id))
            except (FetchError, ParseError):
                warnings.append(f"No box score for {flag.headline}.")
        flags[gender] = gender_flags

    if polls_missing == 2:
        fatal = True

    report = Report(day=day, flags=flags, warnings=warnings, final_counts=final_counts,
                    polls_used=" · ".join(polls_used[g] for g in GENDERS), fatal=fatal)

    if dry_run:
        print(to_text(report))
        return report

    offseason_empty = (4 <= day.month <= 10 and not fatal
                       and total_games == 0
                       and scoreboards_down == 0)
    if offseason_empty:
        return report
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / f"{day.isoformat()}.json").write_text(
        json.dumps(to_json(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if notion is not None:
        notion.publish(report)
    return report


def _yesterday_eastern() -> date:
    from zoneinfo import ZoneInfo
    return (datetime.datetime.now(ZoneInfo("America/New_York")) - datetime.timedelta(days=1)).date()


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m upsets.main")
    parser.add_argument("--date", type=date.fromisoformat, default=None,
                        help="game day, YYYY-MM-DD (default: yesterday, New York time)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the report; write nothing and skip Notion")
    args = parser.parse_args(argv)
    day = args.date or _yesterday_eastern()
    root = Path(__file__).resolve().parent.parent

    notion = None
    if not args.dry_run:
        token = os.environ.get("NOTION_TOKEN")
        database_id = os.environ.get("NOTION_DATABASE_ID")
        if not token or not database_id:
            print("Error: NOTION_TOKEN and NOTION_DATABASE_ID must be set "
                  "(or use --dry-run).", file=sys.stderr)
            return 1
        notion = NotionClient(token, database_id)

    try:
        report = run(day, root, dry_run=args.dry_run, notion=notion)
    except FetchError as e:
        print(f"Error: could not publish to Notion: {e}", file=sys.stderr)
        return 1
    if not args.dry_run:
        print(to_text(report))
    return 1 if report.fatal else 0


if __name__ == "__main__":
    sys.exit(main())
