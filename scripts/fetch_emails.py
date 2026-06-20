#!/usr/bin/env python3
"""
Family HQ Email Fetcher
Fetches unprocessed emails from stimsonfamilyhq@gmail.com via Gmail API.
Outputs JSON array of {id, subject, body, sender, date} to stdout.
These are then interpreted by the agent for intelligent processing.
"""

import json
import sys
import os
import base64
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

FAMILY_EMAIL = "stimsonfamilyhq@gmail.com"
TOKEN_PATH = Path("/Users/simonstimson/.hermes/profiles/home/google_token.json")
PROCESSED_LABEL = "FamilyHQ_Processed"
ALLOWED_SENDERS = [
    "simon.stimson@gmail.com",
    "clementsonemma@gmail.com",
    "eclementson@hotmail.com",
]


def load_token():
    with open(TOKEN_PATH) as f:
        return json.load(f)


def get_access_token():
    tok = load_token()
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
                req = urllib.request.Request(
                    "https://oauth2.googleapis.com/token", data=data, method="POST"
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    result = json.loads(resp.read())
                tok["access_token"] = result["access_token"]
                tok["token"] = result["access_token"]
                tok["expires_in"] = result.get("expires_in", 3599)
                tok["expiry"] = (
                    now + timedelta(seconds=tok["expires_in"])
                ).isoformat()
                with open(TOKEN_PATH, "w") as f:
                    json.dump(tok, f, indent=2)
        except Exception as e:
            print(f"Token refresh failed: {e}", file=sys.stderr)
    return tok.get("access_token") or tok.get("token")


def gmail_get(path, token):
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/{path}"
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def get_or_create_label(token):
    labels = gmail_get("labels", token)
    if "error" in labels:
        return None
    for label in labels.get("labels", []):
        if label["name"] == PROCESSED_LABEL:
            return label["id"]
    result = gmail_get(
        "labels",
        token,
        # POST handled below
    )
    # Create label
    url = "https://gmail.googleapis.com/gmail/v1/users/me/labels"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps({
        "name": PROCESSED_LABEL,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read()).get("id")
    except Exception:
        return None


def get_unprocessed_emails(token):
    query = f"to:{FAMILY_EMAIL} -label:{PROCESSED_LABEL}"
    result = gmail_get(
        f"messages?maxResults=20&q={urllib.parse.quote(query)}", token
    )
    if "error" in result:
        return []
    return result.get("messages", [])


def get_email_detail(msg_id, token):
    return gmail_get(f"messages/{msg_id}?format=full", token)


def extract_body(payload):
    if "body" in payload and payload["body"].get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(
            "utf-8", errors="replace"
        )
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and part["body"].get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                    "utf-8", errors="replace"
                )
            result = extract_body(part)
            if result:
                return result
    return ""


def get_header(headers, name):
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def label_as_processed(msg_id, label_id, token):
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}/modify"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps({
        "addLabelIds": [label_id],
        "removeLabelIds": ["UNREAD"],
    }).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True
    except Exception:
        return False


def main():
    token = get_access_token()
    if not token:
        print(json.dumps({"error": "No access token"}))
        sys.exit(1)

    label_id = get_or_create_label(token)
    if not label_id:
        print(json.dumps({"error": "Could not get/create processed label"}))
        sys.exit(1)

    emails = get_unprocessed_emails(token)
    if not emails:
        print(json.dumps([]))
        sys.exit(0)

    results = []
    for email_info in emails:
        msg_id = email_info["id"]
        detail = get_email_detail(msg_id, token)
        if "error" in detail:
            continue

        headers = detail.get("payload", {}).get("headers", [])
        sender = get_header(headers, "from")
        subject = get_header(headers, "subject")
        date = get_header(headers, "date")
        body = extract_body(detail.get("payload", {}))

        # Extract sender email for filtering
        import re
        sender_email_match = re.search(r"<(.+?)>", sender)
        sender_email = sender_email_match.group(1) if sender_email_match else sender.strip()

        results.append({
            "id": msg_id,
            "subject": subject,
            "body": body[:3000],  # Cap body length
            "sender": sender_email,
            "date": date,
        })

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
