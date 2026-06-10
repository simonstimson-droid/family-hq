#!/usr/bin/env python3
"""
Smart Reminders Generator for Family HQ

Reads calendar events from Google Calendar and generates
context-aware reminders with kit/equipment needs.

Usage:
    python smart_reminders.py --days 2          # Preview next 2 days
    python smart_reminders.py --days 2 --send    # Send via Telegram
"""

import json
import sys
import argparse
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

# Add hermes tools to path for API calls
import urllib.request
import urllib.parse

# ── Configuration ──────────────────────────────────────────────
HOME = Path("/Users/simonstimson")
STATE_FILE = HOME / ".hermes" / "profiles" / "home" / "reminder_state.json"
TOKEN_FILE = HOME / ".hermes" / "profiles" / "home" / "google_token.json"
DATA_FILE = HOME / "FamilyHQ" / "data.json"

CALENDAR_ID = "family17800354474891822339@group.calendar.google.com"

# Timezone for display (UK — auto handles GMT/BST)
LOCAL_TZ = ZoneInfo("Europe/London")


def to_local(dt):
    """Convert a datetime to local timezone for display.
    Handles both offset-naive (assumed UTC) and offset-aware datetimes."""
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt  # date-only, no conversion needed
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)

# Activity → kit required mapping
KIT_REMINDERS = {
    "swim": {
        "keywords": ["swim", "swimming", "pool", "aquatic"],
        "kit": ["swimsuit", "goggles", "towel", "swim cap", "flip flops"],
        "emoji": "🏊",
    },
    "diving": {
        "keywords": ["diving", "dive"],
        "kit": ["swimsuit", "goggles", "towel"],
        "emoji": "🤿",
    },
    "gymnastics": {
        "keywords": ["gymnastics", "gym", "hbs", "revolution"],
        "kit": ["leotard", "gymnastics shorts", "hair tie", "water bottle"],
        "emoji": "🤸",
    },
    "dance": {
        "keywords": ["dance", "bx dance", "ballet"],
        "kit": ["dance shoes", "leotard", "water bottle"],
        "emoji": "💃",
    },
    "drama": {
        "keywords": ["drama", "drama kids", "acting"],
        "kit": ["water bottle", "comfortable clothes"],
        "emoji": "🎭",
    },
    "athletics": {
        "keywords": ["athletics", "track", "running"],
        "kit": ["trainers", "PE kit", "water bottle", "sun hat"],
        "emoji": "🏃",
    },
    "stretch": {
        "keywords": ["stretch", "flex", "stretch & flex", "stretch and flex"],
        "kit": ["comfortable clothes", "water bottle"],
        "emoji": "🧘",
    },
    "yoga": {
        "keywords": ["yogi", "yoga"],
        "kit": ["comfortable clothes", "water bottle"],
        "emoji": "🧘",
    },
    "choir": {
        "keywords": ["choir", "singing"],
        "kit": ["water bottle", "comfortable shoes"],
        "emoji": "🎵",
    },
    "physio": {
        "keywords": ["physio", "physiotherapy", "nhs"],
        "kit": ["shorts", "vest top", "Comfortable clothes"],
        "emoji": "🏥",
    },
    "football": {
        "keywords": ["football", "soccer", "match", "luton", "west ham"],
        "kit": ["", " football boots", "shin guards", "water bottle"],
        "emoji": "⚽",
    },
}

# Person-specific reminders
PERSON_INFO = {
    "Ava": {"colour": "💜", "school": "Fairfield Park Lower"},
    "Ella": {"colour": "💙", "school": "Pix Brook Academy"},
}

# ── Google Calendar API ────────────────────────────────────────

def load_token():
    """Load and refresh Google OAuth token."""
    with open(TOKEN_FILE) as f:
        creds = json.load(f)
    
    # Check if token is expired (simplified — always refresh to be safe)
    req_data = urllib.parse.urlencode({
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "refresh_token": creds["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    
    req = urllib.request.Request(creds["token_uri"], data=req_data)
    resp = urllib.request.urlopen(req, timeout=15)
    new_token = json.loads(resp.read())
    
    # Update stored token
    creds["token"] = new_token["access_token"]
    with open(TOKEN_FILE, "w") as f:
        json.dump(creds, f, indent=2)
    
    return creds["token"]


def fetch_calendar_events(days=7):
    """Fetch events from Google Calendar."""
    token = load_token()
    
    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days)).isoformat() + "Z"
    
    url = (
        f"https://www.googleapis.com/calendar/v3/calendars/"
        f"{urllib.parse.quote(CALENDAR_ID)}/events"
        f"?timeMin={urllib.parse.quote(time_min)}"
        f"&timeMax={urllib.parse.quote(time_max)}"
        f"&singleEvents=true"
        f"&orderBy=startTime"
    )
    
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read())
    
    events = []
    for item in data.get("items", []):
        start = item.get("start", {})
        if "dateTime" in start:
            dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
        elif "date" in start:
            dt = datetime.fromisoformat(start["date"])
        else:
            continue
        
        events.append({
            "title": item.get("summary", ""),
            "description": item.get("description", ""),
            "location": item.get("location", ""),
            "start": to_local(dt),
            "end": item.get("end", {}).get("dateTime", ""),
        })
    
    return events


def fetch_sheet_events():
    """Fetch events from the Google Sheet (fallback)."""
    try:
        with open(DATA_FILE) as f:
            data = json.load(f)
        
        sheets = data.get("sheets", [])
        for sheet in sheets:
            if sheet.get("name", "").startswith("📅"):
                rows = sheet.get("rows", [])
                events = []
                for row in rows:
                    date_val = row.get("Date", "")
                    if not date_val:
                        continue
                    try:
                        if isinstance(date_val, str):
                            dt = datetime.strptime(date_val[:10], "%Y-%m-%d")
                        else:
                            continue
                    except ValueError:
                        continue
                    events.append({
                        "title": row.get("Event", ""),
                        "description": row.get("Who", ""),
                        "location": row.get("Location", ""),
                        "start": dt,
                        "end": "",
                    })
                return events
    except Exception as e:
        print(f"Warning: Could not load sheet events: {e}")
    
    return []


def get_all_events(days=7):
    """Fetch events from both Calendar API and Sheet."""
    events = []
    
    try:
        events = fetch_calendar_events(days)
        print(f"  📅 Got {len(events)} events from Google Calendar API")
    except Exception as e:
        print(f"  ⚠️  Calendar API failed: {e}")
        print("  → Falling back to Sheet data...")
    
    if not events:
        try:
            events = fetch_sheet_events()
            print(f"  📋 Got {len(events)} events from Sheet")
        except Exception as e:
            print(f"  ⚠️  Sheet fallback failed: {e}")
    
    return events


# ── Reminder Logic ─────────────────────────────────────────────

def detect_kit_needs(event_title, event_description=""):
    """Detect what kit/equipment is needed for an event."""
    text = (event_title + " " + event_description).lower()
    
    for activity, info in KIT_REMINDERS.items():
        for keyword in info["keywords"]:
            if keyword in text:
                return info
    
    return None


def detect_person(event_title, event_description=""):
    """Detect which family member the event is for."""
    text = (event_title + " " + event_description).lower()
    
    for name in ["Ava", "Ella", "Simon", "Emma"]:
        if name.lower() in text:
            return name
    
    return None


def is_school_day(dt):
    """Check if a date is a school day (Mon-Fri, not holidays)."""
    return dt.weekday() < 5  # Mon=0 to Fri=4


def generate_reminders(events, days=2):
    """Generate smart reminders from events."""
    today = date.today()
    reminders = []
    
    for event in events:
        event_date = event["start"].date() if isinstance(event["start"], datetime) else event["start"]
        delta = (event_date - today).days
        
        if delta < 0 or delta >= days:
            continue
        
        title = event["title"]
        desc = event.get("description", "")
        location = event.get("location", "")
        person = detect_person(title, desc)
        kit = detect_kit_needs(title, desc)
        
        # Build reminder
        reminder = {
            "title": title,
            "date": event_date.isoformat(),
            "delta": delta,
            "person": person,
            "location": location,
            "kit": kit,
            "time": to_local(event["start"]).strftime("%H:%M") if isinstance(event["start"], datetime) else "All day",
        }
        
        reminders.append(reminder)
    
    return reminders


def format_reminder_message(reminders):
    """Format reminders into a nice Telegram message."""
    today = date.today()
    today_reminders = [r for r in reminders if r["delta"] == 0]
    tomorrow_reminders = [r for r in reminders if r["delta"] == 1]
    
    lines = []
    
    # Today's reminders
    if today_reminders:
        lines.append("*📅 Today's Reminders*")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        for r in today_reminders:
            time_str = r['time'] if r['time'] != 'All day' else 'All day'
            person_emoji = ''
            if r['person'] == 'Ava':
                person_emoji = '💜 '
            elif r['person'] == 'Ella':
                person_emoji = '💙 '
            lines.append('• ' + person_emoji + '*' + r['title'] + '* — ' + time_str)
            if r['location']:
                lines.append('  📍 ' + r['location'])
            if r['kit']:
                kit_items = ', '.join(r['kit']['kit'][:3])
                lines.append('  ' + r['kit']['emoji'] + ' Pack: ' + kit_items)
        lines.append('')
    
    # Tomorrow's reminders
    if tomorrow_reminders:
        lines.append("*🔔 Tomorrow's Reminders*")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        for r in tomorrow_reminders:
            time_str = r['time'] if r['time'] != 'All day' else 'All day'
            person_emoji = ''
            if r['person'] == 'Ava':
                person_emoji = '💜 '
            elif r['person'] == 'Ella':
                person_emoji = '💙 '
            lines.append('• ' + person_emoji + '*' + r['title'] + '* — ' + time_str)
            if r['location']:
                lines.append('  📍 ' + r['location'])
            if r['kit']:
                kit_items = ', '.join(r['kit']['kit'][:3])
                lines.append('  ' + r['kit']['emoji'] + ' Pack: ' + kit_items)
        lines.append('')
    
    # School morning reminder
    if is_school_day(today):
        school_kids = []
        for r in today_reminders:
            if r["person"] in ["Ava", "Ella"]:
                school_kids.append(r["person"])
        
        if not school_kids:
            # No activities today — just school
            lines.append("🏫 *School Day*")
            lines.append("Ava (Fairfield Park) 8:45am")
            lines.append("Ella (Pix Brook) 8:00am")
            lines.append("")
    
    if not lines:
        return "✅ No reminders for today or tomorrow!"
    
    header = "🏠 *Family HQ — Smart Reminders*"
    date_str = today.strftime("%A %d %B")
    return f"{header}\n{date_str}\n\n" + "\n".join(lines)


def generate_weekend_summary(events, start_date):
    """Generate a weekend summary for the coming week (Mon-Sun)."""
    return generate_period_summary(events, start_date, 7, "Weekend Summary", "📅")


def generate_week_ahead_summary(events, start_date):
    """Generate a week-ahead summary (next 14 days, grouped by week)."""
    return generate_period_summary(events, start_date, 14, "Week Ahead", "📆")


def generate_month_ahead_summary(events, start_date):
    """Generate a month-ahead summary (next 30 days, grouped by week)."""
    return generate_period_summary(events, start_date, 30, "Month Ahead", "🗓️")


def generate_period_summary(events, start_date, num_days, title, emoji):
    """Generate a period summary for the given number of days from start_date."""
    from collections import defaultdict
    
    # Group events by ISO week
    week_groups = defaultdict(list)
    week_labels = {}
    
    for event in events:
        event_date = event["start"].date() if isinstance(event["start"], datetime) else event["start"]
        if event_date < start_date:
            continue
        if (event_date - start_date).days >= num_days:
            continue
        
        # Get ISO week number
        iso_year, iso_week, _ = event_date.isocalendar()
        week_key = (iso_year, iso_week)
        
        if week_key not in week_labels:
            # Label: "Week of Mon 15 Jun"
            week_start = event_date - timedelta(days=event_date.weekday())
            week_labels[week_key] = week_start.strftime("Week of %a %d %b")
        
        week_groups[week_key].append((event_date, event))
    
    if not week_groups:
        return f"🏠 *Family HQ — {title}*\n\nNo events found for the next {num_days} days! 🎉"
    
    # Build the summary
    lines = []
    lines.append(f"*{emoji} {title} — Next {num_days} Days*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    for week_key in sorted(week_groups.keys()):
        week_events = week_groups[week_key]
        lines.append(f"\n*{week_labels[week_key]}*")
        lines.append("  ────────────────────")
        
        # Sort by date then time
        def sort_key(x):
            d = x[0]
            t = x[1]["start"]
            if isinstance(t, datetime):
                t = to_local(t)
                return (d, t.hour, t.minute)
            return (d, 0, 0)
        
        week_events.sort(key=sort_key)
        
        current_date = None
        for event_date, event in week_events:
            # Print date header if new day
            if event_date != current_date:
                current_date = event_date
                day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][event_date.weekday()]
                lines.append(f"\n  *{day_name} {event_date.strftime('%d %b')}*")
            
            time_str = to_local(event["start"]).strftime("%H:%M") if isinstance(event["start"], datetime) else "All day"
            title_text = event["title"][:35] + ("..." if len(event["title"]) > 35 else "")
            person = detect_person(event["title"], event.get("description", ""))
            kit = detect_kit_needs(event["title"], event.get("description", ""))
            
            person_emoji = ""
            if person == "Ava":
                person_emoji = "💜 "
            elif person == "Ella":
                person_emoji = "💙 "
            elif person == "Simon":
                person_emoji = "👨 "
            elif person == "Emma":
                person_emoji = "👩 "
            
            lines.append(f"    • {person_emoji}{time_str} — {title_text}")
            
            if event.get("location") and len(event["location"]) < 25:
                lines.append(f"      📍 {event['location']}")
            
            if kit:
                kit_items = ", ".join(kit["kit"][:2])
                if len(kit["kit"]) > 2:
                    kit_items += f" +{len(kit['kit'])-2} more"
                lines.append(f"      {kit['emoji']} {kit_items}")
    
    lines.append("")
    lines.append("💡 *Tip:* Check daily reminders at 7am for kit details and last-minute changes!")
    
    header = f"🏠 *Family HQ — {title}*"
    end_date = start_date + timedelta(days=num_days - 1)
    date_range = f"{start_date.strftime('%d %b')} — {end_date.strftime('%d %b %Y')}"
    return f"{header}\n{date_range}\n\n" + "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Family HQ Smart Reminders")
    parser.add_argument("--days", type=int, default=2, help="Number of days to look ahead")
    parser.add_argument("--send", action="store_true", help="Send via Telegram")
    parser.add_argument("--preview", action="store_true", help="Preview only (don't save)")
    parser.add_argument("--weekend", action="store_true", help="Weekend summary for coming week (Mon-Sun)")
    parser.add_argument("--week-ahead", action="store_true", help="Week-ahead summary (next 14 days)")
    parser.add_argument("--month-ahead", action="store_true", help="Month-ahead summary (next 30 days)")
    args = parser.parse_args()
    
    print(f"🔍 Fetching events...")
    if args.weekend or args.week_ahead or args.month_ahead:
        # For summary modes, fetch from upcoming Monday
        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7
        if days_until_monday == 0:
            start_date = today
        else:
            start_date = today + timedelta(days=days_until_monday)
        
        # Determine how many days to fetch
        if args.month_ahead:
            fetch_days = 30
        elif args.week_ahead:
            fetch_days = 14
        else:
            fetch_days = 7
        
        events = get_all_events(fetch_days)
        filtered_events = []
        for e in events:
            event_date = e["start"].date() if isinstance(e["start"], datetime) else e["start"]
            if event_date >= start_date:
                filtered_events.append(e)
        events = filtered_events
        print(f"  📅 Got {len(events)} events for period starting {start_date}")
    else:
        events = get_all_events(args.days)
        start_date = None
    
    if not events:
        print("No events found!")
        return
    
    print(f"🧠 Generating summary...")
    if args.weekend:
        message = generate_weekend_summary(events, start_date)
    elif args.week_ahead:
        message = generate_week_ahead_summary(events, start_date)
    elif args.month_ahead:
        message = generate_month_ahead_summary(events, start_date)
    else:
        reminders = generate_reminders(events, args.days)
        message = format_reminder_message(reminders)
    
    print("\n" + "=" * 50)
    print(message)
    print("=" * 50)
    
    if args.send:
        # Save to file for the cron job to pick up
        if args.weekend or args.week_ahead or args.month_ahead:
            reminder_count = len(events)
        else:
            reminder_count = len(reminders)
        output = {
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "reminder_count": reminder_count,
        }
        output_file = HOME / ".hermes" / "profiles" / "home" / "pending_reminder.json"
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\n💾 Reminder saved to {output_file}")
        print("The cron job will pick this up and send it via Telegram.")
    
    return message


if __name__ == "__main__":
    main()
