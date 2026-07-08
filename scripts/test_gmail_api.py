#!/usr/bin/env python3
"""
Test Gmail API connection directly
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

TOKEN_PATH = Path("/Users/simonstimson/.hermes/profiles/home/google_token.json")

def get_access_token():
    with open(TOKEN_PATH) as f:
        tok = json.load(f)
    expiry_str = tok.get("expiry", "")
    if expiry_str:
        try:
            exp_dt = datetime.fromisoformat(expiry_str)
            now = datetime.now(timezone.utc)
            if exp_dt <= now:
                print("Token expired, need refresh")
                return None
        except Exception as e:
            print(f"Error parsing expiry: {e}")
    return tok.get("access_token") or tok.get("token")

def test_labels():
    token = get_access_token()
    if not token:
        print("No valid token")
        return
    
    print(f"Token (first 20 chars): {token[:20]}...")
    
    url = "https://gmail.googleapis.com/gmail/v1/users/me/labels"
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            print("Labels API response:")
            print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_labels()