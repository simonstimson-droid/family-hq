# Family HQ web-app deployment — recipe & stale-deployment diagnostic

The dashboard's write actions (add shopping, toggle done, delete, add To-Do,
etc.) call a Google Apps Script **web app** via `API_URL` / `CALENDAR_API_URL`
in `index.html`. The Apps Script source is `apps_script/Code.gs` (handlers:
`append` / `update` / `delete` / `toggleDone`). The deployed URL is baked into
`index.html` as a constant.

## The trap
A web-app deployment is a **frozen snapshot** of the script *at deploy time*.
Editing `Code.gs` (even `clasp push`) does NOT update an existing deployment —
the old snapshot keeps serving. If the dashboard points at a stale deployment,
writes hit old code that ignores `action` and returns the wrong payload (e.g.
the calendar event list) instead of saving. The UI fails silently: no error,
the optimistic local update may flash, then the item is gone on refresh.

## Diagnostic (prove stale vs working, ~1 min)
```bash
# Hit the live URL directly. Healthy returns a proper error for a bogus sheet;
# stale returns the calendar event array regardless of action.
curl -sL "https://script.google.com/macros/s/<DEPLOY_ID>/exec?action=append&sheet=ZZZ_BOGUS&data=%7B%22Item%22%3A%22x%22%7D"
#   Healthy -> {"error":"Sheet not found: ZZZ_BOGUS"}
#   Stale   -> [ ...calendar events... ]   (ignores action -> frozen snapshot)
```
Also confirm the repo `Code.gs` actually has the CRUD handlers:
`grep -c "function appendRow" apps_script/Code.gs`. If it does but the live app
ignores them, it's a deployment problem, not a code problem.

## Fix recipe (copy/paste)
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
#   -> {"success":true,"row":<n>,"message":"Added to Shopping List"}
curl -sL "https://script.google.com/macros/s/$NEW/exec?action=delete&sheet=%F0%9F%9B%92%20Shopping%20List&row=<n>"
# confirm live file:
curl -sL "https://raw.githubusercontent.com/simonstimson-droid/family-hq/main/index.html" | grep -o "<NEW_ID>"
```

## Gotchas
- Run `clasp` from inside `.clasp_clone/` (it holds `.clasp.json`). The project
  is `1IAFtrxUytcYDjpHpKfqk5r1ySe7XxoIKSictvFh2eegyQooDL3PfnhKp`
  ("Family Hq Email Set…"), already authenticated (clasp v3.3.0 at
  `~/.hermes/node/bin/clasp`).
- The raw `/exec` URL 302-redirects, so curl needs `-L`.
- `getSheetByEmoji` matches `name.startsWith(prefix)` — the ` Shopping List`
  tab must keep that prefix or writes fail with "Sheet not found".
- Every future `Code.gs` edit MUST be followed by push + deploy + URL update,
  or the silent failure returns. The repo README "Editing the Apps Script
  backend" section documents this; the OAuth re-auth reminder cron does NOT
  cover deployments (they don't expire, they just go stale).
- Grep the whole repo for the OLD deployment ID after updating, so no shell
  script or README still points at it.
