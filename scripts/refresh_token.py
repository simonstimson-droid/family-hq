#!/usr/bin/env python3
"""Refresh Google OAuth token."""
import json, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

TOKEN_FILE = "/Users/simonstimson/.hermes/profiles/home/google_token.json"

with open(TOKEN_FILE) as f:
    tok = json.load(f)

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
tok["expiry"] = (datetime.now(timezone.utc) + timedelta(seconds=tok["expires_in"])).isoformat()

with open(TOKEN_FILE, "w") as f:
    json.dump(tok, f, indent=2)

print(f"Token refreshed, new expiry: {tok['expiry']}")
