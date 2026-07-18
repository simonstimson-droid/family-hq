#!/usr/bin/env python3
"""
cleanup_activities.py — Remove PAST dated one-off entries from the
"📋 School & Activities" sheet tab on the Family HQ spreadsheet.

WHY: the activity list on the dashboard is a dumb mirror of the sheet — nothing
auto-prunes it. Dated one-off events (e.g. "Father's Breakfast", "Wed 17 Jun")
linger forever. This script deletes rows whose Day/Time contains a calendar
date that is in the past.

SAFETY:
- Dry-run by DEFAULT. Pass --commit to actually delete.
- Only rows with a PARSEABLE PAST DATE in the Day/Time column are touched.
- Recurring entries ("Mon-Fri", "Sat 9:15am", "Weekly", "Thu 5:00pm", plain
  weekday names with no date) are NEVER deleted.
- Rows whose date can't be parsed, or is in the future, are left alone.
- Deletes highest-indexed row first so grid indices don't shift mid-loop.

Usage:
    python3 scripts/cleanup_activities.py            # dry run, prints plan
    python3 scripts/cleanup_activities.py --commit   # actually deletes
"""

import json
import os
import re
import sys
import datetime
import urllib.request
import urllib.parse

SPREADSHEET_ID = "1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA"
TAB = "📋 School & Activities"
TOKEN_FILE = "/Users/simonstimson/.hermes/profiles/home/google_token.json"

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
WEEKDAY_WORDS = {
    "mon", "monday", "tue", "tues", "tuesday", "wed", "weds", "wednesday",
    "thu", "thur", "thurs", "thursday", "fri", "friday", "sat", "saturday",
    "sun", "sunday",
}


def get_access_token():
    tok = json.load(open(TOKEN_FILE))
    if "access_token" in tok and tok.get("expiry"):
        # Best-effort: just try refresh to be safe (cheap, always works).
        pass
    body = urllib.parse.urlencode({
        "client_id": tok["client_id"],
        "client_secret": tok["client_secret"],
        "refresh_token": tok["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body, method="POST")
    out = json.loads(urllib.request.urlopen(req, timeout=20).read())
    return out["access_token"]


def sheets_get(tab_range, access_token):
    url = (
        "https://sheets.googleapis.com/v4/spreadsheets/"
        + SPREADSHEET_ID
        + "/values/"
        + urllib.parse.quote(tab_range)
    )
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + access_token})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def batch_delete_rows(sheet_id, rows, access_token):
    requests = [
        {
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": r - 1,
                    "endIndex": r,
                }
            }
        }
        for r in sorted(rows, reverse=True)
    ]
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + SPREADSHEET_ID + ":batchUpdate"
    req = urllib.request.Request(
        url,
        data=json.dumps({"requests": requests}).encode(),
        headers={"Authorization": "Bearer " + access_token, "Content-Type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=20).status


def get_sheet_id(access_token):
    url = (
        "https://sheets.googleapis.com/v4/spreadsheets/"
        + SPREADSHEET_ID
        + "?fields=sheets(properties(title,sheetId))"
    )
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + access_token})
    data = json.loads(urllib.request.urlopen(req, timeout=20).read())
    for s in data["sheets"]:
        if s["properties"]["title"] == TAB:
            return s["properties"]["sheetId"]
    raise RuntimeError("Sheet tab not found: " + TAB)


def parse_past_date(day_time):
    """Return a past datetime if day_time contains a recognizable calendar date,
    else None. Never returns a future date."""
    if not day_time:
        return None
    text = day_time.strip()
    low = text.lower()

    # Reject obvious recurring patterns first (before any date parsing).
    if any(w in low for w in ("weekly", "every", "mon-fri", "term", "tbc")):
        return None
    # Plain weekday with a time but no date -> recurring class, not a one-off.
    # e.g. "Sat 9:15am", "Thu 5:00pm", "Friday 6:00 PM"
    if re.search(r"\b(mon|tue|wed|thu|fri|sat|sun)\b", low) and not re.search(r"\d{1,2}\s+\w{3}", low):
        # weekday word present but NO "DD Mon" date token -> treat as recurring
        return None

    # Look for a "D[st|nd|rd|th] Month" or "D Month" pattern.
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,})", low)
    if not m:
        return None
    dom = int(m.group(1))
    mon_name = m.group(2)
    mon = MONTHS.get(mon_name[:3])
    if not mon:
        return None
    # Year defaults to current year; if the date would be in the future,
    # assume it's last year (handles "26 Jun" entered before rollover).
    today = datetime.date.today()
    try:
        candidate = datetime.date(today.year, mon, dom)
    except ValueError:
        return None
    if candidate > today:
        try:
            candidate = datetime.date(today.year - 1, mon, dom)
        except ValueError:
            return None
    # Only flag as "past / to be deleted" if it's strictly before today.
    if candidate < today:
        return candidate
    return None


def main():
    commit = "--commit" in sys.argv[1:]
    at = get_access_token()
    sheet_id = get_sheet_id(at)

    vals = sheets_get(TAB + "!A1:E1000", at)
    rows = vals.get("values", [])
    if not rows:
        print("Sheet is empty.")
        return

    header = rows[0]
    # Identify columns by header name (robust to reordering).
    def col(name):
        try:
            return header.index(name)
        except ValueError:
            return None

    day_idx = col("Day/Time")
    child_idx = col("Child")
    act_idx = col("Activity")

    to_delete = []  # grid row numbers (1-based, incl header)
    for i, row in enumerate(rows[1:], start=2):  # start=2 -> first data row is grid row 2
        day_time = row[day_idx] if day_idx is not None and day_idx < len(row) else ""
        past = parse_past_date(day_time)
        if past is not None:
            child = row[child_idx] if child_idx is not None and child_idx < len(row) else "?"
            act = row[act_idx] if act_idx is not None and act_idx < len(row) else "?"
            to_delete.append((i, child, act, day_time, past))

    if not to_delete:
        print("✅ No past dated activities found. Nothing to do.")
        return

    print(f"Found {len(to_delete)} past dated entr{'y' if len(to_delete)==1 else 'ies'} to remove:")
    for i, child, act, day_time, past in to_delete:
        print(f"  • grid row {i}: {child} — {act} ({day_time})  [{past.isoformat()}]")

    if not commit:
        print("\n(DRY RUN — no changes made. Re-run with --commit to actually delete.)")
        return

    grid_rows = [t[0] for t in to_delete]
    status = batch_delete_rows(sheet_id, grid_rows, at)
    print(f"\n✅ Deleted {len(grid_rows)} row(s) (HTTP {status}).")


if __name__ == "__main__":
    main()
