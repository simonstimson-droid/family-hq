#!/usr/bin/env python3
"""
Family HQ Email Processor
Reads emails from stimsonfamilyhq@gmail.com, figures out what they are,
adds them to the correct Google Sheet, and confirms via Telegram.
"""

import json
import re
import sys
import os
import base64
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ---- Config ----
FAMILY_EMAIL = "stimsonfamilyhq@gmail.com"
SHEET_ID = "1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC58LSFXA"
TOKEN_PATH = Path.home() / ".hermes/profiles/home/google_token.json"
PROCESSED_LABEL = "FamilyHQ_Processed"
ALLOWED_SENDERS = [
    "simon.stimson@gmail.com",
    # Add Emma's email when known
]

# ---- Load token ----
def load_token():
    with open(TOKEN_PATH) as f:
        return json.load(f)

def get_access_token():
    """Get a valid access token, refreshing if needed."""
    import urllib.request, urllib.parse
    tok = load_token()
    # Try to use the token directly first
    return tok.get("access_token") or tok.get("token")

def gmail_api_request(method, path, data=None, token=None):
    """Make a Gmail API request."""
    import urllib.request, urllib.parse, json as _json
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/{path}"
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=_json.dumps(data).encode(), headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return _json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def sheets_api_request(method, path, data=None, token=None):
    """Make a Google Sheets API request."""
    import urllib.request, urllib.parse, json as _json
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/{path}"
    headers = {"Authorization": f"Bearer {token}"}
    if data:
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=_json.dumps(data).encode(), headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return _json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def get_or_create_label(token):
    """Get or create the FamilyHQ_Processed label."""
    labels = gmail_api_request("GET", "labels", token=token)
    if "error" in labels:
        return None
    for label in labels.get("labels", []):
        if label["name"] == PROCESSED_LABEL:
            return label["id"]
    # Create it
    result = gmail_api_request("POST", "labels", {"name": PROCESSED_LABEL, "labelListVisibility": "labelShow", "messageListVisibility": "show"}, token=token)
    return result.get("id")

def get_unread_emails(token, label_id=None):
    """Get unread emails in the family inbox."""
    # Search for unread emails NOT already processed
    query = f"is:unread to:{FAMILY_EMAIL}"
    if label_id:
        query += f" -label:{PROCESSED_LABEL}"
    
    result = gmail_api_request("GET", f"messages?maxResults=10&q={urllib.parse.quote(query)}", token=token)
    if "error" in result:
        print(f"Gmail error: {result['error']}")
        return []
    return result.get("messages", [])

def get_email_detail(msg_id, token):
    """Get full email content."""
    return gmail_api_request("GET", f"messages/{msg_id}?format=full", token=token)

def extract_body(payload):
    """Extract plain text body from email payload."""
    if "body" in payload and payload["body"].get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part["body"].get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            # Recurse into multipart
            result = extract_body(part)
            if result:
                return result
    return ""

def get_header(headers, name):
    """Get a specific header value."""
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""

def classify_email(subject, body, sender):
    """Figure out what type of dashboard item this email is about."""
    text = f"{subject} {body}".lower()
    
    # Check for explicit format prefixes
    if subject.upper().startswith("SHOPPING:") or "shopping" in subject.lower():
        return "shopping"
    if subject.upper().startswith("EVENT:") or subject.upper().startswith("CALENDAR:"):
        return "calendar"
    if subject.upper().startswith("CHORE:"):
        return "chore"
    if subject.upper().startswith("MEAL:") or subject.upper().startswith("DINNER:"):
        return "meal"
    if subject.upper().startswith("CONTACT:"):
        return "contact"
    if subject.upper().startswith("NEWS:") or subject.upper().startswith("ANNOUNCEMENT:"):
        return "announcement"
    if subject.upper().startswith("TODO:") or subject.upper().startswith("TO-DO:"):
        return "todo"
    
    # Natural language detection
    calendar_keywords = ["appointment", "dentist", "doctor", "meeting", "party", "pick up", "school trip", "event", "on ", "next ", "at ", "pm", "am"]
    shopping_keywords = ["buy", "shopping", "milk", "bread", "eggs", "get some", "need", "add to list", "shopping list", "groceries"]
    chore_keywords = ["chore", "clean", "tidy", "hoover", "wash", "homework", "practice", "take out", "feed"]
    meal_keywords = ["dinner", "lunch", "breakfast", "meal", "cook", "recipe", "spaghetti", "pizza", "chicken", "pasta"]
    contact_keywords = ["contact", "phone number", "add to contacts", "number is"]
    announcement_keywords = ["announcement", "news", "reminder", "don't forget", "important", "note that"]
    
    scores = {
        "calendar": sum(1 for k in calendar_keywords if k in text),
        "shopping": sum(1 for k in shopping_keywords if k in text),
        "chore": sum(1 for k in chore_keywords if k in text),
        "meal": sum(1 for k in meal_keywords if k in text),
        "contact": sum(1 for k in contact_keywords if k in text),
        "announcement": sum(1 for k in announcement_keywords if k in text),
    }
    
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "unknown"
    return best

def parse_shopping(subject, body):
    """Parse shopping item from email."""
    # Try structured format: SHOPPING: Item | Qty | Category
    text = subject + " " + body
    m = re.search(r"(?i)shopping[:\s]+(.+?)(?:\s*\|\s*(.+?))?(?:\s*\|\s*(.+?))?(?:\n|$)", text)
    if m:
        return {
            "item": m.group(1).strip(),
            "quantity": (m.group(2) or "").strip() or "1",
            "category": (m.group(3) or "").strip() or "Other",
            "added_by": "email"
        }
    # Natural language: extract the item
    for line in text.split("\n"):
        line = line.strip()
        if line and not line.lower().startswith("shopping"):
            return {"item": line[:100], "quantity": "1", "category": "Other", "added_by": "email"}
    return None

def parse_calendar(subject, body):
    """Parse calendar event from email."""
    text = subject + "\n" + body
    
    # Try structured format: EVENT: Title | Date | Start | End | Location
    m = re.search(r"(?i)event[:\s]+(.+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\d{1,2}:\d{2})\s*(?:\|\s*(\d{1,2}:\d{2}))?\s*(?:\|\s*(.+?))?(?:\n|$)", text)
    if m:
        return {
            "title": m.group(1).strip(),
            "date": m.group(2),
            "start": m.group(3),
            "end": m.group(4) or "",
            "location": (m.group(5) or "").strip()
        }
    
    # Try to extract date/time from natural language
    title = subject.replace("EVENT:", "").replace("CALENDAR:", "").strip() or "New Event"
    
    # Look for date patterns
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    date = date_match.group(1) if date_match else ""
    
    # Look for time patterns
    time_match = re.search(r"(\d{1,2}:\d{2})\s*(am|pm)?", text, re.IGNORECASE)
    start_time = time_match.group(0).strip() if time_match else ""
    
    # Look for location
    loc_match = re.search(r"(?:at|in|@)\s+([A-Z][A-Za-z\s]+?)(?:\n|$|\d)", text)
    location = loc_match.group(1).strip() if loc_match else ""
    
    if date or start_time:
        return {"title": title, "date": date, "start": start_time, "end": "", "location": location}
    return None

def parse_chore(subject, body):
    """Parse chore from email."""
    text = subject + "\n" + body
    
    # Try structured format: CHORE: Person | Task | Points | Difficulty
    m = re.search(r"(?i)chore[:\s]+(.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(\w+)", text)
    if m:
        return {
            "person": m.group(1).strip(),
            "task": m.group(2).strip(),
            "points": int(m.group(3)),
            "difficulty": m.group(4).strip().capitalize()
        }
    
    # Natural language
    title = subject.replace("CHORE:", "").strip()
    person = ""
    for name in ["Ava", "Ella", "Simon", "Emma"]:
        if name.lower() in text.lower():
            person = name
            break
    return {
        "person": person or "Family",
        "task": title or "New chore",
        "points": 5,
        "difficulty": "Easy"
    }

def parse_meal(subject, body):
    """Parse meal from email."""
    text = subject + "\n" + body
    
    # Try structured format: MEAL: Day | Meal
    m = re.search(r"(?i)meal[:\s]+(.+?)\s*\|\s*(.+?)(?:\n|$)", text)
    if m:
        return {"day": m.group(1).strip(), "meal": m.group(2).strip()}
    
    # Natural language
    title = subject.replace("MEAL:", "").replace("DINNER:", "").strip()
    day = ""
    for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        if d.lower() in text.lower():
            day = d
            break
    return {"day": day or "Unscheduled", "meal": title or "New meal"}

def parse_contact(subject, body):
    """Parse contact from email."""
    text = subject + "\n" + body
    
    # Try structured format: CONTACT: Name | Phone | Notes
    m = re.search(r"(?i)contact[:\s]+(.+?)\s*\|\s*([\d\s\+]+)\s*(?:\|\s*(.+?))?(?:\n|$)", text)
    if m:
        return {
            "name": m.group(1).strip(),
            "phone": m.group(2).strip(),
            "notes": (m.group(3) or "").strip()
        }
    return None

def parse_announcement(subject, body):
    """Parse announcement from email."""
    text = subject + "\n" + body
    title = subject.replace("NEWS:", "").replace("ANNOUNCEMENT:", "").strip()
    if not title:
        # Use first line of body
        title = body.strip().split("\n")[0][:100] if body.strip() else "New announcement"
    return {"title": title, "body": body.strip()[:500]}

def parse_todo(subject, body):
    """Parse todo from email."""
    text = subject + "\n" + body
    title = subject.replace("TODO:", "").replace("TO-DO:", "").strip()
    if not title:
        title = body.strip().split("\n")[0][:100] if body.strip() else "New task"
    return {"task": title, "assigned_to": "", "due_date": "", "priority": "Medium", "notes": ""}

def append_to_sheet(sheet_name, row_data, token):
    """Append a row to a specific sheet."""
    values = [row_data]
    result = sheets_api_request(
        "POST",
        f"values/{sheet_name}!A1:append",
        {
            "values": values,
            "majorDimension": "ROWS",
            "valueInputOption": "USER_ENTERED"
        },
        token=token
    )
    return "error" not in result

def label_email(msg_id, label_id, token):
    """Add a label to an email to mark it as processed."""
    gmail_api_request(
        "POST",
        f"messages/{msg_id}/modify",
        {"addLabelIds": [label_id], "removeLabelIds": ["UNREAD"]},
        token=token
    )

def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Family HQ Email Processor starting...")
    
    token = get_access_token()
    if not token:
        print("❌ No access token available")
        sys.exit(1)
    
    # Get or create processed label
    label_id = get_or_create_label(token)
    if not label_id:
        print("❌ Could not get/create processed label")
        sys.exit(1)
    
    # Get unread emails
    emails = get_unread_emails(token, label_id)
    if not emails:
        print("No new emails to process")
        sys.exit(0)
    
    print(f"Found {len(emails)} unread email(s)")
    
    results = []
    for email_info in emails:
        msg_id = email_info["id"]
        detail = get_email_detail(msg_id, token)
        if "error" in detail:
            print(f"  ❌ Error fetching email: {detail['error']}")
            continue
        
        headers = detail.get("payload", {}).get("headers", [])
        sender = get_header(headers, "from")
        subject = get_header(headers, "subject")
        body = extract_body(detail.get("payload", {}))
        
        # Check sender is allowed
        sender_email = re.search(r"<(.+?)>", sender)
        sender_email = sender_email.group(1) if sender_email else sender.strip()
        
        if not any(allowed in sender_email.lower() for allowed in ALLOWED_SENDERS):
            print(f"  ⏭ Skipping email from unauthorized sender: {sender_email}")
            label_email(msg_id, label_id, token)
            continue
        
        # Classify the email
        category = classify_email(subject, body, sender)
        print(f"  📧 From: {sender_email} | Subject: {subject[:50]} | Type: {category}")
        
        success = False
        detail_msg = ""
        
        if category == "shopping":
            parsed = parse_shopping(subject, body)
            if parsed:
                row = [parsed["item"], parsed["quantity"], parsed["category"], "", parsed["added_by"]]
                success = append_to_sheet("🛒 Shopping List", row, token)
                detail_msg = f"🛒 Added '{parsed['item']}' to Shopping List"
        
        elif category == "calendar":
            parsed = parse_calendar(subject, body)
            if parsed:
                row = [parsed["title"], parsed["date"], parsed["start"], parsed["end"], parsed["location"], "", "email"]
                success = append_to_sheet("📅 Calendar", row, token)
                detail_msg = f"📅 Added event '{parsed['title']}' to Calendar"
        
        elif category == "chore":
            parsed = parse_chore(subject, body)
            if parsed:
                row = [parsed["person"], parsed["task"], parsed["difficulty"], parsed["points"], "", "Active", "email"]
                success = append_to_sheet("✅ Chores", row, token)
                detail_msg = f"✅ Added chore '{parsed['task']}' for {parsed['person']}"
        
        elif category == "meal":
            parsed = parse_meal(subject, body)
            if parsed:
                row = [parsed["day"], parsed["meal"], "", "email"]
                success = append_to_sheet("🍽️ Meals", row, token)
                detail_msg = f"🍽️ Added meal '{parsed['meal']}' for {parsed['day']}"
        
        elif category == "contact":
            parsed = parse_contact(subject, body)
            if parsed:
                row = [parsed["name"], parsed["phone"], parsed["notes"], "email"]
                success = append_to_sheet("📇 Important Contacts", row, token)
                detail_msg = f"📞 Added contact '{parsed['name']}'"
        
        elif category == "announcement":
            parsed = parse_announcement(subject, body)
            row = [parsed["title"], parsed["body"], datetime.now().strftime("%Y-%m-%d"), "email"]
            success = append_to_sheet("📝 News", row, token)
            detail_msg = f"📝 Added announcement: '{parsed['title']}'"
        
        elif category == "todo":
            parsed = parse_todo(subject, body)
            row = [parsed["task"], parsed["assigned_to"], parsed["due_date"], parsed["priority"], "", parsed["notes"], datetime.now().strftime("%Y-%m-%d")]
            success = append_to_sheet("📌 To-Do", row, token)
            detail_msg = f"📌 Added todo: '{parsed['task']}'"
        
        else:
            print(f"    ⚠️ Could not classify email: {subject[:50]}")
            detail_msg = f"⚠️ Could not understand email: '{subject[:40]}...' — try a clearer format"
        
        # Label as processed
        label_email(msg_id, label_id, token)
        
        if success:
            print(f"    ✅ {detail_msg}")
        results.append(detail_msg if detail_msg else f"Processed: {subject[:40]}")
    
    # Output results for cron delivery
    if results:
        print(f"\n📬 Processed {len(results)} email(s):")
        for r in results:
            print(f"  {r}")
    else:
        print("\nNo emails were processed")

if __name__ == "__main__":
    main()
