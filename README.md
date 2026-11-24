# Upset alerts (Division I and Division II)

Each morning this checks yesterday's NCAA basketball games, both Division I (ranked by the AP Top 25 poll) and Division II (ranked by the coaches' polls), men and women. It flags upsets, close finishes and overtimes, and writes one page to a Notion database, with a Division I section and a Division II section. Each flag can also carry a "Big story" or "Strong story" label, worked out from simple rules (how highly ranked the beaten team was, how close the game was, and so on) with a few facts under it. The labels are guides to where to look first; they never hide a flag.
Try it without writing anything: `python3 -m upsets.main --date 2026-11-21 --dry-run`
Run the tests: `python3 -m unittest discover -s tests`
It runs on its own in the cloud every day at 6 AM Eastern through GitHub Actions (`.github/workflows/daily.yml`).
First-time setup, click by click: see `SETUP.md`.
