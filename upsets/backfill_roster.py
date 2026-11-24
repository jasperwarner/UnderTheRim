"""One-time helper: learn every team that has played so far this season.

    python3 -m upsets.backfill_roster [--division d1|d2] --from 2026-11-01 --to 2026-11-22 [--dry-run]

It reads the public scoreboards for each day in the range and adds every team it sees
to data/teams.json (data/teams_d1.json for --division d1; the default is d2). Teams
already in that file keep their current names. It also prints every conference seo it
saw with the number of distinct teams, which is how d1_conferences.json gets built.
Nothing is posted anywhere.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from . import sources
from .http import FetchError
from .roster import GENDERS, add_games, empty_roster, load_roster, save_roster
from .sources import ParseError


def backfill(start: date, end: date, root: Path, *, dry_run: bool, fetch=sources,
             division: str = "d2") -> int:
    """Returns how many scoreboard fetches failed (0 means every day was read)."""
    warnings: list = []
    existing = load_roster(root, warnings, division)
    for w in warnings:
        print(f"Warning: {w}")
    found = empty_roster()
    conf_teams: dict = {}  # conference seo -> set of distinct team seos
    failures = 0
    day = start
    while day <= end:
        counts = []
        for gender in GENDERS:
            try:
                games = fetch.fetch_scoreboard(gender, day, division)
            except (FetchError, ParseError) as e:
                failures += 1
                counts.append(f"{gender}: FAILED ({type(e).__name__})")
                continue
            add_games(found, gender, games)
            for g in games:
                for t in (g.home, g.away):
                    if t.seo:
                        conf_teams.setdefault(t.conference, set()).add(t.seo)
            counts.append(f"{gender}: {len(games)} games")
        print(f"{day}  " + "  ".join(counts))
        day += timedelta(days=1)
    merged = {g: {**found[g], **existing[g]} for g in GENDERS}  # current names win
    for g in GENDERS:
        print(f"{g}: {len(merged[g])} teams ({len(merged[g]) - len(existing[g])} new)")
    print("Conference seos seen (seo, distinct teams):")
    for conf, teams in sorted(conf_teams.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        print(f"  {conf or '(none)'}  {len(teams)}")
    if dry_run:
        print("Dry run: nothing saved.")
    else:
        path = save_roster(merged, root, division)
        print(f"Saved data/{path.name}.")
    return failures


def main(argv: Optional[list] = None, *, fetch=sources, root: Optional[Path] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m upsets.backfill_roster")
    parser.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    parser.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    parser.add_argument("--division", choices=("d1", "d2"), default="d2")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.end < args.start:
        print("Error: --to must not be before --from.", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent.parent if root is None else Path(root)
    failures = backfill(args.start, args.end, root, dry_run=args.dry_run, fetch=fetch,
                        division=args.division)
    if failures:
        print(f"{failures} scoreboard fetch(es) failed — run it again to fill the gaps.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
