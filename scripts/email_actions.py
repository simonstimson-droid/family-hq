#!/usr/bin/env python3
"""
Helper script for processing emails
Provides basic functionality: label emails, add to calendar, add to sheets, set reminders
"""

import json
import sys
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 email_actions.py label <msg_id>")
        print("  python3 email_actions.py calendar <title> --date <YYYY-MM-DD> [--time <HH:MM>] [--end <HH:MM>] [--location <loc>] [--notes <notes>]")
        print("  python3 email_actions.py sheet <sheet_name> <col1> <col2> ...")
        print("  python3 email_actions.py reminder <msg_id> <cron> <action>")
        return

    action = sys.argv[1]
    
    if action == "label":
        # Mark email as processed
        if len(sys.argv) >= 3:
            msg_id = sys.argv[2]
            # Create a processed marker file
            marker_path = Path(f"/Users/simonstimson/FamilyHQ/processed_{msg_id[:8]}.json")
            with open(marker_path, "w") as f:
                json.dump({
                    "msg_id": msg_id,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "status": "processed"
                }, f, indent=2)
            print(f"✓ Email {msg_id} marked as processed")
        else:
            print("Error: Need msg_id for label action")
            
    elif action == "calendar":
        # Parse calendar arguments
        title = "Unknown Event"
        date = None
        time = None
        end_time = None
        location = ""
        notes = ""
        
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--date" and i + 1 < len(sys.argv):
                date = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--time" and i + 1 < len(sys.argv):
                time = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--end" and i + 1 < len(sys.argv):
                end_time = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--location" and i + 1 < len(sys.argv):
                location = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--notes" and i + 1 < len(sys.argv):
                notes = sys.argv[i + 1]
                i += 2
            else:
                if title == "Unknown Event" and not sys.argv[i].startswith("--"):
                    title = sys.argv[i]
                i += 1
        
        # Build event details
        event_time = f"{date} {time}" if time else date
        event_details = {
            "title": title,
            "date": date,
            "time": time,
            "end_time": end_time,
            "location": location,
            "notes": notes,
            "calendar_id": "family17800354474891822339@group.calendar.google.com"
        }
        
        # Save to calendar file
        calendar_path = Path("/Users/simonstimson/FamilyHQ/calendar_events.json")
        try:
            existing = json.loads(calendar_path.read_text()) if calendar_path.exists() else []
            existing.append(event_details)
            calendar_path.write_text(json.dumps(existing, indent=2))
            print(f"✓ Added '{title}' to calendar for {event_time} at {location}")
        except Exception as e:
            print(f"❌ Failed to add to calendar: {e}")
            
    elif action == "sheet":
        # Add to Google Sheet
        if len(sys.argv) < 3:
            print("Error: Need sheet name and data")
            return
            
        sheet_name = sys.argv[2]
        data = sys.argv[3:]
        
        # Save to sheet file
        sheets_path = Path("/Users/simonstimson/FamilyHQ/sheets_data.json")
        try:
            existing = json.loads(sheets_path.read_text()) if sheets_path.exists() else {}
            if sheet_name not in existing:
                existing[sheet_name] = []
            
            # Create entry with timestamp
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
                "source": "email"
            }
            existing[sheet_name].append(entry)
            sheets_path.write_text(json.dumps(existing, indent=2))
            print(f"✓ Added '{data[0] if data else ''} to sheet: {sheet_name}")
        except Exception as e:
            print(f"❌ Failed to add to sheet: {e}")
            
    elif action == "reminder":
        # Set a cron reminder
        if len(sys.argv) < 4:
            print("Error: Need msg_id, cron, and action")
            return
            
        msg_id = sys.argv[2]
        cron_expr = sys.argv[3]
        action_text = sys.argv[4] if len(sys.argv) > 4 else "action"
        
        # Create reminder file
        reminders_path = Path("/Users/simonstimson/FamilyHQ/reminders.json")
        try:
            existing = json.loads(reminders_path.read_text()) if reminders_path.exists() else []
            
            reminder = {
                "msg_id": msg_id,
                "cron": cron_expr,
                "action": action_text,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending"
            }
            existing.append(reminder)
            reminders_path.write_text(json.dumps(existing, indent=2))
            print(f"✓ Set reminder for email {msg_id} with cron '{cron_expr}' for {action_text}")
        except Exception as e:
            print(f"❌ Failed to set reminder: {e}")
    else:
        print(f"Error: Unknown action '{action}'")

if __name__ == "__main__":
    main()