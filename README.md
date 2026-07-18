# 🏠 Family HQ

A shared family dashboard for managing tasks, calendar, shopping, meals, and more.

## Features
- 📅 Family calendar integration
- 🛒 Shared shopping list
- ✅ Chores & tasks
- 🍽️ Weekly meal planner
- 📋 School & activities tracker
- 💰 Household budget
- 📝 Family announcements

## Access
- **Dashboard:** [GitHub Pages URL]
- **Data:** [Google Sheets URL]

## Family Members
- Simon (Dad)
- Emma (Mum)
- Ava (Daughter)

## ⚠️ Editing the Apps Script backend (IMPORTANT)

The dashboard's write actions (add shopping item, tick done, delete, add todo,
etc.) call a **Google Apps Script web app**. The web app URL lives in
`index.html` as `API_URL` / `CALENDAR_API_URL`.

**If you edit `apps_script/Code.gs`, you MUST redeploy the web app, or the
dashboard writes will silently fail.**

Why: a web-app deployment is a frozen snapshot of the script *at deploy time*.
Editing `Code.gs` (even via `clasp push`) does **not** update an existing
deployment — the old snapshot keeps serving. Every write then hits stale code
and returns the wrong response instead of saving.

Steps after any backend change:
1. `cd .clasp_clone && clasp push`   (upload the new code to the project)
2. `clasp deploy --description "what changed"`   (creates a NEW deployment ID)
3. Copy the new deployment ID from the output and update `API_URL` +
   `CALENDAR_API_URL` in `index.html` to it.
4. `git add index.html && git commit && git push`

Tip: to test a deployment directly without the UI:
`curl -sL "https://script.google.com/macros/s/<ID>/exec?action=append&sheet=%F0%9F%9B%92%20Shopping%20List&data=%7B%22Item%22%3A%22test%22%7D"`
A working deployment returns `{"success":true,...}`; a stale one returns the
calendar event list instead.
