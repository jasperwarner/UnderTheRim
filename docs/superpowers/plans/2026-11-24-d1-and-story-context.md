# D1 Upsets and Story Strength Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Division I (D1) men's and women's upset flags to the daily Notion page, rate each flag with a rules-based story strength, and show a facts block for the strongest stories.

**Architecture:** Every place that handled "a gender" now handles "a division plus a gender". D2's saved-file paths, alias keys and output stay exactly as they are; D1 gets its own parallel files. A new `story.py` scores flags by fixed rules. The Notion page gets Division I and Division II sections. No AI anywhere in the program (Claude-written context is a separate later Part 2, not in this plan).

**Tech Stack:** Python 3.9 (local) and 3.12 (CI), stdlib only, `unittest`, the public NCAA API at `https://ncaa-api.henrygd.me`, Notion API 2022-06-28.

**Spec:** `docs/superpowers/specs/2026-11-24-d1-and-story-context-design.md` (builds on `2026-11-23-d2-upset-alerts-design.md`).

## Global Constraints

- Stdlib only. Every module starts with `from __future__ import annotations`. Tests: `python3 -m unittest discover -s tests` must pass on 3.9.
- Work on a new branch `d1-story` in `/Users/jasper/Claude/d2-upsets`. Commit on the branch as you go. **Never merge to `main` or push**: Jasper must say yes first.
- The program never posts anywhere except the Notion database. Secrets only come from env vars and are never logged. No AI in the program.
- D2 must keep working untouched: `data/polls/{men,women}/`, `data/teams.json`, the top-level `men`/`women`/`not_same` keys in `aliases.json`, `d2_conferences.json`, and already-saved poll files (which have no `division` or `record` fields) must all keep loading.
- D1 files live beside them: `data/polls/d1/{men,women}/`, `data/teams_d1.json`, a `"d1"` key in `aliases.json`, `d1_conferences.json`.
- Rules are unchanged: a ranked team loses to an unranked team; winner ranked 10 or more spots worse than the loser; margin of 3 or fewer or overtime only when a ranked team is involved; 35+ points checked only on flagged games.
- Every flag has a source link. Data that looks empty or wrong gets a warning on the page. Fail loudly, never quietly.
- Requests stay at least 0.5 s apart (existing `http.py` throttle).
- A division's failure must not blank the other division's flags.
- Story labels never hide or remove a flag. Facts shown must come only from data the program already fetched.

## Review Focus

Most likely first. Each has a test in the task that owns the code.

1. A D1 poll team whose name doesn't match the scoreboard (UConn vs Connecticut, Miami (FL), Saint Mary's) must warn, not silently lose its ranking. (Task 2, Task 6)
2. A D2 or NAIA team on the D1 scoreboard may carry a real D2 conference name; "Non-D1 opponent" must use an allowlist of D1 conferences, not an empty-conference check. (Task 3, Task 6)
3. One division's scoreboard or poll failing must still publish the other division's flags and show what is missing. (Task 5)
4. D2 output on real days (11/21, 11/22, 11/23) must have the same flags, headlines and tags as before, and old saved D2 polls must still load. (Task 1, Task 6)
5. The 35+ scorer tag arrives after the box score, so story points must be computed after it; label boundaries (3, 4, 5, 6 points) must be exact; top scorers are shown only when the box score is complete. (Task 3)

---

### Task 1: Division-aware models and sources

**Files:**
- Modify: `upsets/models.py`, `upsets/sources.py`
- Create: `tests/fixtures/scoreboard_d1_men_2026-11-23.json`, `tests/fixtures/ap_men_2026-11-22.json`, `tests/fixtures/ap_women_2026-11-22.json`
- Test: `tests/test_sources.py`, plus a test in `tests/test_polls_store.py` or a new `tests/test_models.py`

**Interfaces:**
- Produces:
  - `Game.division: str = "d2"` (new last field with default); `Poll.division: str = "d2"`; `PollEntry.record: str = ""`.
  - `Poll.to_json()` includes `"division"`, and each entry's `"record"` only when non-empty. `Poll.from_json()` reads `division` (default `"d2"`) and `record` (default `""`; must be a string if present). Old saved files load unchanged.
  - `sources.parse_scoreboard(data, gender, division="d2") -> list[Game]`
  - `sources.parse_ap(data: dict, gender: str) -> Poll` (division `"d1"`, label `f"AP thru {Mon d}"`, source = the AP rankings URL, rows' `RECORD` kept)
  - `sources.fetch_scoreboard(gender, day, division="d2")` (URL uses `d1` or `d2`)
  - `sources.fetch_poll(gender, division="d2")`: D1 uses `/rankings/basketball-{men|women}/d1/associated-press`; D2 unchanged.

- [ ] **Step 1: Save fixtures from the live API** (real data, one call each, 0.6 s apart): D1 men's scoreboard for 2026/11/23 and both AP polls (`curl -s` into the three fixture files above).
- [ ] **Step 2: Write failing tests**:
  - `ParseApTest.test_men_poll`: parsing `ap_men_2026-11-22.json` gives 25 entries, rank 1 name `Houston` (the ` (55)` vote count stripped), `as_of == date(2026, 11, 22)`, label `AP thru Nov 22`, division `d1`, rank 1 record `6-0`.
  - `test_school_with_parenthesis_kept`: a row `"Miami (FL)"` keeps its name; `"Houston (55)"` loses only the digits.
  - `test_ap_bad_shape_raises_parse_error` and `test_ap_too_few_entries_raises` (use `_check_poll`).
  - `ParseScoreboardTest.test_d1_division_set`: every game from the D1 fixture has `division == "d1"`; the existing D2 fixture games have `division == "d2"`.
  - `PollJsonTest.test_old_saved_poll_still_loads`: a dict with no `division`/`record` loads with `division == "d2"` and `record == ""`; a round trip of a D1 poll keeps both.
  - `FetchUrlTest`: with a fake `get_json` recording the URL, `fetch_scoreboard("men", day, "d1")` asks for `/scoreboard/basketball-men/d1/2026/11/23/all-conf`, and `fetch_poll("women", "d1")` asks for `/rankings/basketball-women/d1/associated-press`.
- [ ] **Step 3: Run them** (`python3 -m unittest tests.test_sources -v`): expect failures.
- [ ] **Step 4: Implement** the interfaces above in `models.py` and `sources.py`. `parse_ap` follows `parse_nabc` (same date regex works for `Through Games NOV. 22, 2026`); strip only a trailing `(digits)`.
- [ ] **Step 5: Run the full suite**: all pass, D2 untouched.
- [ ] **Step 6: Commit** on branch `d1-story`: `git add -A && git commit -m "Read D1 scoreboards and AP polls"` (end with the Co-Authored-By trailer).

---

### Task 2: Division-aware storage and name matching

**Files:**
- Modify: `upsets/polls_store.py`, `upsets/roster.py`, `upsets/names.py`, `upsets/backfill_roster.py` (signature plumbing only), `aliases.json` (add an empty `"d1"` section)
- Test: `tests/test_polls_store.py`, `tests/test_roster.py`, `tests/test_names.py`, `tests/test_backfill_roster.py`

**Interfaces:**
- Consumes: `Poll.division` (Task 1).
- Produces:
  - `polls_store.save_poll(poll, root)` writes D2 polls to `data/polls/{gender}/` (unchanged) and D1 polls to `data/polls/d1/{gender}/`; `poll_for(gender, game_day, root, warnings=None, division="d2")`.
  - `roster.roster_path(root, division="d2")`: D2 → `data/teams.json`, D1 → `data/teams_d1.json`; `load_roster(root, warnings=None, division="d2")`; `save_roster(roster, root, division="d2")`. `add_games` unchanged.
  - `names.load_aliases(path)` result gains key `"d1"`: `{"men": {...}, "women": {...}, "not_same": {"men": {...}, "women": {...}}}`, all empty if absent; same validation as D2. `names.aliases_for(aliases: dict, division: str) -> dict`: for `"d2"` returns the top-level `men`/`women`/`not_same` dict, for `"d1"` returns the `"d1"` dict.
  - `names.build_rank_map(poll, games, aliases, not_same=None, known=None, records=None)`: when `records` (a dict) is given, set `records[seo] = entry.record` for each matched entry (the best-ranked entry wins on duplicates; only non-empty records).

- [ ] **Step 1: Write failing tests**: a D1 poll saves to `data/polls/d1/men/2026-11-22.json` while a D2 poll still saves to `data/polls/men/…`; `poll_for` with `division="d1"` never returns a D2 poll and vice versa; an old D2 file still loads; D1 roster saves and loads separately from D2's; `load_aliases` on today's `aliases.json` still returns the same D2 values and an empty `"d1"`; `aliases_for` returns the right branch; `build_rank_map` fills `records` and leaves it alone when not given; a D1 poll name that matches nothing and resembles a scoreboard team still produces the near-miss warning (use "Connecticut" vs scoreboard "UConn"-style names).
- [ ] **Step 2: Run, see failures. Step 3: Implement. Step 4: Run the full suite.**
- [ ] **Step 5: Commit**: `git commit -am "Keep D1 files beside D2's"`.

---

### Task 3: Flag rules for both divisions and story strength

**Files:**
- Modify: `upsets/models.py` (Flag), `upsets/rules.py`
- Create: `upsets/story.py`, `tests/test_story.py`
- Test: `tests/test_rules.py`

**Interfaces:**
- Produces:
  - `Flag` gains defaults: `division: str = "d2"`, `winner_rank: Optional[int] = None`, `loser_rank: Optional[int] = None`, `story_points: int = 0`, `story: str = ""`, `facts: list[str]`.
  - `rules.flag_games(games, ranks, conferences=None, division="d2") -> list[Flag]`: same behavior as today; `conferences` is the allowlist for that division; a team outside it adds tag `"Non-D2 opponent"` (D2) or `"Non-D1 opponent"` (D1); the flag records `division`, `winner_rank`, `loser_rank`. Calls that pass the old third positional argument keep working.
  - `story.STRONG_AT = 4`, `story.BIG_AT = 6`.
  - `story.story_points(flag) -> int`. Points: unranked winner over a ranked loser +2; loser ranked 1–5 +3, 6–10 +2, 11–25 +1; tag "Big rank gap" +1; a `Close` tag +1; "Overtime" tag +1; a `35+ pts` tag +1; `division == "d1"` +1.
  - `story.rate_story(flag, records: dict[str, str], players: list[PlayerLine]) -> None`: sets `story_points`; `story` is `"Big story"` at 6 or more, `"Strong story"` at 4–5, else `""`. When a label is set it fills `facts` with plain lines: each team's rank (or "unranked") and poll record when known; final score and margin; overtime when present; and each team's top scorer **only if** `boxscore_complete(flag.game, players)` is true, otherwise one line `"Box score incomplete — top scorers not shown."`. When no label, `facts` stays empty.

- [ ] **Step 1: Write failing tests** in `tests/test_story.py`:
  - `test_big_story`: D1 game, unranked beats No. 3 in overtime → 2+3+1+1 = 7 → `Big story`.
  - `test_strong_story`: D2, unranked beats No. 8 by 2 → 2+2+1 = 5 → `Strong story`.
  - `test_boundaries`: 3 points → `""`, 4 → `Strong story`, 5 → `Strong story`, 6 → `Big story`. Use flags built directly so each boundary is exact.
  - `test_35_points_can_lift_label`: D2, unranked beats No. 12 (2+1 = 3, no label); after `add_big_scorers` adds a `35+ pts` tag and `rate_story` runs, the label is `Strong story`.
  - `test_facts_use_poll_records_and_scorers`: records `{"a": "6-0"}`, complete box score → facts mention `6-0`, the score, and each top scorer by name.
  - `test_incomplete_box_score_hides_scorers`: facts hold the "Box score incomplete" line and no player names.
  - `test_unlabeled_has_no_facts`.
  In `tests/test_rules.py`: `test_non_d1_label_uses_d1_allowlist` (a team with a D2 conference seo on a D1 game gets `Non-D1 opponent`; a D1 conference team does not); `test_flag_records_ranks` (`winner_rank`/`loser_rank` set); every existing test still passes unchanged.
- [ ] **Step 2: Run, see failures. Step 3: Implement. Step 4: Run the full suite.**
- [ ] **Step 5: Commit**: `git commit -am "Rate flags by story strength"`.

---

### Task 4: Report and Notion page with divisions

**Files:**
- Modify: `upsets/report.py`, `upsets/notion.py`, `upsets/main.py` (adapt to the new Report keys, **D2 only for now**, no D1 fetching yet)
- Test: `tests/test_report.py`, `tests/test_notion.py`, `tests/test_main.py` (update to the new keys)

**Interfaces:**
- Produces:
  - `Report.flags`, `Report.final_counts`, `Report.games` are keyed by `(division, gender)`, e.g. `("d2", "men")`. `Report.polls_used` stays a string. `flag_count` sums all.
  - `report.SECTIONS = (("d1", "Division I"), ("d2", "Division II"))`. Output (`to_text`, `to_notion_blocks`) shows a division section only for divisions that appear as keys in `flags`, D1 first. Each section has `Men's` and `Women's` parts. A division heading is `heading_2`, a gender heading `heading_3`.
  - A labeled flag's line starts with its label (`Big story · …` / `Strong story · …`); its `facts` follow as one indented/child block each (a paragraph right after the bullet is acceptable if nesting is awkward).
  - Footer: per division and gender, the number of final games checked.
  - `to_json`: each flag gets `division`, `story`, `story_points`, `facts`, `winner_rank`, `loser_rank`; `games` and `final_counts` are grouped by division then gender. Already-saved `data/*.json` files are left as they are.
  - Notion page title: `Upsets — Nov 23, 2026` (no "D2"). Properties unchanged.

- [ ] **Step 1: Write failing tests**: text and Notion output with only D2 keys shows only a Division II section; with both, D1 comes first; a labeled flag shows its label and facts, an unlabeled flag shows neither; the "no upsets" line counts games across divisions; `to_json` keys; Notion title; block-chunking at 100 still works with the extra headings. Update existing tests to the new keys.
- [ ] **Step 2: Run, see failures. Step 3: Implement. Step 4: Run the full suite**: `main` still produces a D2-only run that passes its existing tests (updated for the new keys only).
- [ ] **Step 5: Commit**: `git commit -am "Page sections for each division"`.

---

### Task 5: Run both divisions in the daily program

**Files:**
- Modify: `upsets/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces:
  - `run(day, root, *, dry_run, fetch=sources, notion=None, divisions=("d1", "d2")) -> Report`. For each division then gender: fetch scoreboard (division-aware), fetch and save poll, pick poll (`poll_for(..., division=...)`), load that division's roster/aliases (`aliases_for`) and conference list (`d2_conferences.json` / `d1_conferences.json`, same safe-loading as D2), build ranks with `records`, flag games, fetch box scores for flagged games, `add_big_scorers`, then `rate_story`, and finally add the day's teams to that division's roster.
  - Warnings name the division when ambiguous (`"Division I: Men's poll couldn't be read today — …"`); update affected test strings.
  - `polls_used` is one readable string covering all four polls, e.g. `D1: Men AP thru Nov 22 · Women AP thru Nov 22 | D2: Men NABC thru Nov 15 · Women WBCA Nov 17`.
  - Status rules: `fatal` when any scoreboard can't be fetched, or when every poll is missing. A failure in one division still publishes the other division's flags, and the warning says which part is missing. Crash handling (`Failed` page, exit 1) is unchanged.
  - A missing or unreadable `d1_conferences.json` produces a warning and falls back to the empty-conference rule, like D2.

- [ ] **Step 1: Write failing tests** with fake fetchers: both divisions flag and appear; **D1 scoreboard down → D2 flags still published, status Failed, warning says Division I**; the reverse; D1 poll missing → D1 ranked rules skipped with a warning while D2 is unaffected; D1 poll saved under `data/polls/d1/…` and the D1 roster saved to `data/teams_d1.json` on a real run, neither written on a dry run; `divisions=("d2",)` reproduces today's D2-only behavior; D2 flags, headlines and tags for the existing D2 fixtures are identical to before; story labels set after the 35+ tag (a fake box score with a 35-point scorer lifts a flag).
- [ ] **Step 2: Run, see failures. Step 3: Implement. Step 4: Run the full suite.**
- [ ] **Step 5: Commit**: `git commit -am "Check D1 and D2 in one run"`.

---

### Task 6: D1 team list, conference list, and backfill

**Files:**
- Modify: `upsets/backfill_roster.py` (add `--division d1|d2`, default `d2`)
- Create: `d1_conferences.json`, `data/teams_d1.json` (generated), a test in `tests/test_backfill_roster.py` and `tests/test_main.py` (or a new `tests/test_conferences.py`)

**Interfaces:**
- Produces: `backfill(start, end, root, *, dry_run, fetch=sources, division="d2")`; the D1 run prints the conference seos it saw. `d1_conferences.json` is a JSON list of D1 conference seos (strings, non-empty, sorted).

- [ ] **Step 1: Write failing tests**: `--division d1` fetches D1 scoreboards and writes `data/teams_d1.json`, not `teams.json`; D2 behavior unchanged; `d1_conferences.json` loads, has no blanks, and shares no entry with `d2_conferences.json`.
- [ ] **Step 2: Implement the CLI flag. Run the suite.**
- [ ] **Step 3: Run it live once**, D1 only: `python3 -m upsets.backfill_roster --division d1 --from 2026-10-31 --to 2026-11-23`. Build `d1_conferences.json` from the conference seos seen on D1 scoreboards, minus empty ones and minus anything in `d2_conferences.json`. Print the final list in the task report so Jasper can read it, and note any seo that looks like a D2/NAIA conference.
- [ ] **Step 4: Commit**: `git add -A && git commit -m "D1 team list and conference list"`.

---

### Task 7: Real-day check, D1 aliases, and docs

**Files:**
- Modify: `aliases.json` (`"d1"` section), `SETUP.md`, `README.md`
- Create: `docs/test-runs/2026-11-2{1,2,3}-d1.txt`

- [ ] **Step 1: Dry-run the three real days (11/21, 11/22, 11/23)** with both divisions: `python3 -m upsets.main --date 2026-11-21 --dry-run` (and 22, 23), saving each output under `docs/test-runs/` as `…-d1.txt`.
- [ ] **Step 2: D2 regression.** Compare the D2 part to `docs/test-runs/2026-11-21.txt` and `2026-11-22.txt` and to the known counts on 11/23. Flags, headlines and tags must match; only labels and facts may be new. Report any difference.
- [ ] **Step 3: Name warnings.** For each D1 near-miss warning, decide if it is the same school (add to the `"d1"` aliases) or different schools (add to `"d1"` `not_same`). Re-run until D1 name warnings are only real ones. Do not hide a warning without a reason.
- [ ] **Step 4: Spot-check D1 flags** against the real ncaa.com scoreboard and the AP poll for each flagged game (score, who was ranked, source link). Put a short table of D1 flags with their links in the task report so Jasper can check them by hand.
- [ ] **Step 5: Docs.** `SETUP.md`: D1 is now included, what the Big/Strong story labels mean and that they are guides, the new files (`d1_conferences.json`, `data/teams_d1.json`, `data/polls/d1/`), the page title change, and when to add a D1 alias. `README.md`: one paragraph.
- [ ] **Step 6: Run the full suite one last time and commit**: `git add -A && git commit -m "D1 aliases, real-day checks and docs"`.

---

## Not in this plan

- Part 2 (Claude-written context via a scheduled Claude task). It needs a test that a scheduled Claude task can write to Jasper's Notion; it gets its own plan once Part 1 has run.
- Merging to `main` and pushing. Both wait for Jasper's yes.
