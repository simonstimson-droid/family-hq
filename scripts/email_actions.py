#!/usr/bin/env python3
"""
Family HQ Email Action Helpers
Called by the agent to take action on interpreted emails.

Usage:
  python3 email_actions.py calendar "Title" "2026-06-25" "09:00" "10:00" "Location" "Notes"
  python3 email_actions.py sheet "SheetName" "col1" "col2" "col3" ...
  python3 email_actions.py label "msg_id"
  python3 email_actions.py reminder "Title" "2026-06-25T09:00:00" "Description"
"""

import json
import sys
import urllib.request
import urllib.parse
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path

TOKEN_PATH = Path("/Users/simonstimson/.hermes/profiles/home/google_token.json")
SHEET_ID = "1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA"
FAMILY_CALENDAR_ID = "family17800354474891822339@group.calendar.google.com"
PROCESSED_LABEL = "FamilyHQ_Processed"


def get_access_token():
    with open(TOKEN_PATH) as f:
        tok = json.load(f)
    expiry_str = tok.get("expiry", "")
    if expiry_str:
        try:
            exp_dt = datetime.fromisoformat(expiry_str)
            now = datetime.now(timezone.utc)
            if exp_dt <= now:
                params = {
                    "client_id": tok["client_id"],
                    "client_secret": tok["client_secret"],
                    "refresh_token": tok["refresh_token"],
                    "grant_type": "refresh_token",
                }
                data = urllib.parse.urlencode(params).encode()
                req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                tok["access_token"] = result["access_token"]
                tok["token"] = result["access_token"]
                tok["expires_in"] = result.get("expires_in", 3599)
                tok["expiry"] = (now + timedelta(seconds=tok["expires_in"])).isoformat()
                with open(TOKEN_PATH, "w") as f:
                    json.dump(tok, f, indent=2)
        except Exception as e:
            print(f"Token refresh failed: {e}", file=sys.stderr)
    return tok.get("access_token") or tok.get("token")


def api_request(method, url, data=None, token=None):
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def add_calendar_event(title, date, start_time, end_time, location, notes, token):
    """Add an event to the Family Google Calendar."""
    # Build the event time
    if start_time:
        start_dt = f"{date}T{start_time}:00"
        if end_time:
            end_dt = f"{date}T{end_time}:00"
        else:
            # Default 1 hour duration
            from datetime import datetime as dt, timedelta as td
            start_parsed = dt.fromisoformat(start_dt)
            end_parsed = start_parsed + td(hours=1)
            end_dt = end_parsed.strftime("%Y-%m-%dT%H:%M:%S")
        
        event = {
            "summary": title,
            "start": {"dateTime": start_dt, "timeZone": "Europe/London"},
            "end": {"dateTime": end_dt, "timeZone": "Europe/London"},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 24 * 60},
                    {"method": "popup", "minutes": 60},
                ],
            },
        }
    else:
        # All-day event
        event = {
            "summary": title,
            "start": {"date": date},
            "end": {"date": date},
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "email", "minutes": 24 * 60}],
            },
        }
    
    if location:
        event["location"] = location
    if notes:
        event["description"] = notes

    url = f"https://www.googleapis.com/calendar/v3/calendars/{FAMILY_CALENDAR_ID}/events"
    result = api_request("POST", url, event, token)
    if "error" in result:
        print(f"❌ Calendar error: {result['error']}")
        return False
    print(f"✅ Calendar event created: {title} on {date}" + (f" at {start_time}" if start_time else " (all day)"))
    return True


def append_sheet_row(sheet_name, values, token):
    """Append a row to a Google Sheet."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{sheet_name}!A1:append"
    data = {
        "values": [values],
        "majorDimension": "ROWS",
        "valueInputOption": "USER_ENTERED",
    }
    result = api_request("POST", url, data, token)
    if "error" in result:
        print(f"❌ Sheet error: {result['error']}")
        return False
    print(f"✅ Added to {sheet_name}: {values[0] if values else '(empty)'}")
    return True


def get_label_id(token):
    """Get the FamilyHQ_Processed label ID."""
    url = "https://gmail.googleapis.com/gmail/v1/users/me/labels"
    result = api_request("GET", url, token=token)
    if "error" in result:
        return None
    for label in result.get("labels", []):
        if label["name"] == PROCESSED_LABEL:
            return label["id"]
    # Create it
    data = {"name": PROCESSED_LABEL, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    result = api_request("POST", url, data, token)
    return result.get("id")


def label_email(msg_id, token):
    """Mark an email as processed."""
    label_id = get_label_id(token)
    if not label_id:
        print("❌ Could not get processed label")
        return False
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}/modify"
    data = {"addLabelIds": [label_id], "removeLabelIds": ["UNREAD"]}
    result = api_request("POST", url, data, token)
    if "error" in result:
        print(f"❌ Label error: {result['error']}")
        return False
    print(f"✅ Email {msg_id[:8]}... marked as processed")
    return True


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]
    token = get_access_token()

    if action == "calendar":
        # calendar "Title" "YYYY-MM-DD" "HH:MM" "HH:MM" "Location" "Notes"
        title = sys.argv[2] if len(sys.argv) > 2 else "New Event"
        date = sys.argv[3] if len(sys.argv) > 3 else datetime.now().strftime("%Y-%m-%d")
        start = sys.argv[4] if len(sys.argv) > 4 else ""
        end = sys.argv[5] if len(sys.argv) > 5 else ""
        loc = sys.argv[6] if len(sys.argv) > 6 else ""
        notes = sys.argv[7] if len(sys.argv) > 7 else ""
        add_calendar_event(title, date, start, end, loc, notes, token)

    elif action == "sheet":
        # sheet "SheetName" "col1" "col2" ...
        sheet_name = sys.argv[2] if len(sys.argv) > 2 else "📝 Announcements"
        values = sys.argv[3:] if len(sys.argv) > 3 else [""]
        append_sheet_row(sheet_name, values, token)

    elif action == "label":
        # label "msg_id"
        msg_id = sys.argv[2] if len(sys.argv) > 2 else ""
        if msg_id:
            label_email(msg_id, token)
        else:
            print("❌ No message ID provided")

    else:
        print(f"Unknown action: {action}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
