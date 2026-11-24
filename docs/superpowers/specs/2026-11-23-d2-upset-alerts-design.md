# D2 Basketball Upset Alerts — Design

Date: 2026-11-23
Status: draft, awaiting Jasper's approval

## Why

Jasper wants to post stories about NCAA Division II men's and women's basketball. Finding the stories by hand each morning is slow. A small program should check yesterday's games, pick out the upsets, and leave one summary for Jasper to review. Getting the facts right matters more than anything else: nothing goes out unless Jasper has checked it.

## Goals (v1)

- Every morning, check **yesterday's** D2 men's and women's games (Eastern time).
- Flag upsets using the rules below. Each flag gets a one-line reason and a link to the game on ncaa.com.
- Write **one Notion page per morning**, covering men's and women's, into a Notion database.
- Save each day's raw results to the project so trends can be looked at later.
- Run in the cloud (GitHub Actions) at about 6 AM Eastern, whether or not Jasper's laptop is on.

## Non-goals (v1)

- No posting anywhere and no social media.
- No AI-written captions or video scripts. Those come only after a week or more of real runs.
- No game-of-the-week shortlist.
- No video or footage of any kind.
- No transfer portal, power rankings or player spotlights.

## Anti-goals (a failure even if it "works")

- **A wrong fact gets presented as true.** Examples: a wrong score, a wrong rank, or the wrong winner.
- **Silence that hides a problem.** A day with no page, or a page that says "no upsets," is a failure if the real cause was missing or broken data.
- **A ranked team gets silently dropped** because its name didn't match between the poll and the scoreboard.
- An AI step sitting between the data and the page and rewording the numbers.

## Upset rules

These apply to a game only when it is final.

1. **Ranked loses to unranked.** "Unranked Team A beat No. 7 Team B, 71-68."
2. **Big rank gap.** Both teams are ranked and the winner is ranked 10 or more spots worse than the loser. "No. 18 Team A beat No. 4 Team B, 80-77."
3. **Bonus flags.** These are stories in their own right, not just add-ons to an upset. A ranked favorite that survives an unranked team 70-68 in overtime gets flagged even though it won:
   - Final margin of 3 points or fewer, with a ranked team involved.
   - Overtime game with a ranked team involved.
4. **Big scorer: a player with 35 or more points.** Box scores are only fetched for games flagged by rules 1–3 (upsets, close games and overtime games), which keeps requests low. This follows Jasper's original plan. It means a 40-point night in an ordinary game won't be caught in v1.

**Non-D2 opponents** (Jasper's call): the D2 scoreboard includes games against NAIA and other small schools. On 11/21/26 that was 12 of the 110 men's games. These teams show up with an empty `conferenceSeo`. Games against them go through the same rules, but any flag on one is labeled **"(non-D2 opponent)"** so Jasper can judge it separately. *Builder's call:* whether an empty conference alone is a reliable enough signal, or whether D1 opponents also need handling.

A game shows up once on the page, with all its reasons on that line. The **Flags** count is the number of flagged games.

**Which poll is used:** each run saves the polls it fetched to `data/polls/{men,women}/YYYY-MM-DD.json`, keyed by the date the poll was released or "through." A game is scored against the newest saved poll released *before* the game date. If no saved poll covers a re-run date, the page says so plainly ("ranks are from a poll released after this game"). Every page states which poll week it used.

**After the polls stop** (the final regular-season poll comes out before the tournament): keep using the final poll and label it "final poll" under Polls used. Don't fire the stale-poll warning every day.

## Data sources

| What | Source | Notes |
|---|---|---|
| Scores, men's and women's | Public NCAA API `https://ncaa-api.henrygd.me/scoreboard/basketball-{men,women}/d2/YYYY/MM/DD/all-conf` | Confirmed working. 110 men's games on Sat 11/21/26. |
| Box scores | `https://ncaa-api.henrygd.me/game/{gameID}/boxscore` | Confirmed working for D2. |
| Men's poll | `https://ncaa-api.henrygd.me/rankings/basketball-men/d2/nabc-coaches` | NABC Coaches poll. Confirmed, currently "Through Games NOV. 15, 2026." School names carry first-place votes, e.g. "Gannon (16)", which must be stripped. |
| Women's poll | `https://wbca.org/polls-ncaa-division-ii-coaches/` | WBCA Coaches poll, the official one. ncaa.com's copy is empty this season. Read from the HTML table, which has the columns Rank, School (record), Points, Preseason/Previous Rank, First-Place Votes. Records like "(4-0)" must be stripped. |
| Game link for verification | `https://www.ncaa.com` + the game's `url` field, e.g. `/game/6677046` | Included on every flag. |

Docker isn't needed. The public API allows 3 requests per second, and a full day is about 5 requests plus a handful of box scores. Space requests about half a second apart anyway.

## Team name matching

Poll names and scoreboard names differ. Examples: "Grand Valley State" vs "Grand Valley St.", "Winston-Salem State" vs "Winston-Salem", and "Minnesota State" vs "Minnesota St." with seo name `minn-st-mankato`.

- Normalize both sides: lowercase, "State" becomes "St.", and punctuation and curly quotes are dropped.
- Keep a small hand-edited alias file (`aliases.json`) for odd cases. It maps a poll name to a scoreboard seo name, separately for men's and women's.
- **Every ranked team the program can't find on any scoreboard so far this season goes in a warning on the page.** Rule of thumb: if a ranked team played yesterday and wasn't matched, that's a bug. The page must make it visible.
- *Builder's call:* how exactly to detect "unmatched." A simple version is to warn when a ranked team matches no team name in yesterday's games and also isn't on a known "didn't play" list. Pick whatever is reliable.

## Data quality checks (shown at the top of the page)

- The scoreboard returned zero games on a date between Nov 1 and the end of March: "No games found for yesterday — verify on ncaa.com."
- Any game for yesterday is not final, for example postponed or still showing in progress. List it.
- A poll couldn't be fetched or read: "Women's poll couldn't be read today — women's ranked rules skipped." Never treat a missing poll as "nobody is ranked."
- A poll is older than 9 days during the regular season: note it.
- A box score was missing for a flagged game: note it.

**Status rules:**
- `OK` means no warnings.
- `Check data` means any warning above. The page is still written and the run still counts as a success.
- `Failed` means a scoreboard or both polls couldn't be fetched at all, so the page can't be trusted. The program writes a short `Failed` page if Notion can be reached, **and** marks the GitHub run as failed so GitHub sends its failure email. You get two signals, so neither can go missing silently.
- A re-run of the same date updates that day's existing page instead of making a duplicate.
- *Builder's call:* the API has a schedule route, but the obvious path (`/schedule/basketball-men/d2/2026/11`) returned a validation error. If a working schedule route is found, use it to confirm whether games were scheduled. Otherwise the checks above are enough for v1.

## Output: Notion

- A Notion database named **"D2 Upset Alerts"**, with one page per morning.
- Properties: **Date** (the game date), **Flags** (number), **Status** (select: `OK` / `Check data` / `Failed`), and **Polls used** (text, e.g. "Men NABC thru Nov 15 · Women WBCA Nov 17").
- Page body, in order:
  1. Data warnings, if any.
  2. Men's flags.
  3. Women's flags.
  4. A one-line footer with game counts ("Men: 110 final games checked · Women: 98").
- Each flag is one line: the reason plus a link to the ncaa.com game page.
- **A page is written every day, even with zero flags** ("No upsets yesterday — 110 men's and 98 women's games checked"), so a missing page always means something broke.
- On days with no games at all outside the season, still write a short page, or skip it if the date is outside Nov–March. *Builder's call.*
- Writing to Notion uses the official Notion API with an integration key. **Jasper creates the key in Notion and stores it as a GitHub secret themselves.** The builder gives Jasper click-by-click steps, never handles the key directly, and never asks them to paste it into chat.

## Running it: GitHub Actions

- A private GitHub repo. Jasper has a GitHub account with SSH keys on their Mac. The `gh` command-line tool isn't installed, so the builder can install it or walk Jasper through creating the repo on the website.
- A scheduled workflow runs at **11:00 UTC**, which is 6 AM Eastern during basketball season (EST). GitHub's scheduled runs can start 5–30 minutes late, which is fine.
- There's also a manual "Run workflow" button, with an optional date input to re-run any past day.
- After each run, the workflow commits that day's results to `data/YYYY-MM-DD.json` for history.
- If the run crashes outright, GitHub emails the account owner by default. That's the backstop for the Notion page never appearing.
- Python 3.12 on the runner. Use the standard library if practical, so there's nothing to install. *Builder's call.*

## Approaches considered

| Approach | Trade-off | Decision |
|---|---|---|
| Run on Jasper's Mac (launchd) | Free and simple, but the summary only arrives when the laptop is open | Not chosen |
| **Run in the cloud (GitHub Actions)** | Runs on time even with the laptop shut, free, and needs a bit more setup (GitHub repo, secret) | **Chosen by Jasper** |
| Scheduled Claude task posts via Notion connector | No API key needed, but uses Claude usage daily and puts an AI between data and page | Rejected: conflicts with "no bad data" |
| Self-hosted NCAA API in Docker | No outside rate limit, but needs an always-on machine, and Docker isn't installed | Rejected: a daily run is well under the public limit |

## Decisions made by Jasper

- Upset rules as listed, with box scores only for flagged games.
- Games against non-D2 schools are flagged but labeled "(non-D2 opponent)."
- Men's and women's in one daily summary.
- Delivery into a Notion page.
- Runs in the cloud.
- Women's poll comes from the WBCA website.
- No game-of-the-week in v1.

## Calls made by Claude (open to correction)

- Use the public API instead of Docker.
- One Notion database, one page per day, and a page written even on zero-flag days.
- Close and overtime games are flagged even when the favorite wins. One line per game, and Flags counts games.
- Polls are saved daily, and re-runs use the poll that was current on the game date.
- Status rules (OK / Check data / Failed). A failure both writes a page and fails the run so GitHub emails.
- After polls end, the final poll is used without daily stale warnings.
- Save history as daily JSON files in the repo, not a separate database.
- The "cross-check scores against a second source" rule from the original plan isn't automated in v1. Nothing goes public in v1, and every flag links to ncaa.com for a one-click check. It becomes required before any automatic posting is added.

## Known risks

- The NCAA API is unofficial and run by a hobbyist, and the WBCA page could change its layout. Either can break without warning. The program must fail loudly, with a warning on the page or a failed run email, never quietly.
- D2 box scores can be missing.
- Check ncaa.com's terms of use before anything public is built on this data.

## Testing before trusting

- Test against real past dates, for example Sat 11/21/2026 (110 men's games), and compare the flags to the actual results and polls by hand.
- Then two weeks of quiet daily runs. Jasper compares the flags to what actually happened before relying on them.
