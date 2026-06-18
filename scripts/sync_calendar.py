#!/usr/bin/env python3
"""
sync_calendar.py — Sync events between Google Calendar and the Family HQ spreadsheet.

Logic:
1. Fetch events from Google Calendar (next N days)
2. Fetch events from the spreadsheet Calendar sheet
3. Match events by: same date + same start time + similar name
4. Report:
   - Events in Calendar but NOT in spreadsheet (candidates to add)
   - Events in spreadsheet but NOT in Calendar (candidates to remove)
   - Events in both with different names (duplicates / naming mismatches)
5. Optionally write new events to the spreadsheet

Usage:
    python3 sync_calendar.py              # dry run (report only)
    python3 sync_calendar.py --write      # write new events to spreadsheet
    python3 sync_calendar.py --days 60    # look ahead 60 days (default 90)
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

# ── Config ──────────────────────────────────────────────────────────────────

SPREADSHEET_ID = "1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA"
CALENDAR_ID = "family17800354474891822339@group.calendar.google.com"
DEFAULT_DAYS = 90
SIMILARITY_THRESHOLD = 0.60  # name similarity threshold (0-1) after normalization

# ── Helpers ─────────────────────────────────────────────────────────────────

def get_token():
    """Load and return the Google OAuth token."""
    token_file = "/Users/simonstimson/.hermes/profiles/home/google_token.json"
    with open(token_file) as f:
        tok = json.load(f)
    return tok["access_token"]


def refresh_token_if_needed(token):
    """Check token expiry and refresh if needed. Returns fresh token."""
    token_file = "/Users/simonstimson/.hermes/profiles/home/google_token.json"
    with open(token_file) as f:
        tok = json.load(f)
    
    expiry_str = tok.get("expiry", "")
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if now >= expiry:
                print("  ⚠️ Token expired, refreshing...")
                params = {
                    "client_id": tok["client_id"],
                    "client_secret": tok["client_secret"],
                    "refresh_token": tok["refresh_token"],
                    "grant_type": "refresh_token",
                }
                data = urllib.parse.urlencode(params).encode()
                req = urllib.request.Request(
                    "https://oauth2.googleapis.com/token", data=data, method="POST"
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                tok["access_token"] = result["access_token"]
                tok["token"] = result["access_token"]
                tok["expires_in"] = result.get("expires_in", 3599)
                tok["expiry"] = (
                    datetime.now(timezone.utc) + timedelta(seconds=tok["expires_in"])
                ).isoformat()
                with open(token_file, "w") as f:
                    json.dump(tok, f, indent=2)
                return tok["access_token"]
        except Exception as e:
            print(f"  ⚠️ Token check failed: {e}")
    
    return token


def api_get(url, token):
    """Simple GET request to Google API."""
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def api_post(url, token, payload):
    """Simple POST request to Google API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def api_put(url, token, payload):
    """Simple PUT request to Google API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ── Fetch Google Calendar events ────────────────────────────────────────────

def fetch_calendar_events(token, days_ahead=DEFAULT_DAYS):
    """Fetch events from Google Calendar for the next N days."""
    now = datetime.now(timezone.utc)
    time_min = urllib.parse.quote(now.isoformat())
    time_max = urllib.parse.quote((now + timedelta(days=days_ahead)).isoformat())
    cal_id = urllib.parse.quote(CALENDAR_ID)

    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
        f"?timeMin={time_min}&timeMax={time_max}"
        f"&singleEvents=true&orderBy=startTime"
    )

    data = api_get(url, token)
    events = data.get("items", [])

    result = []
    for e in events:
        start = e.get("start", {})
        end = e.get("end", {})

        # Handle all-day events (date) vs timed events (dateTime)
        if "dateTime" in start:
            start_dt = datetime.fromisoformat(start["dateTime"])
            end_dt = datetime.fromisoformat(end["dateTime"])
            # Convert UTC to local time for comparison with spreadsheet
            if start_dt.tzinfo is not None:
                start_dt = start_dt.astimezone()
                end_dt = end_dt.astimezone()
            is_all_day = False
        else:
            start_dt = datetime.fromisoformat(start["date"])
            end_dt = datetime.fromisoformat(end["date"])
            is_all_day = True

        result.append({
            "summary": e.get("summary", ""),
            "start_date": start_dt.strftime("%Y-%m-%d"),
            "start_time": "" if is_all_day else start_dt.strftime("%H:%M"),
            "end_time": "" if is_all_day else end_dt.strftime("%H:%M"),
            "is_all_day": is_all_day,
            "location": e.get("location", ""),
            "description": e.get("description", ""),
            "who": extract_who_from_description(e.get("description", "")),
            "event_id": e.get("id", ""),
            "html_link": e.get("htmlLink", ""),
        })

    return result


def extract_who_from_description(desc):
    """Try to extract 'Who' from the event description."""
    if not desc:
        return ""
    # Common patterns: "Who: Ava", "For: Ella", "Ava & Ella"
    for line in desc.split("\n"):
        line = line.strip()
        lower = line.lower()
        if lower.startswith("who:") or lower.startswith("for:"):
            return line.split(":", 1)[1].strip()
    return ""


# ── Fetch spreadsheet Calendar sheet ────────────────────────────────────────

def fetch_spreadsheet_calendar(token):
    """Fetch the 📅 Calendar sheet from the spreadsheet."""
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
        f"/values/%F0%9F%93%85%20Calendar!A1:Z200"
    )
    data = api_get(url, token)
    values = data.get("values", [])

    if not values or len(values) < 2:
        return []

    headers = values[0]
    rows = []
    for row in values[1:]:
        row_dict = {}
        for i, h in enumerate(headers):
            row_dict[h] = row[i] if i < len(row) else ""
        # Skip completely empty rows
        non_empty = [v for v in row_dict.values() if str(v).strip()]
        if non_empty:
            rows.append(row_dict)

    return rows


# ── Matching / dedup logic ──────────────────────────────────────────────────

def normalize_name(name):
    """Strip emojis, parentheticals, who suffixes, and lowercase for comparison."""
    import re
    # Remove emojis
    name = re.sub(r"[^\x00-\x7F]+", "", name)
    # Remove parentheticals like (BX Dance), (Fox Class, DB)
    name = re.sub(r"\(.*?\)", "", name)
    # Remove who suffixes like " - Ava & Ella", " - Ava", " - Ella", " - Both"
    name = re.sub(r"-\s*(ava|ella|ava & ella|both)\s*$", "", name, flags=re.IGNORECASE)
    # Remove @location patterns
    name = re.sub(r"@\s*\S+", "", name)
    # Remove extra whitespace
    name = " ".join(name.split())
    return name.lower().strip()


def name_similarity(a, b):
    """Return similarity ratio between two event names (0-1)."""
    a_norm = normalize_name(a)
    b_norm = normalize_name(b)
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def times_match(cal_time, sheet_time):
    """Check if two time strings represent the same start time."""
    if not cal_time and not sheet_time:
        return True  # both all-day
    if not cal_time or not sheet_time:
        return False  # one is all-day, one isn't
    # Normalize: "17:00" == "17:00-17:45" (compare start times)
    cal_start = cal_time.split("-")[0].strip()
    sheet_start = sheet_time.split("-")[0].strip()
    return cal_start == sheet_start


def find_matches(cal_events, sheet_rows):
    """
    Match calendar events to spreadsheet rows.
    
    Returns:
        matched: list of (cal_event, sheet_row, similarity) tuples
        cal_only: list of calendar events with no match
        sheet_only: list of spreadsheet rows with no match
    """
    matched = []
    cal_matched = set()
    sheet_matched = set()

    # First pass: exact date + time match with name similarity
    for ci, cal in enumerate(cal_events):
        best_match = None
        best_sim = 0

        for si, row in enumerate(sheet_rows):
            sheet_date = row.get("Date", "")
            sheet_time = row.get("Time", "")
            sheet_event = row.get("Event", "")

            # Must match on date
            if cal["start_date"] != sheet_date:
                continue

            # Must match on start time (or both all-day)
            cal_time = cal["start_time"]
            if not times_match(cal_time, sheet_time):
                continue

            # Check name similarity
            sim = name_similarity(cal["summary"], sheet_event)
            if sim > best_sim:
                best_sim = sim
                best_match = si

        if best_match is not None and best_sim >= SIMILARITY_THRESHOLD:
            matched.append((cal, sheet_rows[best_match], best_sim))
            cal_matched.add(ci)
            sheet_matched.add(best_match)

    # Unmatched
    cal_only = [cal_events[i] for i in range(len(cal_events)) if i not in cal_matched]
    sheet_only = [sheet_rows[i] for i in range(len(sheet_rows)) if i not in sheet_matched]

    return matched, cal_only, sheet_only


# ── Write to spreadsheet ────────────────────────────────────────────────────

def add_event_to_spreadsheet(token, event):
    """Append a new event row to the Calendar sheet."""
    # Build the row: Date, Time, Event, Who, Location, Notes
    date = event["start_date"]
    if event["is_all_day"]:
        time_str = "All day"
    elif event["start_time"] and event["end_time"]:
        time_str = f"{event['start_time']}-{event['end_time']}"
    else:
        time_str = event["start_time"]

    row_values = [
        date,
        time_str,
        event["summary"],
        event.get("who", ""),
        event.get("location", ""),
        "",  # Notes
    ]

    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
        f"/values/%F0%9F%93%85%20Calendar!A:F"
        f"?valueInputOption=USER_ENTERED"
    )
    payload = {"values": [row_values]}
    api_post(url, token, payload)
    return True


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    write_mode = "--write" in sys.argv
    days = DEFAULT_DAYS
    for i, arg in enumerate(sys.argv):
        if arg == "--days" and i + 1 < len(sys.argv):
            days = int(sys.argv[i + 1])

    print(f"{'='*60}")
    print(f"  Family HQ Calendar Sync")
    print(f"  Mode: {'WRITE' if write_mode else 'DRY RUN'}")
    print(f"  Lookahead: {days} days")
    print(f"{'='*60}\n")

    # Get token
    token = get_token()
    token = refresh_token_if_needed(token)

    # Fetch both sources
    print("📡 Fetching Google Calendar events...")
    cal_events = fetch_calendar_events(token, days)
    print(f"   Found {len(cal_events)} events\n")

    print("📊 Fetching spreadsheet Calendar sheet...")
    sheet_rows = fetch_spreadsheet_calendar(token)
    print(f"   Found {len(sheet_rows)} rows\n")

    # Match
    print("🔍 Matching events...")
    matched, cal_only, sheet_only = find_matches(cal_events, sheet_rows)

    # Report matched (with name differences)
    print(f"\n{'─'*60}")
    print(f"  MATCHED: {len(matched)} events found in both sources")
    print(f"{'─'*60}")
    name_mismatches = []
    for cal, row, sim in matched:
        cal_name = cal["summary"]
        sheet_name = row.get("Event", "")
        if normalize_name(cal_name) != normalize_name(sheet_name):
            name_mismatches.append((cal, row, sim))
            print(f"  📝 Name mismatch (sim={sim:.0%}):")
            print(f"     Calendar: \"{cal_name}\"")
            print(f"     Sheet:    \"{sheet_name}\"")
            print(f"     When:     {cal['start_date']} {cal.get('start_time','all-day')}")
            print()

    if not name_mismatches:
        print("  ✅ All matched events have consistent names\n")

    # Report calendar-only events
    print(f"{'─'*60}")
    print(f"  IN CALENDAR ONLY (not in spreadsheet): {len(cal_only)} events")
    print(f"{'─'*60}")
    for cal in cal_only:
        time_str = cal["start_time"] if not cal["is_all_day"] else "All day"
        print(f"  ➕ {cal['start_date']} | {time_str} | {cal['summary']}")
        if cal.get("location"):
            print(f"              📍 {cal['location']}")
    print()

    # Report sheet-only events
    print(f"{'─'*60}")
    print(f"  IN SPREADSHEET ONLY (not in Calendar): {len(sheet_only)} events")
    print(f"{'─'*60}")
    for row in sheet_rows:
        if row in sheet_only:
            print(f"  ➖ {row.get('Date','')} | {row.get('Time','')} | {row.get('Event','')}")
    print()

    # Write mode: add calendar-only events to spreadsheet
    if write_mode and cal_only:
        print(f"{'─'*60}")
        print(f"  WRITING {len(cal_only)} new events to spreadsheet...")
        print(f"{'─'*60}")
        for cal in cal_only:
            try:
                add_event_to_spreadsheet(token, cal)
                print(f"  ✅ Added: {cal['start_date']} | {cal['summary']}")
            except Exception as e:
                print(f"  ❌ Failed: {cal['summary']} — {e}")
        print()
        print("  Done! Run fetch_data.py to regenerate data.json")
    elif write_mode:
        print("  No new events to write.")

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Matched:      {len(matched)}")
    print(f"  Name mismatches: {len(name_mismatches)}")
    print(f"  Calendar-only:   {len(cal_only)} (need adding)")
    print(f"  Sheet-only:      {len(sheet_only)} (may be stale)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
