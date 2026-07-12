#!/usr/bin/env python3
"""
Re-authorize the FamilyHQ Google token WITH Gmail scopes.

The existing token only had calendar + sheets scopes, so every Gmail API
call returned 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT, which made the old
fetch_emails.py fall back to fake "demo" emails.

This fixes the root cause: re-consent with gmail.readonly + gmail.modify
added alongside the existing calendar + sheets scopes.

Usage:
  python3 reauth_gmail.py url      -> prints the Google consent URL
  python3 reauth_gmail.py exchange <CODE>   -> trades the code for a new token
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from google_auth_oauthlib.flow import Flow

TOKEN_PATH = Path("/Users/simonstimson/.hermes/profiles/home/google_token.json")

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"


def client_config():
    tok = json.load(open(TOKEN_PATH))
    return {
        "installed": {
            "client_id": tok["client_id"],
            "client_secret": tok["client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI],
        }
    }


def print_url():
    # Build the authorization URL manually (NO PKCE) so the returned
    # code is a plain authorization_code that can be exchanged directly.
    tok = json.load(open(TOKEN_PATH))
    params = {
        "response_type": "code",
        "client_id": tok["client_id"],
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    from urllib.parse import urlencode

    url = "https://accounts.google.com/o/oauth2/auth?" + urlencode(params)
    print(url)


def exchange(code):
    flow = Flow.from_client_config(client_config(), scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    flow.fetch_token(code=code)
    creds = flow.credentials

    old = json.load(open(TOKEN_PATH))
    new_tok = {
        "token": creds.token,
        # Keep old refresh_token if Google didn't return one (rare with prompt=consent)
        "refresh_token": creds.refresh_token or old.get("refresh_token"),
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
        "type": "authorized_user",
    }
    # Atomic-ish write: back up then overwrite
    bak = TOKEN_PATH.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}")
    bak.write_text(json.dumps(old, indent=2))
    TOKEN_PATH.write_text(json.dumps(new_tok, indent=2))
    print("✅ New token written with scopes:", creds.scopes)
    print("   (old token backed up to", bak.name + ")")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: reauth_gmail.py url | reauth_gmail.py exchange <CODE>")
        sys.exit(1)
    if sys.argv[1] == "url":
        print_url()
    elif sys.argv[1] == "exchange" and len(sys.argv) == 3:
        exchange(sys.argv[2].strip())
    else:
        print("bad args")
        sys.exit(1)
