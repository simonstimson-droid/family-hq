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
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

# ---- Config ----
FAMILY_EMAIL = "stimsonfamilyhq@gmail.com"
SHEET_ID = "1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA"
TOKEN_PATH = Path("/Users/simonstimson/.hermes/profiles/home/google_token.json")
PROCESSED_LABEL = "FamilyHQ_Processed"

# We process the WHOLE inbox now (schools / hospitals / clubs / etc. are
# external senders). Instead of an allowlist, a confidence gate + the LLM
# classifier decide what gets written. Low-confidence mail is left in the
# inbox and flagged to Simon — never silently dropped.
ALLOWED_SENDERS = []  # empty = process all unread mail

# Promotional / newsletter / marketing senders that should NEVER be auto-filed
# to the dashboard (they are not family-relevant). Matched as a substring of
# the sender's email/name (case-insensitive). Mail from these is left in the
# inbox and skipped.
PROMO_SENDERS = [
    "mse's money tips", "moneysavingexpert", "stylelife", "dating tips",
    "newsletter", "marketing", "promo", "offers", "groupon", "voucher",
    "noreply", "no-reply", "mailchimp", "substack", "medium.com",
    "linkedin", "facebook", "instagram", "x.com", "twitter",
]

def is_promo(sender):
    """True if the sender looks like marketing/promo and should be skipped."""
    s = (sender or "").lower()
    return any(p in s for p in PROMO_SENDERS)

# Dashboard destinations the LLM may route to. Using the exact sheet tab
# titles so the writer can append directly.
CATEGORY_TO_SHEET = {
    "calendar":       "📅 Calendar",
    "shopping":       "🛒 Shopping List",
    "chore":          "✅ Chores",
    "meal":           "🍽️ Meal Plan",
    "contact":        "📞 Important Contacts",
    "announcement":   "📝 Announcements",
    "todo":           "📌 To-Do",
    "medical":        "📝 Announcements",   # medical/school notices -> Announcements (flagged)
    "unknown":        None,
}

# OpenRouter key resolution: prefer env var (set by Hermes agent runtime),
# else a local secrets file. If neither is present, the processor falls back
# to the deterministic regex classifier (still works, just less accurate).
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_KEY_FILE = "/Users/simonstimson/.hermes/profiles/home/secrets/openrouter_key.txt"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/auto")

def get_openrouter_key():
    key = os.environ.get(OPENROUTER_KEY_ENV, "").strip()
    if key:
        return key
    try:
        with open(OPENROUTER_KEY_FILE) as f:
            key = f.read().strip()
            return key or None
    except Exception:
        return None

# ---- Load token ----
def load_token():
    with open(TOKEN_PATH) as f:
        return json.load(f)

def get_access_token():
    """Get a valid access token, refreshing if expired."""
    import urllib.request, urllib.parse, ssl
    from datetime import datetime, timezone, timedelta
    tok = load_token()
    # Check if token is expired
    expiry_str = tok.get('expiry', '')
    if expiry_str:
        try:
            exp_dt = datetime.fromisoformat(expiry_str)
            if exp_dt.tzinfo is None:
                # Stored expiry is naive; Google tokens are UTC
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if exp_dt <= now:
                # Token expired — refresh it silently
                params = {
                    'client_id': tok['client_id'],
                    'client_secret': tok['client_secret'],
                    'refresh_token': tok['refresh_token'],
                    'grant_type': 'refresh_token'
                }
                data = urllib.parse.urlencode(params).encode()
                req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                tok['access_token'] = result['access_token']
                tok['token'] = result['access_token']
                tok['expires_in'] = result.get('expires_in', 3599)
                tok['expiry'] = (now + timedelta(seconds=tok['expires_in'])).isoformat()
                with open(TOKEN_PATH, 'w') as f:
                    json.dump(tok, f, indent=2)
        except Exception as e:
            print(f"Token refresh failed: {e}", flush=True)
    return tok.get("access_token") or tok.get("token")

def llm_classify(subject, body, sender):
    """Use the LLM (OpenRouter) to classify an email and extract structured
    fields. Returns a dict:
        {category, confidence, summary, fields:{date,time,who,amount,
         action_needed}, medical:bool}
    Falls back to the regex classifier if no OpenRouter key is available.
    """
    key = get_openrouter_key()
    if not key:
        # Graceful fallback: deterministic regex classifier.
        cat = classify_email(subject, body, sender)
        return {
            "category": cat,
            "confidence": 0.5,
            "summary": subject[:120],
            "fields": {},
            "medical": False,
            "llm": False,
        }

    # Strip forward boilerplate so the model reads the ORIGINAL message.
    clean = strip_forward_boilerplate(subject, body)
    prompt = (
        "You are a household email triage assistant for the Stimson family "
        "(Simon, Emma, Ava age 7, Ella age 10). Emails arrive from schools, "
        "hospitals, doctors, clubs, and shops. Classify the email and extract "
        "key fields. Reply with ONLY a JSON object, no prose.\n\n"
        "CATEGORIES (use exactly these keys):\n"
        "  calendar - a dated event/appointment/trip/club session\n"
        "  shopping - something to buy / item needed\n"
        "  chore - a task to do\n"
        "  meal - a meal/food plan item\n"
        "  contact - a new phone/contact to save\n"
        "  announcement - general info/notice (incl. medical & school letters)\n"
        "  todo - an action item / reminder\n"
        "  medical - appointment or result from a hospital/doctor/clinic\n"
        "  unknown - truly unclear OR marketing/promo/newsletter/spam "
        "(e.g. money tips, dating tips, sales, social-media notifications)\n\n"
        "JSON shape:\n"
        '{"category":"...","confidence":0.0-1.0,"medical":true/false,'
        '"summary":"one line","fields":{"date":"YYYY-MM-DD or empty",'
        '"time":"HH:MM or empty","who":"Ava/Ella/Emma/Simon or empty",'
        '"amount":"£.. or empty","action_needed":"short or empty"}}\n\n'
        f"From: {sender}\nSubject: {clean['subject']}\n\nBody:\n{clean['body'][:2500]}"
    )
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    try:
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        result = json.loads(content)
        result["llm"] = True
        # Normalise category to a known key.
        cat = str(result.get("category", "unknown")).lower()
        if cat not in CATEGORY_TO_SHEET:
            cat = "unknown"
        result["category"] = cat
        return result
    except Exception as e:
        print(f"    ⚠️ LLM classify failed ({e}); using regex fallback", flush=True)
        cat = classify_email(subject, body, sender)
        return {
            "category": cat,
            "confidence": 0.4,
            "summary": subject[:120],
            "fields": {},
            "medical": False,
            "llm": False,
        }


def strip_forward_boilerplate(subject, body):
    """Return {subject, body} with forwarded-email quoting removed so the
    model reads the original message, not the forwarding wrapper."""
    clean_subject = re.sub(r"^(fwd|fw|fwd:|fw:)\s*", "", subject, flags=re.IGNORECASE).strip()
    text = body
    # Cut at the forwarded-message marker.
    m = re.search(r"Begin forwarded message:", text, re.IGNORECASE)
    if m:
        text = text[:m.start()]
    # Drop quoted lines.
    lines = [l for l in text.split("\n") if not l.strip().startswith(">")]
    text = "\n".join(lines).strip()
    # Drop mobile sigs.
    text = re.sub(r"(?i)sent from my (iphone|android|phone).*$", "", text).strip()
    return {"subject": clean_subject or subject, "body": text[:3000]}


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
    """Get emails in the family inbox that haven't been processed yet.
    Checks both unread emails AND read emails without the processed label
    (to catch forwarded emails which Gmail auto-marks as read)."""
    # Search for emails to family inbox that don't have the processed label
    # This catches both unread emails AND forwarded emails (which are auto-read)
    query = f"to:{FAMILY_EMAIL} -label:{PROCESSED_LABEL}"
    
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
    # Strip Fwd: prefix for classification
    clean_subject = re.sub(r"^(fwd|fw):\s*", "", subject, flags=re.IGNORECASE).strip()
    text = f"{clean_subject} {body}".lower()
    
    # Check for explicit format prefixes (on original subject)
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
    
    # ---- Natural-language classification (priority order) ----
    # NOTE: avoid bare "am"/"pm"/"on "/"at " substrings — they match inside
    # ordinary words (e.g. "name", "team") and cause false calendar hits.
    subj_l = subject.lower()

    # 1) Payments / money notices FIRST (so "Dinner Money" doesn't get caught
    #    by the meal rule, and "MCAS payment" isn't treated as an event).
    payment_keywords = ["dinner money", "balance is getting low", "balance low",
                        "payment due", "payment", "invoice", "outstanding balance",
                        "please pay", "money owed", "mcas"]
    if any(k in text for k in payment_keywords):
        return "shopping"

    # 2) Explicit meal/food request.
    meal_words = ["dinner", "lunch", "breakfast", "meal", "cook", "recipe",
                  "spaghetti", "pizza", "chicken", "pasta", "order food", "food order"]
    if any(k in text for k in meal_words):
        return "meal"

    # 3) Clear shopping ITEM words win over generic calendar words
    #    ("tea towel", "uniform", "costume", "ticket", "order", "buy"...).
    shopping_words = ["buy", "shopping", "milk", "bread", "eggs", "get some", "need",
                      "add to list", "shopping list", "groceries", "tea towel", "towel",
                      "uniform", "costume", "ticket", "order", "item"]
    if any(k in text for k in shopping_words):
        return "shopping"

    # 4) Calendar: explicit EVENT words OR a real time pattern (digit + am/pm,
    #    or HH:MM). Catches trips, colour runs, appointments, lessons, etc.
    has_real_time = bool(re.search(r"\d{1,2}\s*(?:am|pm)\b|\d{1,2}:\d{2}", text))
    calendar_words = ["appointment", "dentist", "doctor", "party",
                      "pick up", "school trip", "colour run", "sports day",
                      "summer fete", "fete", "trip", "visit", "parents evening",
                      "concert", "performance", "assembly"]
    # "meeting"/"event" intentionally excluded here: a bare "meeting" inside a
    # newsletter/announcement should NOT force a calendar event. Only count
    # them when paired with a real time.
    if has_real_time or any(w in text for w in calendar_words):
        return "calendar"

    # 5) Remaining categories
    if any(k in text for k in ["chore", "clean", "tidy", "hoover", "wash", "homework", "practice", "take out", "feed"]):
        return "chore"
    if any(k in text for k in ["contact", "phone number", "add to contacts", "number is"]):
        return "contact"
    if any(k in text for k in ["announcement", "news", "reminder", "don't forget", "important", "note that", "school", "academy", "bulletin", "newsletter", "update", "dear families", "pupils", "year 5", "year 3", "pta", "meeting", "event"]):
        return "announcement"

    return "unknown"

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
    """Parse calendar event from email, including forwarded email headers."""
    text = subject + "\n" + body
    
    # Try structured format: EVENT: Title | Date | Start | End | Location
    m = re.search(r"(?i)event[:\s]+(.+?)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(\d{1,2}:\d{2})\s*(?:\|\s*(\d{1,2}:\d{2}))?\s*(?:\|\s*(.+?))?(?:\n|$)", text)
    if m:
        return {
            "title": m.group(1).strip(),
            "date": m.group(2),
            "start": m.group(3),
            "end": m.group(4) or "",
            "location": (m.group(5) or "").strip(),
            "notes": ""
        }
    
    # Natural language: extract the title (strip Fwd: prefix)
    title = re.sub(r"^(fwd|fw):\s*", "", subject, flags=re.IGNORECASE).strip()
    title = title.replace("EVENT:", "").replace("CALENDAR:", "").strip() or "New Event"
    
    # === Extract info from forwarded email headers ===
    # Look for "From:" header to get original sender (often the school)
    fwd_from = re.search(r">\s*From:\s*(.+?)(?:\n|$)", body)
    original_sender = fwd_from.group(1).strip() if fwd_from else ""
    
    # Look for "Date:" header in forwarded content
    fwd_date = re.search(r">\s*Date:\s*(.+?)(?:\n|$)", body)
    original_date_str = fwd_date.group(1).strip() if fwd_date else ""
    
    # Look for "Subject:" header in forwarded content
    fwd_subject = re.search(r">\s*Subject:\s*(.+?)(?:\n|$)", body)
    original_subject = fwd_subject.group(1).strip() if fwd_subject else ""
    
    # Use forwarded subject if main subject is just "Fwd: ..."
    if original_subject and subject.lower().startswith("fwd:"):
        title = original_subject
    
    # === Extract date from body and forwarded headers ===
    date = ""
    start_time = ""
    location = ""
    notes_parts = []
    # Clean body for date/time searching: remove forwarded email header lines
    # This prevents matching the email's own send date as the event date
    clean_text_for_dates = body
    # Remove "Sent from my iPhone" line (single line only)
    clean_text_for_dates = re.sub(r"^Sent from my iPhone\s*$", "", clean_text_for_dates, flags=re.MULTILINE | re.IGNORECASE)
    # Remove forwarded header lines (lines starting with > that contain From:, Date:, Subject:, To:, Reply-To:)
    clean_text_for_dates = re.sub(r"^>\s*(From|Date|Subject|To|Reply-To|Cc|Bcc):.*$", "", clean_text_for_dates, flags=re.MULTILINE | re.IGNORECASE)
    # Remove the "Begin forwarded message:" line itself
    clean_text_for_dates = re.sub(r"^.*Begin forwarded message:.*$", "", clean_text_for_dates, flags=re.MULTILINE | re.IGNORECASE)
    # Remove any remaining blank lines at the start
    clean_text_for_dates = clean_text_for_dates.lstrip()
    clean_text_for_dates = subject + "\n" + clean_text_for_dates
    
    # Try to parse date from forwarded email header (e.g. "Date: 12 June 2026 at 09:48:39 BST")
    header_date_str = ""
    if original_date_str:
        header_date = re.search(r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})", original_date_str, re.IGNORECASE)
        if header_date:
            d = int(header_date.group(1))
            month_names = ["january","february","march","april","may","june","july","august","september","october","november","december"]
            m = month_names.index(header_date.group(2).lower()) + 1
            y = int(header_date.group(3))
            header_date_str = f"{y}-{m:02d}-{d:02d}"
    
    # Try ISO date format first (YYYY-MM-DD)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", clean_text_for_dates)
    if date_match:
        date = date_match.group(1)
    
    # Try UK date formats: "25 June 2026", "25th June 2026"
    if not date:
        uk_date = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})", clean_text_for_dates, re.IGNORECASE)
        if uk_date:
            d = int(uk_date.group(1))
            month_names = ["january","february","march","april","may","june","july","august","september","october","november","december"]
            m = month_names.index(uk_date.group(2).lower()) + 1
            y = int(uk_date.group(3))
            date = f"{y}-{m:02d}-{d:02d}"
    
    # Try short UK date: "25/06/2026" or "25-06-2026"
    if not date:
        short_date = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", clean_text_for_dates)
        if short_date:
            d, m, y = int(short_date.group(1)), int(short_date.group(2)), int(short_date.group(3))
            if d > 12:  # DD/MM/YYYY
                date = f"{y}-{m:02d}-{d:02d}"
            elif m > 12:
                date = f"{y}-{d:02d}-{m:02d}"
            else:
                date = f"{y}-{m:02d}-{d:02d}"
    
    # Do NOT silently fall back to the email/forward header date — that is a
    # SEND date, not the event date, and leads to wrong calendar entries.
    # If we still have no date from the body, leave it empty and flag for review.
    if not date and header_date_str:
        notes_parts.append("⚠️ No event date found in email body — please add the correct date manually (header date was a send date, not used)")
    
    # Look for time patterns — be more specific to avoid matching years like 2026
    time_patterns = [
        (r"(\d{1,2}):(\d{2})\s*(am|pm)", "ampm"),      # 2:30pm
        (r"(\d{1,2})\s*(am|pm)", "ampm_short"),          # 2pm
        (r"(?<!\d)(\d{1,2}):(\d{2})(?!\s*(am|pm|\w))", "24h"),  # 14:30 (no am/pm)
    ]
    for pattern, kind in time_patterns:
        time_match = re.search(pattern, clean_text_for_dates, re.IGNORECASE)
        if time_match:
            groups = time_match.groups()
            if kind == "ampm":
                hour, minute, ampm = int(groups[0]), groups[1], groups[2]
                if ampm.lower() == "pm" and hour < 12: hour += 12
                elif ampm.lower() == "am" and hour == 12: hour = 0
                start_time = f"{hour:02d}:{minute}"
                break
            elif kind == "ampm_short":
                hour, ampm = int(groups[0]), groups[1]
                if ampm.lower() == "pm" and hour < 12: hour += 12
                elif ampm.lower() == "am" and hour == 12: hour = 0
                start_time = f"{hour:02d}:00"
                break
            elif kind == "24h":
                hour, minute = int(groups[0]), int(groups[1])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    start_time = f"{hour:02d}:{minute}"
                    break
    
    # Look for location patterns
    loc_patterns = [
        r"(?:at|in|@)\s+([A-Z][A-Za-z\s]+?)(?:\n|$|\d)",
        r"(?:venue|where|held at)[:\s]+([A-Z][A-Za-z\s]+?)(?:\n|$)",
        r"(?:location)[:\s]+([A-Z][A-Za-z\s]+?)(?:\n|$)",
    ]
    for pattern in loc_patterns:
        loc_match = re.search(pattern, text, re.IGNORECASE)
        if loc_match:
            location = loc_match.group(1).strip()
            break
    
    # Look for day-of-week patterns (e.g. "next Thursday", "on Friday")
    if not date:
        day_match = re.search(r"(?:on|this|next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", text, re.IGNORECASE)
        if day_match:
            from datetime import datetime, timedelta
            day_str = day_match.group(1).capitalize()
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            target_day = days.index(day_str)
            today = datetime.now()
            days_ahead = (target_day - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            next_date = today + timedelta(days=days_ahead)
            date = next_date.strftime("%Y-%m-%d")
    
    # Build notes
    if not date and not start_time:
        notes_parts.insert(0, "⚠️ Date/time not found — please check original email/attachment for details")
    elif not date:
        notes_parts.insert(0, "⚠️ Date not found — please check original email")
    elif not start_time:
        notes_parts.insert(0, "⚠️ Time not found — please check original email")
    
    notes = " | ".join(notes_parts)
    
    return {"title": title, "date": date, "start": start_time, "end": "", "location": location, "notes": notes}

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
    # Strip Fwd:/Fw: prefix and clean subject
    clean_subject = re.sub(r"^(fwd|fw):\s*", "", subject, flags=re.IGNORECASE).strip()
    title = clean_subject.replace("NEWS:", "").replace("ANNOUNCEMENT:", "").strip()
    if not title:
        # Use first meaningful line of body (skip forwarded headers)
        for line in body.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith(">") and not line.startswith("From:") and not line.startswith("Date:") and not line.startswith("Subject:") and not line.startswith("To:") and not line.startswith("Reply-To:") and line != "Sent from my iPhone" and not line.startswith("Begin forwarded message"):
                title = line[:100]
                break
        if not title:
            title = "New announcement"
    # Clean up body: remove forwarded email headers
    clean_body = body.strip()
    # Try to extract just the forwarded content
    fwd_match = re.search(r"Begin forwarded message:(.+)", clean_body, re.DOTALL | re.IGNORECASE)
    if fwd_match:
        clean_body = fwd_match.group(1).strip()
    # Remove quoted lines (starting with >)
    clean_lines = [l for l in clean_body.split("\n") if not l.strip().startswith(">")]
    clean_body = "\n".join(clean_lines).strip()[:500]
    return {"title": title, "body": clean_body}

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
    # IMPORTANT: valueInputOption is a QUERY parameter on the Sheets
    # values.append endpoint, NOT part of the JSON body. Putting it in the
    # body causes HTTP 400 "Unknown name valueInputOption" and silent failure.
    result = sheets_api_request(
        "POST",
        f"values/{sheet_name}!A1:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS",
        {
            "values": values,
            "majorDimension": "ROWS"
        },
        token=token
    )
    return "error" not in result

def label_email(msg_id, label_id, token):
    """Add a label to an email to mark it as processed.
    Returns True on success, False on failure (e.g. insufficient scopes)."""
    result = gmail_api_request(
        "POST",
        f"messages/{msg_id}/modify",
        {"addLabelIds": [label_id], "removeLabelIds": ["UNREAD"]},
        token=token
    )
    if "error" in result:
        print(f"    ⚠️ Could not label email as processed: {result['error']}")
        return False
    return True

def route_and_write(category, fields, medical, subject, body, token, label_id, msg_id):
    """Deterministically route a classified email to the correct sheet tab
    and label it processed. Returns (success: bool, detail_msg: str)."""
    fields = fields or {}
    sheet_name = CATEGORY_TO_SHEET.get(category)
    success = False
    detail_msg = ""

    if category in ("calendar", "medical"):
        parsed = parse_calendar(subject, body)
        if fields.get("date"):
            parsed["date"] = fields["date"]
        if fields.get("time"):
            parsed["start"] = fields["time"]
        if fields.get("who"):
            parsed["title"] = f"{fields['who']}: {parsed['title']}"
        tag = "🏥" if medical else "📅"
        row = [parsed["date"], parsed["start"], parsed["title"],
               "email", parsed["location"], parsed.get("notes", "")]
        sheet_name = "📅 Calendar"
        success = append_to_sheet(sheet_name, row, token)
        detail_msg = f"{tag} Added {'medical ' if medical else ''}event '{parsed['title']}' to Calendar"
        if parsed.get("notes"):
            detail_msg += f" ({parsed['notes']})"
    elif category == "shopping":
        item = fields.get("summary") or subject
        row = [item[:100], "1", "email", "", "Other"]
        success = append_to_sheet("🛒 Shopping List", row, token)
        detail_msg = f"🛒 Added '{item[:60]}' to Shopping List"
    elif category == "chore":
        task = fields.get("summary") or subject
        row = [task[:100], fields.get("who", ""), "", "Once", "", ""]
        success = append_to_sheet("✅ Chores", row, token)
        detail_msg = f"✅ Added chore '{task[:50]}'"
    elif category == "meal":
        row = [fields.get("date", ""), "", "", fields.get("summary", subject)[:100], ""]
        success = append_to_sheet("🍽️ Meal Plan", row, token)
        detail_msg = f"🍽️ Added meal '{fields.get('summary', subject)[:40]}'"
    elif category == "contact":
        row = [fields.get("summary", subject)[:60], "Contact",
               fields.get("amount", ""), "", "", ""]
        success = append_to_sheet("📞 Important Contacts", row, token)
        detail_msg = f"📞 Added contact '{fields.get('summary', subject)[:40]}'"
    elif category == "announcement":
        title = fields.get("summary") or subject
        note = ("🏥 MEDICAL: " if medical else "") + (fields.get("action_needed", "") or "")
        row = [datetime.now().strftime("%Y-%m-%d"), "email",
               f"{title}: {fields.get('body', '')[:200]}", "Info"]
        success = append_to_sheet("📝 Announcements", row, token)
        detail_msg = f"📝 Added announcement: '{title[:50]}'" + (f" ({note})" if note else "")
    elif category == "todo":
        row = [fields.get("summary", subject)[:100], fields.get("who", ""),
               fields.get("date", ""), "Medium", "", "", datetime.now().strftime("%Y-%m-%d")]
        success = append_to_sheet("📌 To-Do", row, token)
        detail_msg = f"📌 Added todo: '{fields.get('summary', subject)[:40]}'"
    else:
        return False, f"⚠️ Unrouted category '{category}' — left in inbox"

    if success:
        label_email(msg_id, label_id, token)
    return success, detail_msg


def emit_pending():
    """Print unread (unprocessed) emails as a JSON array for an LLM to
    classify. Includes only id, sender, subject, body (forward-stripped)."""
    token = get_access_token()
    if not token:
        print(json.dumps({"error": "no token"}))
        return
    label_id = get_or_create_label(token)
    emails = get_unread_emails(token, label_id) if label_id else []
    out = []
    for e in emails:
        detail = get_email_detail(e["id"], token)
        if "error" in detail:
            continue
        headers = detail.get("payload", {}).get("headers", [])
        sender = get_header(headers, "from")
        subject = get_header(headers, "subject")
        body = extract_body(detail.get("payload", {}))
        clean = strip_forward_boilerplate(subject, body)
        out.append({
            "id": e["id"],
            "sender": sender,
            "subject": subject,
            "body": clean["body"][:3000],
        })
    print(json.dumps({"emails": out}, ensure_ascii=False))


def apply_classifications(path):
    """Read a JSON file of [{id, category, confidence, medical, fields}] and
    write each (deterministically) to the dashboard. Low confidence => skip."""
    token = get_access_token()
    if not token:
        print("❌ No access token available")
        sys.exit(1)
    label_id = get_or_create_label(token)
    if not label_id:
        print("❌ Could not get/create processed label")
        sys.exit(1)
    data = json.load(open(path))
    items = data if isinstance(data, list) else data.get("emails", data.get("items", []))
    results = []
    HIGH = 0.7
    for it in items:
        msg_id = it["id"]
        category = str(it.get("category", "unknown")).lower()
        confidence = float(it.get("confidence", 0.5))
        medical = bool(it.get("medical"))
        subject = it.get("subject", "")
        sender = it.get("sender", "")
        if is_promo(sender) or is_promo(subject):
            results.append(f"⏭️ Skipped promo sender: {subject[:50]}")
            continue
        if category not in CATEGORY_TO_SHEET or category == "unknown" or confidence < HIGH:
            results.append(f"⚠️ Skipped (conf={confidence:.2f}) {subject[:50]}")
            continue
        ok, msg = route_and_write(
            category, it.get("fields", {}) or {}, medical,
            subject, it.get("body", ""), token, label_id, msg_id)
        results.append(msg)
    print(f"\n📬 Applied {len(results)} classification(s):")
    for r in results:
        print(f"  {r}")


def main():

    # Silent startup — only output if something happens
    
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
        # Silent exit — nothing to process
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
        sender_email = re.search(r"<(.+?)>", sender)
        sender_email = sender_email.group(1) if sender_email else sender.strip()

        # Skip promotional / marketing senders — never auto-file to dashboard.
        if is_promo(sender) or is_promo(sender_email):
            print(f"  ⏭ Skipping promo/marketing sender: {sender_email}")
            label_email(msg_id, label_id, token)
            continue
        subject = get_header(headers, "subject")
        body = extract_body(detail.get("payload", {}))
        
        # Classify with the LLM (falls back to regex if no key).
        result = llm_classify(subject, body, sender)
        category = result["category"]
        confidence = float(result.get("confidence", 0.5))
        medical = bool(result.get("medical"))
        print(f"  📧 From: {sender_email} | Subject: {subject[:50]} | "
              f"Type: {category} (conf={confidence:.2f}{', MEDICAL' if medical else ''})", flush=True)

        # Confidence gate: only WRITE when we're reasonably sure. Low
        # confidence => leave the email in the inbox and flag it to Simon.
        HIGH = 0.7
        if category == "unknown" or confidence < HIGH:
            note = (f"⚠️ Low-confidence ({category}, {confidence:.2f}) — left in inbox for review: "
                    f"{subject[:50]}")
            results.append(note)
            print(f"    {note}", flush=True)
            # Do NOT label as processed, so it stays actionable.
            continue

        # Route + write deterministically.
        ok, detail_msg = route_and_write(
            category, result.get("fields", {}) or {}, medical,
            subject, body, token, label_id, msg_id)
        if detail_msg:
            results.append(detail_msg)
        if ok:
            print(f"    ✅ {detail_msg}", flush=True)
        else:
            print(f"    ❌ {detail_msg} (write failed — left in inbox)", flush=True)

    
    # Output results for cron delivery
    if results:
        print(f"\n📬 Processed {len(results)} email(s):")
        for r in results:
            print(f"  {r}")
    else:
        print("\nNo emails were processed")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--emit", action="store_true",
                   help="Print pending unread emails as JSON (for LLM classification)")
    p.add_argument("--apply", metavar="FILE",
                   help="Apply classifications from a JSON file (deterministic write)")
    p.add_argument("--dry-run", action="store_true",
                   help="With --emit: also run the built-in classifier and print its verdicts")
    args = p.parse_args()

    if args.emit:
        emit_pending()
    elif args.apply:
        apply_classifications(args.apply)
    else:
        main()
