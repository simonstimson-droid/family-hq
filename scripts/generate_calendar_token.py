#!/usr/bin/env python3
"""Generate / exchange a Google Calendar token for Simon's PERSONAL account.

The Family HQ pipeline uses stimsonfamilyhq@gmail.com for Gmail + Sheets, but
that account cannot see Emma's calendar (or, until shared, the Family calendar).
Simon's PERSONAL Google account DOES have access to both calendars, so calendar
fetches use a SEPARATE token for the personal account (calendar.readonly scope).

This reuses the same OAuth app (client id/secret) as the main token, so no
change to the Google Cloud project is needed. Simon must authenticate while
logged in as his PERSONAL account (he owns the OAuth app, so no test-user
approval is required).

Usage:
  python3 generate_calendar_token.py url            # print consent URL
  python3 generate_calendar_token.py exchange CODE  # save token to disk
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

TOKEN_PATH = "/Users/simonstimson/.hermes/profiles/home/google_token_calendar.json"
MAIN_TOKEN = "/Users/simonstimson/.hermes/profiles/home/google_token.json"
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
# Read-WRITE calendar scope so we can also delete/correct events (e.g. the
# incorrect "Last Day of Term - Ella" entry) via the API, not just read them.
SCOPES = ["https://www.googleapis.com/auth/calendar"]
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def client_config():
    return json.load(open(MAIN_TOKEN))


def print_url():
    t = client_config()
    params = {
        "response_type": "code",
        "client_id": t["client_id"],
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    url = AUTH_ENDPOINT + "?" + urllib.parse.urlencode(params)
    print(url)


def exchange(code):
    t = client_config()
    data = {
        "code": code,
        "client_id": t["client_id"],
        "client_secret": t["client_secret"],
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    req = urllib.request.Request(
        TOKEN_ENDPOINT, data=urllib.parse.urlencode(data).encode(), method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        r = json.loads(resp.read())
    out = {
        "token": r["access_token"],
        "access_token": r["access_token"],
        "refresh_token": r["refresh_token"],
        "token_uri": t.get("token_uri", "https://oauth2.googleapis.com/token"),
        "client_id": t["client_id"],
        "client_secret": t["client_secret"],
        "scopes": SCOPES,
        "expiry": (
            datetime.now(timezone.utc) + timedelta(seconds=r.get("expires_in", 3599))
        ).isoformat(),
    }
    # Back up the existing token before overwriting (the other reauth scripts
    # do this; this one originally didn't).
    from pathlib import Path as _P
    _tp = _P(TOKEN_PATH)
    if _tp.exists():
        _tp.with_suffix(".json.bak").write_text(_tp.read_text())
    with open(TOKEN_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print("Saved calendar token to", TOKEN_PATH)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "url":
        print_url()
    elif len(sys.argv) > 2 and sys.argv[1] == "exchange":
        exchange(sys.argv[2])
    else:
        print("Usage: python3 generate_calendar_token.py [url|exchange CODE]")
