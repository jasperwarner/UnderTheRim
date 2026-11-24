# Setting up D2 upset alerts

You do this once. It takes about 20 minutes. After that, a Notion page shows up every morning on its own.

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

1. In Notion, create a new page and choose **Database** (a table). Name it: `D2 Upset Alerts`
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
7. Open your Notion database. You should see a new page called **D2 Upsets — Nov 21, 2026** with about **11 flags** and the Status **Check data**.

"Check data" is expected for this date. The warnings at the top will say that one game (Selma at AUM) is listed as not final, and probably that a box score or two looked incomplete. That is the real data for that day, not a problem with your setup.

This matches the saved test run in `docs/test-runs/2026-11-21.txt`. The number of flags may be a little different if a newer weekly poll has come out since: on its very first run the program has no older poll saved yet, so it uses the newest poll, which can change which teams count as ranked (it will also add a warning saying so).

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
- **Failed**: the program could not do its job that day. Nothing reliable on the page. GitHub will also email you.

(Before March 8 it's usually a little after 6 AM; from March 8, when the clocks change, a little after 7 AM. GitHub sometimes starts a few minutes late.)

**If no page shows up by about 9 AM Eastern, treat that as broken**, even if you got no email. Tell Claude.

### Fixing a "possible name mismatch" warning

Sometimes a team is spelled differently in the poll and on the scoreboard, so the program can't tell whether they are the same team. The warning names both spellings. Sometimes they really are two different schools that just have similar names (for example "Grand Valley State" and "Fort Valley St.").

1. First check whether the two names are the same school. A quick web search of both names usually settles it.
2. **Same school:** tell Claude: "Add an alias for the name mismatch warning from [date]." Claude will add it to `aliases.json` and upload it.
3. **Different schools:** tell Claude: "These are different schools — add them to not_same for the warning from [date]." That stops the warning for that pair.

Either way, it stays fixed from then on.

### If the daily run stops (the off-season)

GitHub switches off scheduled jobs in a repository that has had no activity for 60 days. During the season the program saves its data every day, which counts as activity. In the off-season there may be no games, so nothing is saved, and GitHub might pause it. To turn it back on: go to the **Actions** tab, click **D2 upset alerts**, and click the **Enable workflow** button.
