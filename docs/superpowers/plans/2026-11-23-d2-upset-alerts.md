# D2 Upset Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily program that flags yesterday's D2 men's and women's basketball upsets and writes one Notion page per morning from GitHub Actions.

**Architecture:** A small Python package, `upsets/`, with one file per job: fetching, name matching, rules, poll history, report building and Notion. `upsets/main.py` ties them together and runs as `python -m upsets.main`. A GitHub Actions workflow runs it at 11:00 UTC and commits `data/` back to the repo.

**Tech Stack:** Python standard library only (`urllib`, `json`, `dataclasses`, `zoneinfo`, `difflib`, `unittest`). The code must run on Python 3.9 (the local Mac) and 3.12 (the runner), so use `from __future__ import annotations` and avoid `match`.

**Spec:** `docs/superpowers/specs/2026-11-23-d2-upset-alerts-design.md`

## Global Constraints

- No third-party packages. Tests run with `python3 -m unittest discover -s tests -v` from the repo root.
- API base: `https://ncaa-api.henrygd.me`. Leave at least 0.5 s between any two HTTP requests.
- Scoreboard: `/scoreboard/basketball-{men|women}/d2/YYYY/MM/DD/all-conf`. Box score: `/game/{gameID}/boxscore`. Men's poll: `/rankings/basketball-men/d2/nabc-coaches`. Women's poll: `https://wbca.org/polls-ncaa-division-ii-coaches/` (HTML).
- Game link: `https://www.ncaa.com` + the game's `url` field.
- Thresholds: rank gap **10 or more** spots; close game margin **3 or fewer**; big scorer **35 or more** points.
- "Yesterday" means yesterday in `America/New_York`.
- The program never posts anywhere except the Notion database. No AI anywhere in the data path.
- Secrets come only from env vars `NOTION_TOKEN` and `NOTION_DATABASE_ID`. Never log them.
- The Notion API version header is `Notion-Version: 2022-06-28`.

## Review Focus

1. **The poll can't be fetched, or WBCA changes its page layout.** Expected: that gender's ranked rules are skipped and the page shows the warning `"{Women's|Men's} poll couldn't be read today — {women's|men's} ranked rules skipped."`. It is never treated as "nobody is ranked." Tested in Task 1 (`test_wbca_without_table_raises`) and Task 7 (`test_missing_women_poll_warns`).
2. **A ranked team played but its name didn't match.** Expected: a warning naming both spellings, which tells Jasper to add an entry to `aliases.json`. Tested in Task 2 (`test_near_miss_warns`).
3. **A game isn't final.** That covers postponed games, `gameState` `pre`, a blank score, and an opponent listed as `TBA`. Expected: the game is never flagged and is listed under warnings. Tested in Task 1 (`test_blank_score_is_not_final`) and Task 3 (`test_non_final_never_flagged`).
4. **The same date runs twice.** Expected: one Notion page for that date, not two. Tested in Task 6 (`test_rerun_archives_old_page`).
5. **Re-running an old date after a newer poll is out.** Expected: the program uses the saved poll that was current on that date, or warns `"ranks are from a poll released after this game"`. Tested in Task 4 (`test_poll_for_picks_newest_before`) and Task 7 (`test_rerun_uses_later_poll_with_warning`).

---

### Task 1: Project skeleton, data models, HTTP and parsers

**Files:**
- Create: `.gitignore` (`__pycache__/`, `.env`, `*.pyc`), `upsets/__init__.py`, `upsets/models.py`, `upsets/http.py`, `upsets/sources.py`, `tests/__init__.py`, `tests/test_sources.py`
- Fixtures already in place (real responses): `tests/fixtures/scoreboard_men_2026-11-21.json` (110 games: 105 `FINAL`, 4 `FINAL - OT`, 1 `pre`), `tests/fixtures/scoreboard_women_2026-11-21.json` (109 games), `tests/fixtures/nabc_2026-11-15.json`, `tests/fixtures/wbca_2026-11-17.html`, `tests/fixtures/boxscore_6677046.json`

**Interfaces (Produces):**
```python
# upsets/models.py — all @dataclass
Team(seo: str, name: str, score: int | None, winner: bool, conference: str)   # conference "" = non-D2
Game(game_id: str, gender: str, home: Team, away: Team, state: str, period: str, url: str)
    # properties: is_final -> bool (state == "final" and both scores not None)
    #             overtime -> bool ("OT" in period)
    #             link -> str ("https://www.ncaa.com" + url)
PollEntry(rank: int, name: str)
Poll(gender: str, title: str, as_of: datetime.date, entries: list[PollEntry], source: str, label: str)
    # label: "NABC thru Nov 15" / "WBCA Nov 17" (shown under Polls used)
    # as_of: games dated AFTER as_of are measured against this poll
    # to_json() -> dict / from_json(d: dict) -> Poll (classmethod)
PlayerLine(name: str, team_seo: str, points: int)
Flag(game: Game, headline: str, tags: list[str])

# upsets/http.py
class FetchError(Exception)
get_text(url: str, timeout: float = 20, retries: int = 2) -> str   # sleeps so calls are >=0.5s apart; User-Agent "d2-upsets/1.0"
get_json(url: str) -> Any

# upsets/sources.py
class ParseError(Exception)
parse_scoreboard(data: dict, gender: str) -> list[Game]
parse_nabc(data: dict) -> Poll        # strips " (16)" vote counts; as_of from "Through Games NOV. 15, 2026"
parse_wbca(html: str) -> Poll         # strips " (4-0)" records; as_of = release date (first m/d/yyyy in page) minus 1 day
parse_boxscore(data: dict) -> list[PlayerLine]   # map teamBoxscore[].teamId -> teams[].seoname
fetch_scoreboard(gender: str, day: date) -> list[Game]
fetch_poll(gender: str) -> Poll
fetch_boxscore(game_id: str) -> list[PlayerLine]
```
`gender` is always the string `"men"` or `"women"`.

- [ ] **Step 1: Write failing tests in `tests/test_sources.py`**
  - `test_men_scoreboard_counts`: 110 games, 109 `is_final`, 4 `overtime`.
  - `test_game_fields`: the game with `game_id == "6677046"` has home seo `neb-kearney`, home score 78, home `winner` True, away seo `regis-co`, away score 69, and `link == "https://www.ncaa.com/game/6677046"`.
  - `test_blank_score_is_not_final`: game `6679563` (Selma vs AUM, `pre`) has `is_final` False and scores None.
  - `test_non_d2_conference_blank`: in game `6679563`, away team `selma` has `conference == ""`.
  - `test_nabc`: 25 entries, `entries[0] == PollEntry(1, "Gannon")`, `as_of == date(2026, 11, 15)`, `label == "NABC thru Nov 15"`, and no entry name contains `"("`.
  - `test_wbca`: 25 entries, `entries[0] == PollEntry(1, "Grand Valley State")`, and the entry with rank 3 is named `"Indiana, PA"`. `as_of == date(2026, 11, 16)` and `label == "WBCA Nov 17"`.
  - `test_wbca_without_table_raises`: `parse_wbca("<html>nothing</html>")` raises `ParseError`.
  - `test_wbca_wrong_row_count_raises`: a table with only 3 data rows raises `ParseError`. A real poll has 25 rows, so anything under 20 means the layout changed.
  - `test_boxscore`: the list is non-empty, every `team_seo` is in `{"neb-kearney", "regis-co"}`, and the top scorer has 19 points.
- [ ] **Step 2: Run them and see them fail.** Run `python3 -m unittest tests.test_sources -v`. Expected: ImportError / FAIL.
- [ ] **Step 3: Implement `models.py`, `http.py` and `sources.py` to the interfaces above.** For `parse_wbca`, use regex over `<tr>`/`<td>` plus `html.unescape`, the same approach that worked in recon. `fetch_*` wrap `get_json`/`get_text` and the parsers. Scores convert with `int()` and come out as `None` if blank or not a number.
- [ ] **Step 4: Run the tests and see them pass.** Run `python3 -m unittest tests.test_sources -v`. Expected: all PASS.
- [ ] **Step 5: Commit.** `git init` first if the repo doesn't exist yet. Then `git add -A && git commit -m "feat: data models, HTTP helper and NCAA/WBCA parsers"`.

### Task 2: Team name matching

**Files:**
- Create: `upsets/names.py`, `aliases.json`, `tests/test_names.py`

**Interfaces:**
- Consumes: `Poll`, `Game`, `Team` (Task 1)
- Produces:
```python
normalize(name: str) -> str
load_aliases(path: Path) -> dict[str, dict[str, str]]     # {"men": {poll_name: seo}, "women": {...}}
build_rank_map(poll: Poll, games: list[Game], aliases: dict[str, str]) -> tuple[dict[str, int], list[str]]
    # returns (seo -> rank for ranked teams found in games, warnings)
```
`normalize` does the following, in order: lowercase, straight-quote the curly quotes, delete apostrophes, turn `&` into `and`, turn `-`, `,`, `.` and `(` `)` into spaces, turn the word `state` into `st`, then collapse whitespace.

Matching order is (a) an alias seo, (b) `normalize(poll name) == normalize(team.name)`, (c) `normalize(poll name) == team.seo.replace("-", " ")`. For each poll entry that still isn't matched, check whether any team in `games` has `difflib.SequenceMatcher(None, a, b).ratio() >= 0.75`, comparing normalized names. If one does, add the warning `Possible name mismatch ({gender}): poll "{poll name}" vs scoreboard "{team.name}" ({team.seo}) — add to aliases.json`.

`aliases.json` starts with `{"men": {}, "women": {"Winston-Salem State": "winston-salem"}}`.

- [ ] **Step 1: Write failing tests**
  - `test_normalize`: `normalize("Grand Valley State") == normalize("Grand Valley St.") == "grand valley st"` and `normalize("Texas Woman’s") == "texas womans"`.
  - `test_matches_real_fixture`: running `parse_nabc` and `parse_scoreboard` on the men's fixtures gives a map where `rank_map["gannon"] == 1` and `rank_map["cal-st-east-bay"] == 2`.
  - `test_alias_used`: with women's fixtures plus the real `aliases.json`, `"winston-salem"` is in the map with rank 7.
  - `test_near_miss_warns`: a poll entry `"Cal State Eastbay"` against a game containing `Cal St. East Bay` gives no match and exactly one warning that contains `Cal State Eastbay` and `cal-st-east-bay`.
  - `test_absent_team_no_warning`: a ranked team with no similar name in the games produces no warning. It simply didn't play.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_names -v`. Expected: FAIL.
- [ ] **Step 3: Implement `names.py` and create `aliases.json`.**
- [ ] **Step 4: Run** the same command. Expected: PASS. Then run the full suite.
- [ ] **Step 5: Commit** `feat: poll-to-scoreboard name matching with aliases`

### Task 3: Upset rules

**Files:**
- Create: `upsets/rules.py`, `tests/test_rules.py`

**Interfaces:**
- Consumes: `Game`, `Flag`, `PlayerLine` (Task 1)
- Produces:
```python
flag_games(games: list[Game], ranks: dict[str, int]) -> list[Flag]
add_big_scorers(flag: Flag, players: list[PlayerLine]) -> None    # appends tag(s) in place
```
Only `is_final` games are considered. Let W be the winner and L the loser, with `rW` and `rL` their ranks (None if unranked). A team is `"No. {r} {name}"` when ranked and plain `"{name}"` otherwise. Tags are added in this order:
1. `"Upset"` when `rL` is set and `rW` is None. In that case the headline puts `"Unranked "` before W's name.
2. `"Big rank gap"` when both are set and `rW - rL >= 10`.
3. `"Close ({m} pts)"` when either team is ranked and `margin <= 3`.
4. `"Overtime"` when either team is ranked and `game.overtime`.
5. `"Non-D2 opponent"` as the last tag on an already-flagged game where either `conference == ""`.

A game is flagged only if at least one of tags 1–4 applies. The headline is `"{W label} beat {L label}, {wScore}-{lScore}"`. `add_big_scorers` adds `"35+ pts: {name} {points} ({team seo})"` for each player with 35 or more points.

- [ ] **Step 1: Write failing tests.** Build `Game` objects with a small helper `g(home_seo, hs, away_seo, as_, period="FINAL", state="final", conf="gsc")`.
  - `test_ranked_loses_to_unranked`: ranks `{"b": 7}`, a beats b 71-68 → tags `["Upset", "Close (3 pts)"]`, headline `"Unranked a beat No. 7 b, 71-68"`.
  - `test_rank_gap`: ranks `{"a": 18, "b": 4}`, a beats b 80-70 → tags `["Big rank gap"]`. With `{"a": 13, "b": 4}` there is no flag.
  - `test_favorite_survives_ot`: ranks `{"a": 5}`, a beats b 70-68, period `"FINAL - OT"` → tags `["Close (2 pts)", "Overtime"]`, headline `"No. 5 a beat b, 70-68"`.
  - `test_unranked_close_not_flagged`: no ranks, 60-59 → no flags.
  - `test_non_final_never_flagged`: ranks `{"b": 1}`, `state="pre"` and scores None → no flags.
  - `test_non_d2_label`: ranks `{"b": 3}`, b loses to a with a's `conference=""` → the last tag is `"Non-D2 opponent"`.
  - `test_big_scorer`: `add_big_scorers(flag, [PlayerLine("Zeek Brown", "a", 38), PlayerLine("X", "b", 34)])` → `flag.tags[-1] == "35+ pts: Zeek Brown 38 (a)"`, and only one such tag is added.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_rules -v`. Expected: FAIL.
- [ ] **Step 3: Implement `rules.py`.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: upset, rank-gap, close, OT, non-D2 and big-scorer rules`

### Task 4: Poll history store

**Files:**
- Create: `upsets/polls_store.py`, `tests/test_polls_store.py`

**Interfaces:**
- Consumes: `Poll.to_json` / `Poll.from_json` (Task 1)
- Produces:
```python
save_poll(poll: Poll, root: Path) -> Path            # root/data/polls/{gender}/{as_of}.json, overwrite ok
poll_for(gender: str, game_day: date, root: Path) -> Poll | None   # newest saved poll with as_of < game_day
```
- [ ] **Step 1: Write failing tests** using `tempfile.TemporaryDirectory`.
  - `test_round_trip`: after save, `poll_for` returns an equal Poll.
  - `test_poll_for_picks_newest_before`: save polls with `as_of` 11/15 and 11/22. `poll_for(day=11/21)` returns the 11/15 one, `poll_for(day=11/23)` returns the 11/22 one, and `poll_for(day=11/15)` returns None.
- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: save polls daily and look up the poll in force on a date`

### Task 5: Report building, status and history file

**Files:**
- Create: `upsets/report.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `Flag`, `Game` (Task 1)
- Produces:
```python
@dataclass Report(day: date, flags: dict[str, list[Flag]], warnings: list[str],
                  final_counts: dict[str, int], polls_used: str, fatal: bool = False)
    # property status -> "Failed" if fatal else "Check data" if warnings else "OK"
    # property flag_count -> total flagged games across genders
to_text(r: Report) -> str              # plain text, used for --dry-run and logs
to_json(r: Report) -> dict             # written to data/YYYY-MM-DD.json
to_notion_blocks(r: Report) -> list[dict]
```
The page layout follows the spec. A `heading_2` `"⚠️ Data warnings"` comes first with one bulleted item per warning, and appears only if there are warnings. Then `heading_2` `"Men's"` and `"Women's"`, each with one bulleted item per flag. Each item's rich text is `"{' · '.join(tags)} — {headline} "` followed by a link text `"ncaa.com ↗"` pointing to `game.link`. If a gender has no flags, it gets one paragraph `"No flags."`. The last paragraph is `"Men: {n} final games checked · Women: {n}"`. With zero flags in total, a first paragraph reads `"No upsets yesterday — {men} men's and {women} women's games checked."`.

- [ ] **Step 1: Write failing tests**
  - `test_status`: the status is `"OK"` with no warnings, `"Check data"` with one warning, and `"Failed"` with `fatal=True`.
  - `test_blocks_zero_flags`: the first block's text starts with `"No upsets yesterday — 110 men's and 98 women's games checked."`.
  - `test_blocks_flag_has_link`: a flagged report contains a bulleted item whose rich text includes a `link.url` equal to `game.link`.
  - `test_warnings_first`: with warnings, block 0 is a `heading_2` whose text is `"⚠️ Data warnings"`.
  - `test_json_round_trippable`: `json.dumps(to_json(r))` succeeds and includes `"status"`, `"flags"`, `"warnings"` and `"final_counts"`.
- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: report status, text, JSON and Notion block rendering`

### Task 6: Notion client

**Files:**
- Create: `upsets/notion.py`, `tests/test_notion.py`

**Interfaces:**
- Consumes: `Report`, `to_notion_blocks` (Task 5)
- Produces:
```python
class NotionClient:
    __init__(self, token: str, database_id: str, opener=urllib.request.urlopen)
    publish(self, r: Report) -> str     # returns the page URL
```
`publish` works in four steps:
1. POST `/v1/databases/{id}/query`, filtering on `{"property": "Date", "date": {"equals": "YYYY-MM-DD"}}`.
2. PATCH `/v1/pages/{pid}` with `{"archived": true}` for every result, so there are no duplicates.
3. POST `/v1/pages` with these properties: `Name` (title) `"D2 Upsets — {Mon D, YYYY}"`, `Date`, `Flags` (number), `Status` (select), and `Polls used` (rich_text). Include the first 100 blocks as `children`.
4. If there are more than 100 blocks, PATCH `/v1/blocks/{page_id}/children` in chunks of 100.

Send the headers `Authorization: Bearer {token}`, `Notion-Version: 2022-06-28` and `Content-Type: application/json`. On any HTTP error, raise `FetchError` with the status code and the Notion error message, but never the token.

- [ ] **Step 1: Write failing tests** using a fake opener that records requests and returns canned JSON.
  - `test_rerun_archives_old_page`: when the query returns one existing page, the request sequence is query → PATCH archive → POST create.
  - `test_first_run_creates`: an empty query result means no archive call and one create call whose body has `properties.Status.select.name == r.status`.
  - `test_token_not_in_error`: when the fake opener raises `HTTPError` 401, the `FetchError` message doesn't contain the token string.
- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: Notion publisher that replaces a day's page on re-run`

### Task 7: Main run, data checks and live dry-run

**Files:**
- Create: `upsets/main.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: everything above
- Produces: `run(day: date, root: Path, *, dry_run: bool, fetch=sources, notion: NotionClient | None) -> Report`, plus a CLI: `python -m upsets.main [--date YYYY-MM-DD] [--dry-run]`. The default date is yesterday in `America/New_York`. The exit code is 1 if `report.fatal`, otherwise 0.

`run` does the following, for each gender:
1. Fetch the scoreboard. A `FetchError` sets `fatal` and adds the warning `"{Gender} scoreboard couldn't be fetched."`.
2. Fetch the poll and `save_poll` it. If that fails, keep a warning for later.
3. Pick the poll: `poll_for(gender, day)` if one is saved. Otherwise use the fetched poll and add the warning `"{Gender}: ranks are from a poll released after this game ({as_of})."`. If there's no poll at all, add `"{Gender}'s poll couldn't be read today — {gender}'s ranked rules skipped."` and use `ranks = {}`. If both genders' polls are missing, set `fatal`.
4. Stale poll: if `day < date(day.year if day.month < 7 else day.year + 1, 3, 1)` and `(day - poll.as_of).days > 9`, add `"{Gender} poll is {n} days old."`.
5. Zero games with `day.month in (11, 12, 1, 2, 3)`: add `"No {gender}'s games found for {day} — verify on ncaa.com."`.
6. Each non-final game adds `"Not final ({gender}): {away} at {home} — {state or 'unknown'}."`.
7. Run `build_rank_map`, adding its warnings, then `flag_games`. For each flag, `fetch_boxscore`, then `add_big_scorers`. A failed box score adds `"No box score for {headline}."`.

`polls_used` is `"Men {label} · Women {label}"`, for example `"Men NABC thru Nov 15 · Women WBCA Nov 17"`. Add `" (final poll)"` when `day.month == 3` and the poll is the newest saved one.

When not a dry run: write `data/YYYY-MM-DD.json`, then `notion.publish`. If `day.month` is between 4 and 10 and there are zero games, skip both. With `dry_run`, print `to_text`, write nothing and skip Notion.

- [ ] **Step 1: Write failing tests** with a fake `fetch` module object that returns fixture data and a temp `root`.
  - `test_full_run_on_fixtures`: day 11/21/2026 gives a `Report` with `final_counts == {"men": 109, "women": 109}`, one `"Not final (men)"` warning (Selma at AUM), and status `"Check data"`.
  - `test_missing_women_poll_warns`: when the women's `fetch_poll` raises `FetchError` and nothing is saved, a warning contains `"Women's poll couldn't be read today"`, `fatal` is False and `flags["women"] == []`.
  - `test_both_scoreboards_down_is_fatal`: `fatal` is True and `status == "Failed"`.
  - `test_rerun_uses_later_poll_with_warning`: day 11/10 with only the 11/15 NABC available gives a warning containing `"ranks are from a poll released after this game"`.
- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run** the full suite. Expected: all PASS.
- [ ] **Step 5: Live dry-run on real past dates.** Run `python3 -m upsets.main --date 2026-11-21 --dry-run`, then the same for `2026-11-22`. Expected: no traceback, and counts close to 109 final men's games on 11/21. **Hand-check every flagged line against ncaa.com and the polls**, and note any name-mismatch warnings. Add real mismatches to `aliases.json`, re-run, and save the final output to `docs/test-runs/2026-11-21.txt` and `2026-11-22.txt`.
- [ ] **Step 6: Commit** `feat: daily run with data-quality checks; verified on 11/21 and 11/22`

### Task 8: GitHub workflow and Jasper's setup guide

**Files:**
- Create: `.github/workflows/daily.yml`, `SETUP.md`, `README.md` (5 lines: what it is, how to dry-run)

`daily.yml` has these pieces:
- Triggers: `schedule: - cron: "0 11 * * *"` and `workflow_dispatch` with an optional input `date`.
- `permissions: contents: write`.
- Steps: `actions/checkout@v4`, then `actions/setup-python@v5` with `python-version: "3.12"`, then run tests (`python -m unittest discover -s tests`), then run `python -m upsets.main` (adding `--date "$DATE"` when the input is set) with env `NOTION_TOKEN: ${{ secrets.NOTION_TOKEN }}` and `NOTION_DATABASE_ID: ${{ secrets.NOTION_DATABASE_ID }}`.
- A final step with `if: always()` that commits `data/` as `d2-upsets bot` and pushes. If there's nothing to commit, that's not an error.

`SETUP.md` is plain-language, click-by-click instructions for Jasper:
1. Create a private GitHub repo named `d2-upsets`.
2. Create a Notion internal integration and copy its key.
3. Create the "D2 Upset Alerts" database with the properties Name (title), Date (date), Flags (number), Status (select: OK / Check data / Failed) and Polls used (text), then connect the integration to it. Claude may create the database through the Notion connector if Jasper prefers.
4. Copy the database ID from its URL.
5. Add the two repo secrets.
6. Press "Run workflow" once with date `2026-11-21` and check the page.

The key is never pasted into chat.

- [ ] **Step 1:** Write `daily.yml`. Validate the YAML with `python3 -c "import json,sys; print('ok')"`. No YAML library is available, so read it over carefully and keep it short.
- [ ] **Step 2:** Write `SETUP.md` and `README.md`.
- [ ] **Step 3: Commit** `chore: daily GitHub Actions workflow and setup guide`
- [ ] **Step 4:** Walk Jasper through `SETUP.md` live. Push the repo once it exists. The first workflow run is the end-to-end check, and its Notion page gets compared to `docs/test-runs/2026-11-21.txt`.
