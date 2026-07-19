# Family HQ dashboard — data sources & recurring "wrong data" bugs

## Which panel reads which source
| Panel | Source | Path |
|---|---|---|
| Shopping / Chores / To-Do / Meals / Announcements | Apps Script **web app** (`API_URL`) | `index.html` `apiCall({action:'append'/'update'/'delete'/'toggleDone'})` |
| Calendar | Merged Google Sheet `📅 Calendar` + Google Calendar API | `fetch_data.py` |
| School & Activities | `📋 School & Activities` sheet tab, **read directly** | `renderSchool` -> `getSheet('📋')` |
| Family / Birthdays | `👨 Family Members` sheet tab, **read directly** | `getSheet('👨')` |

The web-app panels and the sheet-tab panels are different plumbing. A "write
does nothing" complaint is almost always the web-app deployment (see
`webapp-deploy.md`). A "shows wrong/junk/duplicate data" complaint is almost
always a render function reading the WRONG source.

## Bug class 1 — widget scrapes event text instead of an authoritative column
Seen: "Upcoming Birthdays" filtered `events` for text containing
"birthday"/"🎂". The Calendar sheet held 2026 AND 2027 birthday rows, so:
- Ava appeared **twice** (2026 + 2027 row).
- Simon & Emma appeared as "random" extras.
- Age math was wrong on 2027 rows (year from event date).

**Fix pattern:** compute from the `DOB` column of Family Members
(`DD/MM` or `DD/MM/YYYY`), dedupe by person (one entry each), and only fall back
to a calendar event when a member has no DOB. Add missing DOBs (day/month is
enough; omit the year rather than invent one — age just won't show).

## Bug class 2 — a "dumb mirror" panel that never auto-prunes
`renderSchool` maps **every** row of `📋 School & Activities` with no date logic.
Dated one-off events ("Father's Breakfast", "Summer Fete", "Where's Wally Day")
stay on the list forever after they pass. Nothing in the hourly refresh or the
render filters them. Recurring weekly classes ("Sat 9:15am", "Thu 5:00pm",
"Mon-Fri", "Weekly", "TBC") are not dated and must NEVER be pruned.

**Fix pattern (already built):** `scripts/cleanup_activities.py` + wrapper
`scripts/cleanup_activities_cron.sh`, run weekly by cron job `8f6e153701d0`
(Sun 23:00). It deletes only rows whose `Day/Time` contains a parseable PAST
date; dry-run by default, `--commit` to actually delete; deletes highest row
index first so grid indices don't shift. Extend this pattern to any other tab
that accumulates stale dated one-off rows (e.g. Announcements).

## Bug class 3 — render re-parses a stored string field that doesn't exist
Seen: the individual family-member popup (`openProfile(name)` in `index.html`
~line 3283) showed **"Invalid Date"** for the Birthday row on EVERY member.

Root cause: `myBday` is built as `{ dateStr }` — a single pre-formatted string
(e.g. `"28 October"`), produced in the DOB branch (`parseDOB` ->
`thisYear.toLocaleDateString('en-GB', {day:'numeric', month:'long'})`) and in the
calendar-event fallback branch. The display block then ignored `myBday.dateStr`
and instead ran:
```js
const bdayDate = new Date((myBday.Date || myBday.Start || '') + 'T00:00:00');
const dateStr = bdayDate.toLocaleDateString('en-GB', { day:'numeric', month:'long' });
```
`myBday` has **no** `.Date`/`.Start` key, so this becomes `new Date('T00:00:00')`
-> Invalid Date -> the literal text "Invalid Date" for all four members. The DOB
values themselves were fine (`28/10`, `27/12`, `17/08/2018`, `20/09/2015` all
match the `DD/MM(/YYYY)?` regex in `parseDOB`).

**Fix pattern:** when a render function already computes a display string, USE IT.
Prefer the stored string and only fall back to re-parsing a real date object:
```js
const bdayDate = new Date((myBday.Date || myBday.Start || '') + 'T00:00:00');
const dateStr = (myBday.dateStr && !isNaN(bdayDate.getTime()))
    ? myBday.dateStr
    : bdayDate.toLocaleDateString('en-GB', { day:'numeric', month:'long' });
```
Guard every `new Date(...)` used for display with `isNaN(d.getTime())` so a bad
parse shows the raw source string or a fallback rather than "Invalid Date".
Applies to any popup/modal/info-row that renders a date derived from a sheet cell
or a `myBday`-style object — check that the property name you re-parse actually
exists on the object before trusting it.

## Safe sheet-row delete recipe (agent or script)
See the "Sheets API direct-write cheat sheet" in SKILL.md. Key points: get the
tab's numeric `sheetId` (gid) — the name is not enough for deleteDimension;
delete highest index first; pass the OAuth token as a `Bearer` header, not a
URL query (the `&` trips the shell backgrounding guard). Sheet-row deletes are
authorized per request; the HARD deletion rule applies only to *calendar events*.
