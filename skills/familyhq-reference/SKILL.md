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
  ⚠️ **HARD RULE (memory): never DELETE calendars/events without Simon's
  explicit per-request permission — opt-in only, never automatic/cron/side-effect.**

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
  redirect_uri, switch the generator to a localhost loopback flow.
