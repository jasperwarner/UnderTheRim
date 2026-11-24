# Setting up the upset alerts

You do this once. It takes about 20 minutes. After that, a Notion page shows up every morning on its own.

The program now checks both Division I (D1, the biggest colleges, ranked by the AP Top 25 poll) and Division II (D2, ranked by the coaches' polls). Both show up on the same page each morning. The setup steps below are the same as before.

You will need: your GitHub account and your Notion account.

**Important:** In step 2 you will get a secret key from Notion. Never paste it into a chat with Claude, and never save it in a file in this project. You will only type it into GitHub (step 5).

---

## Step 1. Make an empty private home for the code on GitHub

1. Go to https://github.com/new and sign in if asked.
2. Next to "Repository name", type: `d2-upsets`
3. Under the name, choose **Private**.
4. Leave everything else alone. Do NOT tick "Add a README file". Leave ".gitignore" and "License" set to "None". The repository must be completely empty.
5. Click the green **Create repository** button.
6. You will land on a page with setup instructions. You don't need to do anything there. Tell Claude the repository is created, and Claude will upload the code for you.

**Good to know:** GitHub only runs the daily schedule, and only shows the "Run workflow" button, when the code is on the branch called `main`. If you ever can't find the button, or the morning pages stop and nothing is red, ask Claude: "Is the code on the main branch on GitHub?"

## Step 2. Create the Notion "robot account" (an integration)

1. Go to https://www.notion.so/profile/integrations and sign in if asked.
2. Click **New integration**.
3. Name it: `D2 Upsets`
4. Choose your workspace if it asks, and keep the type as **Internal**.
5. Click **Save** (or **Create**).
6. Open the **Capabilities** (or "Access") section. Make sure these three are ticked: **Read content**, **Update content**, **Insert content**. Click **Save** if the button appears.
7. Find **Internal Integration Secret**. Click **Show**, then **Copy**. Keep it on your clipboard for step 5. This is the secret key. Do not paste it into chat.

## Step 3. Make the Notion database

You can make it yourself, or ask Claude to create it for you through the Notion connector. If you ask Claude, skip to the "connect" part below.

To make it yourself:

1. In Notion, create a new page and choose **Database** (a table). Name it: `D2 Upset Alerts` (the name is only a label for you. If your database already has this name, keep it, even though it now holds Division I pages too.)
2. Set up these columns exactly, with these spellings and capital letters:
   - **Name**: type "Title" (every database already has this one)
   - **Date**: type "Date"
   - **Flags**: type "Number"
   - **Status**: type "Select". Add three options: `OK`, `Check data`, `Failed`
   - **Polls used**: type "Text"
3. Delete any sample rows Notion added.

To connect the robot to the database (you must do this, or the robot cannot write to it):

1. Open the database page.
2. Click the **...** (three dots) menu in the top right corner.
3. Choose **Connections**.
4. Search for **D2 Upsets** and click it, then confirm if asked.

You should now see "D2 Upsets" listed under Connections.

## Step 4. Copy the database ID

1. Open the database as a full page. Click the **...** menu in the top right, then **Copy link** (or copy the address from your browser's address bar).
2. The link looks like this: `https://www.notion.so/yourname/0123456789abcdef0123456789abcdef?v=...`
3. The database ID is the 32 letters and numbers between the last `/` and the `?v=`. In the example that is `0123456789abcdef0123456789abcdef`. Copy just that part.

This ID is not secret, so it is fine to share it with Claude if you want it checked.

## Step 5. Give GitHub the two secrets

1. Go to your repository on GitHub: `github.com/YOUR-USERNAME/d2-upsets`
2. Click **Settings** (the tab on the far right of the top row).
3. In the left column, click **Secrets and variables**, then click **Actions**.
4. Click the green **New repository secret** button.
5. Next to "Name", type exactly: `NOTION_TOKEN`
6. In the "Secret" box, paste the Internal Integration Secret from step 2. Click **Add secret**.
7. Click **New repository secret** again.
8. Name: `NOTION_DATABASE_ID`. Secret: the 32-character database ID from step 4. Click **Add secret**.

You should now see both names in the list. (GitHub never shows the values again. That is normal.)

## Step 6. Run a first test

Do this after Claude has uploaded the code.

1. On your repository page, click the **Actions** tab.
2. In the left column, click **D2 upset alerts**. (If GitHub asks you to enable workflows, click the green button to do so.)
3. Click the **Run workflow** button on the right. A small box opens.
4. In the "Date to check" box, type: `2026-11-21`
5. Click the green **Run workflow** button in the box.
6. Wait about a minute. Refresh the page. A new line appears with a spinning yellow circle. When it finishes, it turns into a **green check mark**.
7. Open your Notion database. You should see a new page called **Upsets — Nov 21, 2026** (it used to say "D2 Upsets"; the word "D2" is gone because the page now holds both divisions). It has two sections, **Division I** and **Division II**. The Division II section should show about **11 flags**, and the Status should be **Check data**.

"Check data" is expected for this date. The warnings at the top will probably say that a box score or two looked incomplete, and (on a first run) that the Division I ranks come from a poll released after the games. That is the real data for that day, not a problem with your setup.

This matches the saved test runs in `docs/test-runs/2026-11-21.txt` (Division II only, from before Division I was added) and `docs/test-runs/2026-11-21-d1.txt` (both divisions). The number of flags may be a little different if a newer weekly poll has come out since: on its very first run the program has no older poll saved yet, so it uses the newest poll, which can change which teams count as ranked (it will also add a warning saying so).

Please do not treat the Division I results for Nov 21 and Nov 22 in `docs/test-runs/` as the right answer. At that time the program only had the Nov 22 poll, so those results are not ground truth. For example, they miss Villanova beating No. 18 Michigan on Nov 21, and they show Nebraska as No. 21 on Nov 22 when it was No. 24.

If the line turns red, click it to see what went wrong, and show Claude what you see (no secrets in it).

## Step 7. Make sure GitHub emails you when something breaks

That email is your backup alarm, so check it is switched on.

1. On GitHub, click your profile picture (top right), then **Settings**.
2. In the left column, click **Notifications**.
3. Scroll down to the **System** section and find **Actions**.
4. Make sure **Email** is ticked, and tick **Only notify for failed workflows**.

---

## What every morning looks like

At about 6–7 AM Eastern, a new page appears in your database for the previous day's games. The Status column tells you how much to trust it:

- **OK**: everything worked. The list is complete.
- **Check data**: the page was written, but something was a little off. A warning at the top of the page says what. Examples: a game wasn't final yet, a team's name in the poll didn't match the scoreboard, or a box score looked incomplete (so a 35-point game might have been missed). The flags are probably still right.
- **Failed**: some or all of the check could not be done that day (for example, a scoreboard was down, or one part of the program hit an error). The warnings at the top of the page say which part. Any section that was checked is still right: if Division I failed, the Division II results can still be correct, and the other way round. A part that couldn't be checked says **Not checked — see warnings above** instead of "No flags.", so an empty list with no such note really does mean no flags. If a poll was missing, the section says **Ranked-team checks skipped (no poll)**, because the ranked-team rules couldn't run. GitHub will also email you when a day fails.

(Before March 8 it's usually a little after 6 AM; from March 8, when the clocks change, a little after 7 AM. GitHub sometimes starts a few minutes late.)

**If no page shows up by about 9 AM Eastern, treat that as broken**, even if you got no email. Tell Claude.

### What the "Big story" and "Strong story" labels mean

Each flag can now carry a label that says how interesting the game probably is. The program works it out from simple rules, with no guessing: how high the beaten team was ranked, whether an unranked team beat a ranked one, how close the game was, whether it went to overtime, whether a player scored 35 or more, and a small bonus for Division I games. More points means a stronger label:

- **Big story**: the most points. These are the games most worth a look.
- **Strong story**: a step below.
- No label: the game was flagged, but it scored low.

A labeled flag also gets a short block of facts under it (each team's rank and record, the final score, and the top scorer for each team, when the box score is complete).

The labels are only guides. They never hide anything: every flag still shows up on the page whether it has a label or not, and a flag with no label can still be a great game. Treat the label as a hint about where to look first.

### Division I and Division II on one page

Division I and Division II results share one Notion page for each day, in two separate sections (Division I first, then Division II). Each section has its own men's and women's lists. The line at the bottom of the page only shows how many games were checked. Which poll was used for each division is in the **Polls used** column of the database, and in the daily log on GitHub. Ranks are matched only against the right division's poll, so a Division I team is never compared with a Division II poll.

One thing to know about the **Flags** number: a game between a Division I school and a Division II school can show up in both sections, so it can be counted twice in that number.

For Division I the ranks come from the AP Top 25 poll (AP stands for Associated Press, the news agency). On a first run the program has no saved Division I poll yet, so a day from before that can only be checked against the newest poll. When that happens the page says so in a warning ("ranks are from a poll released after this game"), and you should trust that day's Division I flags less. From now on, the program saves each new poll in `data/polls/d1/` as it goes, so new days are checked against the poll that was really in force.

### The files the program keeps

You never need to edit most of these. The program updates the ones it owns itself.

- `aliases.json`: the list of name fixes (see the next section). You or Claude edit this one.
- `d2_conferences.json` and `d1_conferences.json`: which conferences count as Division II and Division I. A team from any other conference is tagged "Non-D2 opponent" or "Non-D1 opponent".
- `data/teams.json` (Division II) and `data/teams_d1.json` (Division I): every team the program has seen on a scoreboard this season. The program uses them to tell "this ranked team did not play today" from "this name does not match anything".
- `data/polls/` (Division II) and `data/polls/d1/` (Division I): the saved weekly polls.
- `docs/test-runs/`: saved example runs you can compare against.

### Fixing a "possible name mismatch" warning

Sometimes a team is spelled differently in the poll and on the scoreboard, so the program can't tell whether they are the same team. The warning names both spellings. Sometimes they really are two different schools that just have similar names (for example "Grand Valley State" and "Fort Valley St.").

The program keeps a list of every team it has seen on a scoreboard this season (the files `data/teams.json` for Division II and `data/teams_d1.json` for Division I, which it updates itself every morning). A ranked team that simply didn't play that day is recognized from that list and does not trigger this warning, so when you do see it, the poll's spelling really doesn't match any team the program has ever seen.

A related warning says: **Poll team "X" was not found on any scoreboard this season**. It means the poll lists a school that the program has never seen play. There are two possible reasons. Either the scoreboard spells the name differently (then it needs an alias), or the school simply has not played a game yet this season (then there is nothing to fix, and the warning goes away on its own once it plays).

1. First check whether the two names are the same school. A quick web search of both names usually settles it.
2. **Same school:** tell Claude: "Add an alias for the name mismatch warning from [date]." Claude will add it to `aliases.json` and upload it.
3. **Different schools:** tell Claude: "These are different schools — add them to not_same for the warning from [date]." That stops the warning for that pair.

Either way, it stays fixed from then on.

**Which part of `aliases.json`?** The warning starts with "Division I:" or "Division II:". Division II fixes go in the main part of the file (the sections called `men`, `women` and `not_same`). Division I fixes go in the separate `d1` section of the same file, which has its own `men`, `women` and `not_same`. This keeps a Division I fix from changing how Division II names are matched. For example, the AP poll says "Southern Cal" while the scoreboard says "Southern California", so the `d1` section has an alias for it.

### If the daily run stops (the off-season)

GitHub switches off scheduled jobs in a repository that has had no activity for 60 days. During the season the program saves its data every day, which counts as activity. In the off-season there may be no games, so nothing is saved, and GitHub might pause it. To turn it back on: go to the **Actions** tab, click **D2 upset alerts**, and click the **Enable workflow** button.
