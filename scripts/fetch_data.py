#!/usr/bin/env python3
"""
Fetch all data from Family HQ Google Sheet and Google Calendar, merge, and output as JSON.
Works both locally and in GitHub Actions.

Environment variables:
    GOOGLE_TOKEN_JSON - Google OAuth token JSON string (GitHub Actions secret)
    Or reads from ~/.hermes/profiles/home/google_token.json (local)
"""
import json, os, sys, tempfile, re, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

SPREADSHEET_ID = "1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA"
CALENDAR_ID = "family17800354474891822339@group.calendar.google.com"
CALENDAR_LOOKAHEAD_DAYS = 120  # how far ahead to fetch calendar events

# ── Token handling ──────────────────────────────────────────────────────────

token_json = os.environ.get("GOOGLE_TOKEN_JSON")
if token_json:
    token_file = os.path.join(tempfile.gettempdir(), "google_token.json")
    with open(token_file, "w") as f:
        f.write(token_json)
elif os.path.exists("/Users/simonstimson/.hermes/profiles/home/google_token.json"):
    token_file = "/Users/simonstimson/.hermes/profiles/home/google_token.json"
else:
    print("ERROR: No Google token found", file=sys.stderr)
    sys.exit(1)

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file(token_file)
service = build("sheets", "v4", credentials=creds)

# ── Fetch spreadsheet sheets ────────────────────────────────────────────────

SHEETS = [
    "📅 Calendar",
    "🛒 Shopping List",
    "✅ Chores",
    "🍽️ Meal Plan",
    "📋 School & Activities",
    "💰 Budget",
    "📝 Announcements",
    "📌 To-Do",
    "👨‍👩‍👧‍👧 Family Members",
    "📞 Important Contacts",
]

output = {}

for name in SHEETS:
    safe_name = "'" + name + "'"
    try:
        data = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{safe_name}!A1:Z100"
        ).execute()
        values = data.get("values", [])
        if values and len(values) > 1:
            headers = values[0]
            rows = []
            for row_idx, row in enumerate(values[1:], start=2):
                row_dict = {"_row": row_idx}
                for i, h in enumerate(headers):
                    row_dict[h] = row[i] if i < len(row) else ""
                # Skip completely empty rows (all fields blank)
                non_empty = [v for k, v in row_dict.items() if k != "_row" and str(v).strip() != ""]
                if not non_empty:
                    continue
                rows.append(row_dict)
            output[name] = {"headers": headers, "rows": rows}
        elif values:
            output[name] = {"headers": [], "rows": values}
        else:
            output[name] = {"headers": [], "rows": []}
    except Exception as e:
        output[name] = {"error": str(e)}

# ── Fetch Google Calendar events ────────────────────────────────────────────

def get_access_token():
    """Get a fresh access token for Calendar API calls."""
    with open(token_file) as f:
        tok = json.load(f)
    # Check expiry
    expiry_str = tok.get("expiry", "")
    if expiry_str:
        try:
            expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if now >= expiry:
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
        except Exception:
            pass
    return tok["access_token"]


def fetch_calendar_events(token):
    """Fetch events from Google Calendar."""
    now = datetime.now(timezone.utc)
    time_min = urllib.parse.quote(now.isoformat())
    time_max = urllib.parse.quote((now + timedelta(days=CALENDAR_LOOKAHEAD_DAYS)).isoformat())
    cal_id = urllib.parse.quote(CALENDAR_ID)

    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events"
        f"?timeMin={time_min}&timeMax={time_max}"
        f"&singleEvents=true&orderBy=startTime"
    )
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    events = data.get("items", [])
    result = []
    for e in events:
        start = e.get("start", {})
        end = e.get("end", {})

        if "dateTime" in start:
            start_dt = datetime.fromisoformat(start["dateTime"])
            end_dt = datetime.fromisoformat(end["dateTime"])
            # Convert UTC to local time
            if start_dt.tzinfo is not None:
                start_dt = start_dt.astimezone()
                end_dt = end_dt.astimezone()
            is_all_day = False
        else:
            start_dt = datetime.fromisoformat(start["date"])
            end_dt = datetime.fromisoformat(end["date"])
            is_all_day = True

        result.append({
            "Date": start_dt.strftime("%Y-%m-%d"),
            "Time": "All day" if is_all_day else f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}",
            "Event": e.get("summary", ""),
            "Who": extract_who(e.get("description", "")),
            "Location": e.get("location", ""),
            "Notes": "",
            "_source": "calendar",
            "_cal_id": e.get("id", ""),
        })
    return result


def extract_who(desc):
    """Try to extract 'Who' from event description."""
    if not desc:
        return ""
    for line in desc.split("\n"):
        line = line.strip()
        lower = line.lower()
        if lower.startswith("who:") or lower.startswith("for:"):
            return line.split(":", 1)[1].strip()
    return ""


def normalize_name(s):
    """Normalize event name for comparison."""
    s = re.sub(r"[^\x00-\x7F]+", "", s)  # strip emoji
    s = re.sub(r"\(.*?\)", "", s)  # strip parentheticals
    s = re.sub(r"-\s*(ava|ella|ava & ella|both)\s*$", "", s, flags=re.IGNORECASE)
    s = " ".join(s.split())
    return s.lower().strip()


def times_overlap(cal_time, sheet_time):
    """Check if two time strings overlap (same start time)."""
    if not cal_time and not sheet_time:
        return True
    if not cal_time or not sheet_time:
        return False
    # Handle "All day"
    if cal_time == "All day" and sheet_time == "All day":
        return True
    if cal_time == "All day" or sheet_time == "All day":
        return False
    cal_start = cal_time.split("-")[0].strip()
    sheet_start = sheet_time.split("-")[0].strip()
    return cal_start == sheet_start


def merge_calendar_events(sheet_rows, cal_events):
    """
    Merge calendar events with spreadsheet rows.
    
    Strategy:
    - Events in both (matched by date + time + name similarity) → keep spreadsheet version
      (spreadsheet may have manual annotations)
    - Events only in Calendar → add to merged list
    - Events only in Sheet → keep (may be manual entries not in calendar)
    
    Returns merged list of event dicts.
    """
    SIMILARITY_THRESHOLD = 0.60
    matched_cal = set()
    matched_sheet = set()

    # Match calendar events to sheet rows
    for ci, cal in enumerate(cal_events):
        best_match = None
        best_sim = 0
        for si, row in enumerate(sheet_rows):
            if cal["Date"] != row.get("Date", ""):
                continue
            if not times_overlap(cal["Time"], row.get("Time", "")):
                continue
            sim = SequenceMatcher(
                None, normalize_name(cal["Event"]), normalize_name(row.get("Event", ""))
            ).ratio()
            if sim > best_sim:
                best_sim = sim
                best_match = si
        if best_match is not None and best_sim >= SIMILARITY_THRESHOLD:
            matched_cal.add(ci)
            matched_sheet.add(best_match)

    # Build merged list
    merged = []

    # Add all sheet rows (spreadsheet is the base)
    for si, row in enumerate(sheet_rows):
        merged.append(row)

    # Add calendar events that weren't matched
    for ci, cal in enumerate(cal_events):
        if ci not in matched_cal:
            merged.append(cal)

    # Sort by date, then by time
    def sort_key(e):
        date = e.get("Date", "9999-99-99")
        time_str = e.get("Time", "")
        if time_str == "All day":
            time = "00:00"
        elif time_str:
            time = time_str.split("-")[0].strip()
        else:
            time = "00:00"
        return f"{date} {time}"

    merged.sort(key=sort_key)
    return merged


# Fetch and merge
try:
    token = get_access_token()
    cal_events = fetch_calendar_events(token)
    sheet_calendar = output.get("📅 Calendar", {}).get("rows", [])
    merged = merge_calendar_events(sheet_calendar, cal_events)
    output["📅 Calendar"] = {
        "headers": ["Date", "Time", "Event", "Who", "Location", "Notes"],
        "rows": merged,
    }
except Exception as e:
    print(f"WARNING: Calendar merge failed: {e}", file=sys.stderr)

# Output
print(json.dumps(output, ensure_ascii=False, indent=2))
