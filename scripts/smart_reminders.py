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
from datetime import datetime, timedelta, date
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
            "start": dt,
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
            "time": event["start"].strftime("%H:%M") if isinstance(event["start"], datetime) else "All day",
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
    # Group events by day
    days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    # Create a dict for each day
    day_events = {day: [] for day in days_of_week}
    
    for event in events:
        event_date = event["start"].date() if isinstance(event["start"], datetime) else event["start"]
        day_name = days_of_week[event_date.weekday()]
        if day_name in day_events:
            day_events[day_name].append(event)
    
    # Build the summary
    lines = []
    lines.append("*📅 Weekend Summary — Week Ahead*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # Start from the upcoming Monday
    today = date.today()
    days_until_monday = (0 - today.weekday()) % 7
    if days_until_monday == 0:
        start_date = today
    else:
        start_date = today + timedelta(days=days_until_monday)
    
    for i in range(7):
        current_date = start_date + timedelta(days=i)
        day_name = days_of_week[current_date.weekday()]
        date_str = current_date.strftime("%a %d %b")
        
        day_list = day_events[day_name]
        if not day_list:
            continue
            
        lines.append(f"\n*{day_name} {date_str}*")
        lines.append("  ────────────────────")
        
        # Sort events by time
        day_list.sort(key=lambda e: e["start"] if isinstance(e["start"], datetime) else 
                     datetime.combine(e["start"], datetime.min.time()))
        
        for event in day_list:
            time_str = event["start"].strftime("%H:%M") if isinstance(event["start"], datetime) else "All day"
            title = event["title"][:30] + ("..." if len(event["title"]) > 30 else "")
            person = detect_person(event["title"], event.get("description", ""))
            kit = detect_kit_needs(event["title"], event.get("description", ""))
            
            # Person emoji
            person_emoji = ""
            if person == "Ava":
                person_emoji = "💜 "
            elif person == "Ella":
                person_emoji = "💙 "
            elif person == "Simon":
                person_emoji = "👨 "
            elif person == "Emma":
                person_emoji = "👩 "
            
            lines.append(f"  • {person_emoji}{time_str} — {title}")
            
            # Add location if short
            if event.get("location") and len(event["location"]) < 20:
                lines.append(f"    📍 {event['location']}")
            
            # Add kit if any
            if kit:
                kit_items = ", ".join(kit["kit"][:2])  # Just first 2 items for brevity
                if len(kit["kit"]) > 2:
                    kit_items += f" +{len(kit['kit'])-2} more"
                lines.append(f"    {kit['emoji']} {kit_items}")
    
    # Add a note about checking tonight
    lines.append("")
    lines.append("💡 *Tip:* Check tomorrow's reminders at 7am for any last-minute changes!")
    
    header = "🏠 *Family HQ — Weekend Summary*"
    date_range = f"{start_date.strftime('%d %b')} — {(start_date + timedelta(days=6)).strftime('%d %b %Y')}"
    return f"{header}\n{date_range}\n\n" + "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Family HQ Smart Reminders")
    parser.add_argument("--days", type=int, default=2, help="Number of days to look ahead")
    parser.add_argument("--send", action="store_true", help="Send via Telegram")
    parser.add_argument("--preview", action="store_true", help="Preview only (don't save)")
    parser.add_argument("--weekend", action="store_true", help="Weekend summary for coming week (Mon-Sun)")
    args = parser.parse_args()
    
    print(f"🔍 Fetching events...")
    if args.weekend:
        # For weekend summary, get next 7 days starting from upcoming Monday
        today = date.today()
        days_until_monday = (0 - today.weekday()) % 7  # Monday is 0
        if days_until_monday == 0:  # Today is Monday
            start_date = today
        else:
            start_date = today + timedelta(days=days_until_monday)
        # Get 7 days from Monday
        events = get_all_events(7)
        # Filter to only events from start_date onwards
        filtered_events = []
        for e in events:
            event_date = e["start"].date() if isinstance(e["start"], datetime) else e["start"]
            if event_date >= start_date:
                filtered_events.append(e)
        events = filtered_events
        print(f"  📅 Got {len(events)} events for week starting {start_date}")
    else:
        events = get_all_events(args.days)
    
    if not events:
        print("No events found!")
        return
    
    print(f"🧠 Generating {'weekend summary' if args.weekend else 'smart reminders'}...")
    if args.weekend:
        message = generate_weekend_summary(events, start_date)
    else:
        reminders = generate_reminders(events, args.days)
        message = format_reminder_message(reminders)
    
    print("\n" + "=" * 50)
    print(message)
    print("=" * 50)
    
    if args.send:
        # Save to file for the cron job to pick up
        if args.weekend:
            # For weekend summary, count total events
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
