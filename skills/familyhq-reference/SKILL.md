---
name: familyhq-reference
description: "Family HQ project reference — Google Calendar/Sheets IDs, OAuth client, dashboard hosting, email-processor cron wiring, and known pitfalls. Load whenever working on the FamilyHQ repo or its cron jobs."
version: 1.0.0
author: Hermes Agent
platforms: [macos, linux]
tags: [family-hq, google-calendar, google-sheets, oauth, github-pages, email-processor, cron]
---

# Family HQ Reference

Single source of truth for the Family HQ home dashboard project
(repo: `github.com:simonstimson-droid/family-hq.git`, local: `~/FamilyHQ`).
Load this whenever touching FamilyHQ code, `data.json`, calendar/sheets sync,
or the email/reminder cron jobs.

## Repo layout
- `~/FamilyHQ/` — git repo, main branch, pushed to GitHub Pages
- `data.json` — generated dashboard data (calendar merged with sheet tabs);
  **regenerated hourly** by the "Family HQ Data Refresh" cron, so manual edits
  to it are overwritten unless the source is fixed or an exclusion filter drops it
- `index.html` — the dashboard; served from GitHub Pages
  (`simonstimson-droid.github.io/family-hq/`), reads `data.json` from same origin
- `scripts/fetch_data.py` — regenerates `data.json` from Google Sheets + Calendar
  (silent stdout JSON, progress to stderr). Has a `EXCLUDE_CAL_IDS` /
  `EXCLUDE_SUMMARY_DATE` block in `fetch_calendar_events()` to drop specific
  bad events at fetch time (used for the incorrect Ella last-day event)
- `scripts/email_auto_processor.py` — the ONLY real email processor
- `apps_script/Code.gs` + `.clasp_clone/` — standalone Google Apps Script
  (web app + orphaned `processEmails` trigger that crashes ~every 5 min;
  `Code.js` has `deleteOrphanedTriggers()` to kill it)

## Critical IDs
- **Google Family Calendar ID:**
  `family17800354474891822339@group.calendar.google.com`
- **Spreadsheet ID:** `1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA`
- **OAuth client_id:**
  `1061650282541-l08qpbg9q1o7db83nfk12qglnci15ftu.apps.googleusercontent.com`
  (app "Hermes Agent", Testing mode, owner = Simon's personal Google account)
- **Gmail/Sheets account:** `stimsonfamilyhq@gmail.com` — must be added as a
  **Test user** on the OAuth consent screen to sign in (unverified app)

## Tokens (in `~/.hermes/profiles/home/`)
- `google_token.json` — main token (Gmail + Sheets + read-write `calendar`);
  used by `email_auto_processor.py`, `fetch_data.py` Sheets calls
- `google_token_calendar.json` — **read-write `calendar` scope** token for
  Simon's PERSONAL account (sees Emma's + Family calendars, which the
  stimsonfamilyhq account cannot). Used by `fetch_data.py` calendar fetches.
  Backed up to `.bak` before each re-auth.
  ⚠️ **HARD RULE: never DELETE calendars/events without Simon's explicit
  per-request permission** — opt-in only, never automatic/cron/side-effect.
  See `references/calendar-write-ops.md` for the (authorised) procedure and the
  preferred hide-without-delete alternative (`fetch_data.py` EXCLUDE block).

## Cron jobs (profile: home)
- `e5ad20774e86` **Family HQ Email Auto-Processor** — `no_agent`, every 2h,
  runs `scripts/familyhq_email_processor.sh` → `email_auto_processor.py`
  (silent on success). Do NOT route it through `fetch_emails.py` (broken stub:
  prints "Token expired", fabricates demo emails).
- `1a7b2f9dd069` **Family HQ Data Refresh** — `no_agent`, every 60m, regenerates
  `data.json` from Sheets/Calendar and commits/pushes.
- `4f1d0ca23138` **Family HQ Calendar Sync** — `no_agent`, every 120m, same
  fetch+merge+push.
- `2a2f3cd76ccd` Evening Kit Reminder, `096b90ea3125` Passport Ren. Reminder,
  `bec8313cc64e` Daily Briefing, `07d57f8785f8` Weekend Summary,
  `5d11caedac50` Mon Morning Summary, `309535d6f8d0` Week Ahead,
  `ecfe12dd6223` Month Ahead, `978fa36e7b8c` OAuth Re-auth Reminder — all read
  from `data.json`/calendar, so fixing the source data fixes their output.

## Known pitfalls
- Editing `data.json` directly is futile unless the source calendar/sheet event
  is also fixed or an exclusion filter drops it — the hourly refresh re-injects it.
- The Apps Script `processEmails` orphaned trigger spams failure emails into the
  inbox; the Python triage leaves them (low confidence) → hourly noise until the
  trigger is deleted via `deleteOrphanedTriggers()`.
- Google unverified-app OAuth: expect "Advanced → Go to Hermes (unsafe)" at consent.
- `oob` redirect flow may be deprecated by Google; if a re-auth URL errors on
  `redirect_uri`, switch the generator to a localhost loopback flow.

## Token re-auth (Sheets/Gmail token = `google_token.json`)
This is the #1 cause of silent Family HQ breakage — when it dies, the Data
Refresh / Email Auto-Processor / Calendar Sync crons all fail and the dashboard
freezes on stale data. The `OAuth Re-auth Reminder` cron warns, but act on it
fast. Diagnose then re-auth:

1. **Detect which token is dead.** Two separate token files, different scopes:
   - `google_token.json` — Sheets + Gmail (the dashboard's data source + email
     processor). Used by `fetch_data.py` Sheets calls, `email_auto_processor.py`.
   - `google_token_calendar.json` — read-write `calendar` (Simon's PERSONAL
     account; sees Family + Emma calendars). Used by `fetch_data.py` calendar
     fetches.
   Try a refresh on each: POST `https://oauth2.googleapis.com/token` with
   `client_id/secret/refresh_token/grant_type=refresh_token`.
   - **`HTTP 400 { "error": "invalid_grant", "error_description": "Token has
     been expired or revoked." }`** → that token's refresh_token is dead. This is
     the usual case (Google rotates/revokes refresh tokens on re-auth or
     security events). The `access_token` in the file is also stale (401 on use).
   - A successful refresh returns a fresh `access_token` — save it back and move on.
2. **Re-auth the dead one.** You do NOT need a new client_id — it's still valid
   in the dead token file. Build a consent URL from the file's own `client_id`:
   `https://accounts.google.com/o/oauth2/v2/auth?client_id=<cid>&redirect_uri=urn%3Aietf%3Awg%3Aoauth%3A2.0%3Aoob&response_type=code&scope=<space-joined scopes from token file>&access_type=offline&prompt=consent`
   - The `scope` list lives in the token file's `scopes` array — reuse it
     verbatim (typically calendar + spreadsheets + gmail.readonly + gmail.modify).
   - The `oob` (`urn:ietf:wg:oauth:2.0:oob`) redirect still works here; if Google
     ever rejects it, fall back to a localhost loopback flow.
3. **Exchange the code** Simon pastes back:
   POST `https://oauth2.googleapis.com/token` with
   `code, client_id, client_secret, redirect_uri=urn:ietf:wg:oauth:2.0:oob,
   grant_type=authorization_code` → returns `access_token` + a NEW
   `refresh_token` (the old one is now revoked).
4. **Rebuild the token file**, preserving the client creds + scopes from the old
   file so future refreshes keep working:
   `{access_token, token:access_token, refresh_token:<new>, token_uri,
   client_id, client_secret, scopes, expiry, type:"Bearer"}`.
   Write it back over `google_token.json` (or `_calendar.json`).
   ⚠️ **EXPIRY FORMAT TRAP (caused a multi-day silent outage):** the OAuth token
   endpoint returns `expires_in` as an **integer seconds** value (e.g. `3599`).
   Do NOT store that integer as `expiry`. `fetch_data.py` loads the token via
   `google.oauth2.credentials.Credentials.from_authorized_user_file`, which does
   `expiry.rstrip("Z").split(".")[0]` — an **int has no `.rstrip`**, so it
   throws `AttributeError: 'int' object has no attribute 'rstrip'` and
   `fetch_data.py` dies at import. The Data Refresh cron (and Email
   Auto-Processor, Calendar Sync) then fail silently and `data.json` FREEZES on
   stale data — any new sheet column (e.g. the Chores `Day` column) never flows
   through, so widgets look "wrong" with no error. **Always compute `expiry` as
   an ISO-8601 string from `expires_in`:**
   `expiry = (now_utc + timedelta(seconds=expires_in)).isoformat()`. If you ever
   see the `'int' object has no attribute 'rstrip'` crash, that's the cause —
   fix the file's `expiry` field then re-run the Data Refresh wrapper
   (`~/.hermes/profiles/home/scripts/familyhq_data_refresh.sh`), do NOT just
   re-run `python3 scripts/fetch_data.py` (that only prints to stdout; the
   wrapper is what validates + overwrites + commits `data.json`).
5. **Verify** by re-reading the live sheet/calendar with the new token before
   declaring done. Also run the Data Refresh wrapper and confirm `data.json`
   regenerated (check a recently-added column such as `Day` actually appears).

PITFALL: the dashboard `renderChores` groups chores by a **`Day` column** that
may not exist in the sheet yet. If a chore shows under "Monday" (the default
fallback) when it should be mid-week, the `Day` column is missing — INSERT it
(see "Chores `Day` column" below) rather than editing `Frequency`.

## Chores `Day` column (data-model pitfall)
`renderChores()` in `index.html` reads `c.Day` and groups the chore under that
weekday; **any chore with no valid `Day` value falls into the "any day" bucket
which defaults to Monday.** The add-chore form (line ~3056) already sends a
`Day` field, but the `✅ Chores` sheet historically had only
`Task | Assigned To | Due Date | Frequency | Done ✓ | Notes` — NO `Day` column.
So a weekly chore like "Put Bins Out" appeared on Monday until the column was
added. Fix: `insertDimension` a COLUMN at index 4 (between Frequency col D and
Done col E) titled `Day`, then set the row's `Day` to the weekday
(e.g. `Wednesday`). The hourly Data Refresh regenerates `data.json` and the
dashboard groups it correctly — no `index.html` change needed. Same pattern
applies to any "chore shows on wrong day" report.

## Dashboard data-source pitfalls (read BEFORE chasing a "wrong data" bug)
Several dashboard widgets have broken because they read from the WRONG source.
When a panel shows junk/duplicates/missing people, check where its render
function gets its data, not just the sheet:
- **"Upcoming Birthdays" must read the Family Members DOB column, NOT calendar
  events.** A version scraped `events` for text containing "birthday"/"🎂" —
  the Calendar sheet had 2026 AND 2027 birthday rows, so Ava appeared twice and
  Simon/Emma showed as "random" extras, and age math was wrong on 2027 rows.
  Fix: compute from `getSheet('👨')` DOB (DD/MM or DD/MM/YYYY), dedupe by person,
  fall back to calendar event only if a member has no DOB. Add missing DOBs
  (even day/month without year) to Family Members so the widget is consistent.
- **"School & Activities" list is a DUMB MIRROR** of the `📋` tab — `renderSchool`
  maps every row with NO date filtering. Dated one-off events (e.g. "Father's
  Breakfast", "Summer Fete") linger forever after they pass. Nothing auto-prunes
  it; either delete rows manually or run the weekly auto-cleanup cron
  (`scripts/cleanup_activities.py` + `cleanup_activities_cron.sh`, job
  `8f6e153701d0`, Sun 23:00). The cleanup deletes only rows whose `Day/Time`
  holds a PARSEABLE PAST date; recurring classes ("Sat 9:15am", "Mon-Fri",
  "Weekly", "TBC") are never touched. Dry-run by default; `--commit` to delete.
- **Where each panel gets its data:** Shopping/Chores/To-Do/Meal/Announcements =
  the Apps Script web app (see Web-app deployment section). Calendar = merged
  sheet+Google Calendar. Activities/Birthdays/Family = the `📋` / `👨` sheet tabs
  directly (no web app). Mixing these up is the usual root cause of "X is wrong".

## Sheets API direct-write cheat sheet (for sheet-row deletes/updates)
Cron Python scripts and the agent both edit sheets via the REST API, NOT the web
app. Pattern that works:
- Refresh token: POST `https://oauth2.googleapis.com/token` with
  `client_id/secret/refresh_token/grant_type=refresh_token` → `access_token`.
- Read: `GET .../spreadsheets/{ID}/values/{TAB}!A1:E1000` (quote the tab name;
  emoji tabs are fine).
- Get the tab's `sheetId` (gid) from `.../spreadsheets/{ID}?fields=sheets(properties(title,sheetId))`
  — you need it for deleteDimension, the NAME is not enough.
- Delete rows: `POST .../spreadsheets/{ID}:batchUpdate` with
  `requests:[{deleteDimension:{range:{sheetId:GID,dimension:"ROWS",startIndex:r-1,endIndex:r}}}]`.
  Delete HIGHEST row index first so lower indices don't shift mid-loop.
- Put the token in the `Authorization: Bearer` header (not the URL query) — the
  `&` in a query URL string trips the shell's backgrounding guard.
- HARD RULE still applies to *calendar events*, not sheet rows — scripted sheet
  deletes (activity cleanup, birthday-row dedupe) are authorized per request.

## Maintenance
- **This skill is symlinked, not copied:** `~/.hermes/profiles/home/skills/familyhq-reference/SKILL.md`
  → `~/FamilyHQ/skills/familyhq-reference/SKILL.md`. Edit and `git commit` the
  **repo copy**; the symlink keeps the live (auto-loaded) skill in sync. Do NOT
  replace the symlink with a standalone file or the two will diverge.
- Put session-specific recipes in `references/` and keep SKILL.md as the index.
- To add a new reference: `skill_manage action=write_file name=familyhq-reference
  file_path=references/<topic>.md`.

## Tooling gotchas (learned the hard way — save your calls)
- **`search_files` returns 0 / times out on `index.html` (232 KB, emoji-heavy)
  and other large repo files.** It also chokes on regex containing unbalanced
  parentheses (`(`, `)`) — "grep: parentheses not balanced". Symptom: total_count
  0 or a `search_timeout`, even though the pattern is present. **Fix: use
  `terminal` + `grep -n` instead** for any FamilyHQ source search. It is the
  reliable path; `search_files` is fine for small/clean files only.
- **Symlink-vs-standalone confusion:** the live skill
  (`~/.hermes/profiles/home/skills/familyhq-reference/SKILL.md`) is a symlink
  pointing at the repo copy (`~/FamilyHQ/skills/familyhq-reference/SKILL.md`).
  `ls -la` INSIDE the repo shows a *regular file* (correct — the symlink lives
  in the home dir, not the repo). Do NOT conclude the symlink is "broken" just
  because the repo copy is a plain file. To verify integrity, `ls -la` the
  **live** path too; a healthy setup shows `SKILL.md -> /Users/.../FamilyHQ/...`.
- **Read-only Google API calls need explicit user consent** (the terminal tool's
  approval gate). A blocked/timeout read is NOT failure — it means consent wasn't
  given. Stop and ask; never retry or route around a blocked command.
- **Before changing a recurring task's schedule (e.g. "Put Bins Out" day), locate
  the real source of truth first.** A repo-wide search may show NO day field
  (Chores tab stores `Frequency: Weekly` with no weekday column, and there may be
  no calendar event either). The day could live only in the live Sheet or a
  calendar event not visible in the local `data.json` snapshot. Confirm the
  source before editing, or you'll change the wrong thing / miss a source.

## References
- `references/calendar-write-ops.md` — calendar event delete procedure + the
  preferred hide-without-delete (EXCLUDE) alternative. HARD deletion rule.
- `references/webapp-deploy.md` — full clasp push/deploy/URL-update recipe +
  the curl diagnostic that proves a deployment is stale vs working.
- `references/dashboard-data-model.md` — which dashboard panel reads which
  source, the birthdays-scrape vs DOB bug, and the activity auto-cleanup cron.

## Web-app deployment (CRITICAL — writes silently fail if stale)
The dashboard's write path (`addShoppingItem`, `toggleShoppingDone`, `delete*`,
add To-Do, etc.) calls a Google Apps Script **web app** via
`API_URL` / `CALENDAR_API_URL` in `index.html` (around line 2829). The Apps
Script source is `apps_script/Code.gs` (handlers: `append`/`update`/`delete`/
`toggleDone`). It is deployed as a web app; the deployed URL is baked into
`index.html` as a constant.

⚠️ **Stale-deployment trap (this is the #1 cause of "I can't add to the
shopping list"):** if `Code.gs` is edited and **not** redeployed, the old
deployment keeps serving its previous behaviour. History: an early version
only implemented `listEvents`, so every `action=append` just returned the
calendar event list (HTTP 200, no error) — the dashboard's optimistic local
update flashed then vanished on refresh. Symptom: dashboard reads fine, but
adds/toggles/deletes don't persist.

**Diagnostic (do this before touching code):** hit the live URL directly and
confirm it echoes `action`:
```
curl -sL "https://script.google.com/macros/s/<DEPLOY_ID>/exec?action=append&sheet=ZZZ_BOGUS&data=%7B%22Item%22%3A%22x%22%7D"
```
- Healthy deployment → `{"error":"Sheet not found: ZZZ_BOGUS"}`
- Stale (read-only) deployment → returns the calendar event JSON array (ignores
  `action`). That's your proof it's stale.

**Fix:** `clasp` (v3.3.0 at `~/.hermes/node/bin/clasp`) is already authenticated
to the project `1IAFtrxUytcYDjpHpKfqk5r1ySe7XxoIKSictvFh2eegyQooDL3PfnhKp`
("Family Hq Email Set…"). The editable copy of the script lives in
`apps_script/Code.gs`; the `.clasp_clone/` dir is the clasp working dir.
1. `cp apps_script/Code.gs .clasp_clone/Code.js` (clasp pushes `.js`, repo uses
   `.gs` — same content).
2. `cd .clasp_clone && clasp push` (says "already up to date" if code matches).
3. `clasp deploy --description "Family HQ dashboard CRUD web app"` → prints a
   NEW deployment ID `@<n>`.
4. Update BOTH `API_URL` and `CALENDAR_API_URL` in `index.html` to the new ID.
5. `git commit && git push` (GitHub Pages serves the file; raw URL updates
   within a minute, Pages site within ~1 min).
6. Re-run the diagnostic curl against the NEW deployment to confirm
   `{"success":true,...}` on a real append, then delete the test row.

Full recipe + verification transcript: `references/webapp-deploy.md`.

### Web-app deployment recipe (copy/paste)
```bash
cd ~/FamilyHQ
cp apps_script/Code.gs .clasp_clone/Code.js          # clasp pushes .js, repo keeps .gs
cd .clasp_clone && clasp push                        # "already up to date" if code matches
clasp deploy --description "Family HQ dashboard CRUD web app"   # prints NEW_ID @n
# set BOTH API_URL and CALENDAR_API_URL in index.html (~line 2829) to:
#   https://script.google.com/macros/s/<NEW_ID>/exec
cd ~/FamilyHQ && git add index.html && git commit -m "fix: new web-app deployment" && git push
# verify against NEW deployment, then delete the test row:
NEW=<NEW_ID>
curl -sL "https://script.google.com/macros/s/$NEW/exec?action=append&sheet=%F0%9F%9B%92%20Shopping%20List&data=%7B%22Item%22%3A%22VERIFY_OK%22%7D"
#   -> {"success":true,"row":<n>,"message":"Added to 🛒 Shopping List"}
curl -sL "https://script.google.com/macros/s/$NEW/exec?action=delete&sheet=%F0%9F%9B%92%20Shopping%20List&row=<n>"
# confirm live file:
curl -sL "https://raw.githubusercontent.com/simonstimson-droid/family-hq/main/index.html" | grep -o "<NEW_ID>"
```
Gotchas: run `clasp` from inside `.clasp_clone/` (holds `.clasp.json`); the raw
`/exec` URL 302-redirects so curl needs `-L`; `getSheetByEmoji` matches
`name.startsWith(prefix)` so the `🛒 Shopping List` tab must keep that prefix or
writes fail with "Sheet not found". Every future `Code.gs` edit must be followed
by push + deploy + URL update or the silent failure returns.
