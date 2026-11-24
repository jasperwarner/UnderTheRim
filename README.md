# D2 upset alerts

Each morning this checks yesterday's NCAA Division II basketball games (men and women), flags upsets, close finishes and overtimes, and writes one page to a Notion database.
Try it without writing anything: `python3 -m upsets.main --date 2026-11-21 --dry-run`
Run the tests: `python3 -m unittest discover -s tests`
It runs on its own in the cloud every day at 6 AM Eastern through GitHub Actions (`.github/workflows/daily.yml`).
First-time setup, click by click: see `SETUP.md`.
