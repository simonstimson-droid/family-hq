# Calendar Write Operations (authorised)

This documents the **only** sanctioned way to mutate Google Calendar from the
agent, in line with Simon's HARD RULE: *never delete calendars/events without
explicit per-request permission — opt-in only, never automatic/cron/side-effect.*

## Token
- Read-write calendar access lives in `~/.hermes/profiles/home/google_token_calendar.json`
  (scope `https://www.googleapis.com/auth/calendar`).
- It is for Simon's **personal** Google account, which can see Emma's + the
  Family calendar (`family17800354474891822339@group.calendar.google.com`).
- Re-auth: `python3 ~/FamilyHQ/scripts/generate_calendar_token.py url` →
  authorise as the personal account → `exchange <CODE>`. Script backs up the
  old token to `.bak` first.

## Procedure — delete a single event (only when Simon explicitly asks)
1. Confirm the event id (`_cal_id`) and which calendar it lives on.
2. DELETE `https://www.googleapis.com/calendar/v3/calendars/<CAL_ID>/events/<EVENT_ID>`
   with `Authorization: Bearer <access_token>`.
3. Verify with a fresh `fetch_data.py` run that it's gone (event count drops by 1).
4. Regenerate + commit `data.json` so the dashboard matches.

## Preferred alternative — hide WITHOUT deleting
Most "bad event" fixes don't need a delete. Add the event's Google id (or
summary+date) to the `EXCLUDE_CAL_IDS` / `EXCLUDE_SUMMARY_DATE` sets in
`scripts/fetch_data.py` `fetch_calendar_events()`. The dashboard never shows it,
and the source event stays intact. This is the default choice unless Simon
specifically wants the source removed.

## Guardrails
- Never iterate over calendars deleting in bulk.
- Never run a delete from a cron or as a side effect of another task.
- If a delete returns 403/404, stop and report — do not retry blindly.
- The token is read-write by design, but `fetch_data.py` only ever reads;
  deletion is a manual, on-request action only.
