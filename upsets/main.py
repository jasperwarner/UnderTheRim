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
from .names import aliases_for, build_rank_map, load_aliases_by_division
from .notion import NotionClient, NotionError
from .polls_store import poll_for, save_poll
from .report import Report, to_json, to_text
from .roster import add_games, load_roster, roster_path, save_roster
from .rules import add_big_scorers, boxscore_complete, flag_games
from .sources import ParseError
from .story import rate_story

GENDERS = ("men", "women")
IN_SEASON_MONTHS = (11, 12, 1, 2, 3)
FAR_FUTURE = date(9999, 12, 31)


def _safe_aliases(root: Path, warnings: list) -> dict:
    """Read aliases.json; a malformed part only blanks its own division's aliases."""
    try:
        aliases, problems = load_aliases_by_division(root / "aliases.json")
    except (OSError, ValueError, AttributeError, TypeError) as e:
        reason = type(e).__name__
        warnings.append(f"aliases.json couldn't be read ({reason}) — "
                        "name matching may miss ranked teams.")
        return {"men": {}, "women": {}, "not_same": {"men": {}, "women": {}},
                "d1": {"men": {}, "women": {}, "not_same": {"men": {}, "women": {}}}}
    if "d2" in problems:
        warnings.append(f"aliases.json couldn't be read ({type(problems['d2']).__name__}) — "
                        "name matching may miss ranked teams.")
    if "d1" in problems:
        warnings.append(f"Division I aliases couldn't be read ({problems['d1']}) — "
                        "D1 name matching may miss ranked teams.")
    return aliases


DIVISIONS = ("d1", "d2")
DIVISION_TITLES = {"d1": "Division I", "d2": "Division II"}


def _safe_conferences(root: Path, division: str, warnings: list) -> Optional[frozenset]:
    """The conference seos that count as `division`, or None if the list can't be read."""
    name = f"{division}_conferences.json"
    try:
        data = json.loads((root / name).read_text(encoding="utf-8"))
        if not isinstance(data, list) or not data or not all(isinstance(c, str) for c in data):
            raise ValueError("expected a non-empty list of conference names")
        return frozenset(data)
    except (OSError, ValueError) as e:
        warnings.append(f"{name} couldn't be read ({type(e).__name__}) — "
                        f"only teams with no conference are labeled "
                        f"Non-{division.upper()} opponent.")
        return None


def _pick_poll(gender, day, root, fetched, warnings, division="d2", prefix=""):
    """Newest poll released strictly before `day`, from saved polls and today's fetch."""
    saved = poll_for(gender, day, root, warnings, division=division)
    usable_fetched = fetched if fetched is not None and fetched.as_of < day else None
    if usable_fetched is not None and (saved is None or usable_fetched.as_of > saved.as_of):
        return usable_fetched
    if saved is not None:
        return saved
    if fetched is not None:
        warnings.append(
            f"{prefix}{gender.capitalize()}: ranks are from a poll released after this game "
            f"({fetched.as_of})."
        )
        return fetched
    return None


def _rate(flag, records, players, warnings) -> None:
    try:
        rate_story(flag, records, players)
    except Exception as e:  # story labels are extras: never let one stop the run
        warnings.append(f"Story rating failed for {flag.headline} ({type(e).__name__}).")


def run(day: date, root: Path, *, dry_run: bool, fetch=sources,
        notion: Optional[NotionClient] = None, divisions=DIVISIONS,
        secrets: Optional[list] = None) -> Report:
    root = Path(root)
    secrets = list(secrets or [])
    divisions = tuple(d for d in DIVISIONS if d in divisions)  # D1 first, then D2
    if not divisions:
        raise ValueError("run needs at least one division")
    warnings: list[str] = []
    all_aliases = _safe_aliases(root, warnings)
    conferences = {d: _safe_conferences(root, d, warnings) for d in divisions}
    rosters = {d: load_roster(root, warnings, division=d) for d in divisions}
    keys = [(d, g) for d in divisions for g in GENDERS]
    flags: dict[tuple, list] = {k: [] for k in keys}
    all_games: dict[tuple, list] = {k: [] for k in keys}
    final_counts = {k: 0 for k in keys}
    polls_used: dict[tuple, str] = {}
    fatal = False
    scoreboards_down = 0
    total_games = 0
    polls_missing = 0
    failed: set = set()  # slots that crashed part-way: their teams stay off the roster

    for division in divisions:
        title = DIVISION_TITLES[division]
        pre = f"{title}: "
        tag = division.upper()
        aliases = aliases_for(all_aliases, division)
        roster = rosters[division]
        for gender in GENDERS:
            key = (division, gender)
            try:
                cap, low = gender.capitalize(), gender
                poss = "Men's" if gender == "men" else "Women's"
                try:
                    games = fetch.fetch_scoreboard(gender, day, division)
                except (FetchError, ParseError):
                    fatal = True
                    scoreboards_down += 1
                    warnings.append(f"{pre}{cap} scoreboard couldn't be fetched.")
                    polls_used[key] = f"{cap} n/a"
                    continue

                fetched: Optional[Poll] = None
                save_warning = None
                try:
                    fetched = fetch.fetch_poll(gender, division)
                except (FetchError, ParseError):
                    fetched = None
                if fetched is not None and not dry_run:
                    try:
                        save_poll(fetched, root)
                    except OSError:
                        save_warning = f"{pre}{cap} poll couldn't be saved."

                poll = _pick_poll(gender, day, root, fetched, warnings, division, pre)
                if poll is None:
                    polls_missing += 1
                    warnings.append(f"{pre}{poss} poll couldn't be read today — "
                                    f"{low}'s ranked rules skipped.")
                    polls_used[key] = f"{cap} none"
                else:
                    if fetched is None:
                        warnings.append(f"{pre}{poss} poll couldn't be refreshed today — "
                                        "using the saved poll.")
                    saved_newest = poll_for(gender, FAR_FUTURE, root, division=division)
                    newest = max([p.as_of for p in (saved_newest, fetched) if p is not None])
                    label = f"{cap} {poll.label}"
                    if day.month == 3 and poll.as_of == newest:
                        label += " (final poll)"
                    polls_used[key] = label
                    season_end = date(day.year if day.month < 7 else day.year + 1, 3, 1)
                    age = (day - poll.as_of).days
                    if day < season_end and age > 9:
                        warnings.append(f"{pre}{cap} poll is {age} days old.")
                if save_warning:
                    warnings.append(save_warning)

                if not games and day.month in IN_SEASON_MONTHS:
                    warnings.append(f"{pre}No {low}'s games found for {day} — verify on ncaa.com.")
                total_games += len(games)
                all_games[key] = games
                final_counts[key] = sum(1 for g in games if g.is_final)
                for g in games:
                    if not g.is_final:
                        warnings.append(f"Not final ({tag} {low}): {g.away.name} at {g.home.name}"
                                        f" — {g.state or 'unknown'}.")

                ranks: dict[str, int] = {}
                records: dict[str, str] = {}
                if poll is not None:
                    ranks, name_warnings = build_rank_map(poll, games, aliases[gender],
                                                          aliases["not_same"][gender],
                                                          known=roster[gender], records=records)
                    warnings.extend(pre + w for w in name_warnings)
                gender_flags = flag_games(games, ranks, conferences[division], division)
                for flag in gender_flags:
                    try:
                        players = fetch.fetch_boxscore(flag.game.game_id)
                        add_big_scorers(flag, players)
                        complete = boxscore_complete(flag.game, players)
                    except Exception:  # box scores are optional: never let one stop the run
                        warnings.append(f"No box score for {flag.headline}.")
                        _rate(flag, records, [], warnings)
                        continue
                    if not complete:
                        warnings.append(f"Box score incomplete for {flag.headline} "
                                        f"({flag.game.link}) — 35+ check may have missed someone")
                    _rate(flag, records, players, warnings)
                flags[key] = gender_flags
            except Exception as e:  # one slot failing must not blank the other slots
                fatal = True
                failed.add(key)
                flags[key] = []
                polls_used.setdefault(key, f"{gender.capitalize()} n/a")
                warnings.append(f"{DIVISION_TITLES[division]}: {gender.capitalize()} couldn't be "
                                f"checked — unexpected error: {_error_text(e, secrets)}. "
                                "Other divisions' results are still shown.")

    if polls_missing == len(keys):
        fatal = True

    polls_text = " | ".join(
        f"{d.upper()}: " + " · ".join(polls_used[(d, g)] for g in GENDERS) for d in divisions)
    report = Report(day=day, flags=flags, warnings=warnings, final_counts=final_counts,
                    polls_used=polls_text, fatal=fatal, games=all_games)

    # Print first, so the GitHub log has the report even if saving or Notion fails.
    print(to_text(report), flush=True)
    if dry_run:
        return report

    offseason_empty = (4 <= day.month <= 10 and not fatal
                       and total_games == 0
                       and scoreboards_down == 0)
    if offseason_empty:
        return report
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    for division in divisions:
        roster = rosters[division]
        try:  # remember today's teams, so a ranked team that is off tomorrow is recognized
            for gender in GENDERS:
                if (division, gender) not in failed:
                    add_games(roster, gender, all_games[(division, gender)])
            save_roster(roster, root, division=division)
        except OSError as e:
            print(f"Warning: could not save data/{roster_path(root, division).name}: "
                  f"{type(e).__name__}", file=sys.stderr)
    (data_dir / f"{day.isoformat()}.json").write_text(
        json.dumps(to_json(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if notion is not None:
        notion.publish(report)
    return report


def _yesterday_eastern() -> date:
    from zoneinfo import ZoneInfo
    return (datetime.datetime.now(ZoneInfo("America/New_York")) - datetime.timedelta(days=1)).date()


def _error_text(e: BaseException, secrets: list) -> str:
    """'ExcName: first line of the message', with secrets masked and length capped."""
    detail = str(e).splitlines()[0] if str(e) else ""
    for value in secrets:
        if value:
            detail = detail.replace(value, "***")
    if len(detail) > 200:
        detail = detail[:200] + "…"
    return f"{type(e).__name__}: {detail}"


def _crash_message(e: BaseException, secrets: list) -> str:
    return f"Program crashed: {_error_text(e, secrets)}"


def _report_crash(e: BaseException, day: date, notion, secrets: list) -> int:
    """Print and (if possible) publish a Failed page for an unexpected crash. Always 1."""
    report = Report(day=day, flags={("d2", g): [] for g in GENDERS},
                    warnings=[_crash_message(e, secrets)],
                    final_counts={("d2", g): 0 for g in GENDERS}, polls_used="n/a", fatal=True)
    print(to_text(report), flush=True)
    if notion is not None:
        try:
            notion.publish(report)
        except Exception as pe:
            print(f"Error: could not publish the crash report to Notion: "
                  f"{_crash_message(pe, secrets)}", file=sys.stderr)
    return 1


def main(argv: Optional[list] = None, *, fetch=sources, root: Optional[Path] = None,
         notion_factory=NotionClient, env=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m upsets.main")
    parser.add_argument("--date", type=date.fromisoformat, default=None,
                        help="game day, YYYY-MM-DD (default: yesterday, New York time)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the report; write nothing and skip Notion")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    root = Path(__file__).resolve().parent.parent if root is None else Path(root)

    notion = None
    secrets: list = []
    if not args.dry_run:
        token = env.get("NOTION_TOKEN")
        database_id = env.get("NOTION_DATABASE_ID")
        if not token or not database_id:
            print("Error: NOTION_TOKEN and NOTION_DATABASE_ID must be set "
                  "(or use --dry-run).", file=sys.stderr)
            return 1
        secrets = [token, database_id]

    day = None
    try:
        day = args.date or _yesterday_eastern()
        if not args.dry_run:
            notion = notion_factory(token, database_id)
        report = run(day, root, dry_run=args.dry_run, fetch=fetch, notion=notion,
                     secrets=secrets)
    except NotionError as e:
        # The report was already printed above; only the Notion upload failed.
        print(f"Error: could not publish to Notion: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        return _report_crash(e, day or date.today(), notion, secrets)
    return 1 if report.fatal else 0


if __name__ == "__main__":
    sys.exit(main())
