# D1 upsets and story context — design

Status: draft, awaiting Jasper's approval
Date: 2026-11-24
Builds on: `2026-11-23-d2-upset-alerts-design.md` (v1, live)

## Why

Jasper uses the daily page to find story leads for posts. Division I (D1) games get far more attention than Division II (D2), so they want D1 upsets on the same page. When a game looks like a very strong story, they also want background written up in Notion to use when making the post.

## Goals

- D1 men's and women's games get the same upset checks D2 already gets, using the AP Top 25 polls.
- Each flagged game gets a plain "story strength" rating computed by fixed rules, so the best stories are easy to spot.
- Strong stories show the facts the program already has (ranks, records, margin, top scorers) in one place.
- Later (Part 2): Claude writes extra context for the strongest stories, clearly labeled as an AI draft.

## Non-goals

- No posting anywhere, no video, no automatic captions.
- No AI inside the daily program. The program stays rules-only and needs no AI key.
- No list of every D1 game. Only flagged games appear, with their final scores.

## Anti-goals (a failure even if it "works")

- AI text mixed in with the program's own numbers, or any AI step that changes a score, rank or flag.
- AI context that states something as fact that nobody can check.
- A D1 problem (bad poll, missing scoreboard) that silently blanks or corrupts the D2 results, or the reverse.
- A flood of D1 noise that buries the strong stories.

## Approaches considered

| Approach | Trade-off | Verdict |
|---|---|---|
| AI inside the daily program via a paid API key | Fully automatic and simple, but Jasper said no to paying for a key | Rejected by Jasper |
| Rules only, no AI ever | Free, predictable, never invents anything, but it can only list facts, not explain why a game matters | Part 1 |
| Claude scheduled task adds context after the program runs (subscription, no key) | Real writing and judgment, but depends on a Claude task reaching Notion; unverified | Part 2, after Part 1 works |
| Jasper asks Claude for context when posting | Simplest, but not automatic | Fallback if Part 2 doesn't work |

Jasper chose: rules first, then Claude. Part 1 is designed in full below. Part 2 is an outline, to be finished after Part 1 has run for a while.

## Part 1: D1 plus story strength (rules only)

### D1 data

- Scoreboards: same API, `/scoreboard/basketball-{men|women}/d1/YYYY/MM/DD/all-conf`. Same shape as D2 (checked 2026-11-24: 46 men's and 37 women's games on 11/23).
- Polls: AP Top 25 from `/rankings/basketball-{men|women}/d1/associated-press`. It lists rank, school, record and points. School names carry first-place vote counts like `Houston (55)`; those must be stripped before matching.
- A game uses the newest AP poll released before the game day, same as D2. D1 polls are saved the same way D2's are.
- Rules are unchanged: a ranked team loses to an unranked team; the winner is ranked 10 or more spots worse than the loser; bonus tags (margin of 3 or fewer, overtime) only when a ranked team is involved; 35+ point scorers on flagged games.
- D1 teams do play small non-D1 schools (found on 11/21 and 11/22: Calumet College, Alice Lloyd, Milligan and others with no conference). A flag involving one is labeled **"Non-D1 opponent"**, using a D1 conference list the same way `d2_conferences.json` works for D2.
- Name matching uses the same alias, `not_same` and season-team-list machinery, kept separately for D1. D1 names will need new aliases (for example UConn vs Connecticut), so expect a few name warnings in the first days. Real mismatches must still warn.

### Notion page

- Still one page per day, with separate **Division I** and **Division II** sections, men's and women's inside each. D1 first. The page title changes from "D2 Upsets" to "Upsets" for new pages; old pages stay as they are.
- The **Flags** count is the total across both divisions. **Status** (OK / Check data / Failed) keeps its current meaning, applied to both divisions. If one division's data is missing, the other division's flags are still published and the page says clearly which part is missing.
- Each flag shows the final score, the poll week used, and the ncaa.com link, as now.

### Story strength

Each flagged game gets a label from a point score. These are starting values, to be tuned after Jasper sees real days:

| Reason | Points |
|---|---|
| Unranked beat a ranked team | +2 |
| Loser was ranked 1–5 | +3 |
| Loser was ranked 6–10 | +2 |
| Loser was ranked 11–25 | +1 |
| Big rank gap (10+ spots) | +1 |
| Margin of 3 or fewer | +1 |
| Overtime | +1 |
| A player scored 35+ | +1 |
| Division I game | +1 |

Labels: **Big story** (6 or more), **Strong story** (4–5), unlabeled below that. Only the labeled ones get the facts block: both teams' ranks and records (from the poll), score, margin, overtime, top scorers from the box score. Every item in the facts block comes from data the program already fetched. Nothing is looked up elsewhere.

The labels are guides, never a filter. Every flag still appears.

### Left to the builder

- File layout for D1 saved polls, the D1 season team list and the D1 conference list. D2's existing files and paths must keep working untouched.
- How the daily JSON records the division. Existing `data/*.json` must stay readable.
- A one-time backfill of the D1 team list for the season so far, like the D2 one.

### Testing

- Run D1 against real past days (11/21, 11/22, 11/23) and compare flags to the real results and AP polls by hand.
- D2 output on the same days must be unchanged.
- Then the same quiet-period rule as v1: two weeks of daily runs that Jasper compares with reality before trusting them.

## Part 2: Claude-written context (outline, to be finished later)

- A scheduled Claude task runs after the program's page exists. It reads the day's Big and Strong stories, and appends a block headed **"AI draft — check before posting"** under each. It never edits the program's own blocks.
- It runs on Jasper's Claude subscription, so there's no API key and no extra bill.
- Decisions to settle when we get there: whether it may search the web (more useful background, but more risk of wrong claims), how it must mark anything it can't source, and whether a scheduled Claude task can really write to Notion. The last must be tested first. If it can't, the fallback is Jasper asking Claude for context on demand.

## Risks

- D1 name mismatches will be noisy at first.
- The story-strength points are guesses until real days show whether they pick the right games.
- The public NCAA API is unofficial; D1 adds a few more requests per day, well within its limits.
