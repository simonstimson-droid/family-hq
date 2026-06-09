#!/usr/bin/env python3
"""
One-time Google OAuth token generator for Family HQ.
Run this once on your iMac to generate a calendar+sheets token.

Usage:
    python3 scripts/google_auth.py

This opens a browser for Google sign-in and saves the token locally.
"""

import json
import os
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "google-auth-oauthlib"])
    from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/spreadsheets',
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_PATH = os.path.join(SCRIPT_DIR, "client_secrets.json")
TOKEN_DIRS = [
    os.path.expanduser("~/.hermes/profiles/home"),
    SCRIPT_DIR,
]
TOKEN_FILENAME = "google_token.json"

def find_token():
    for d in TOKEN_DIRS:
        p = os.path.join(d, TOKEN_FILENAME)
        if os.path.exists(p):
            return p
    return os.path.join(TOKEN_DIRS[0], TOKEN_FILENAME)

def main():
    print("=" * 50)
    print("Family HQ — Google Calendar + Sheets Auth")
    print("=" * 50)
    print()

    token_path = find_token()
    
    # Check for existing valid token
    if os.path.exists(token_path):
        from google.oauth2.credentials import Credentials
        creds = __import__('google.oauth2.credentials', fromlist=['Credentials']).Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds and creds.valid:
            print("✅ Existing token is valid!")
            print(f"   Token: {token_path}")
            return
        elif creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            with open(token_path, 'w') as f:
                f.write(creds.to_json())
            print(f"✅ Token refreshed! Saved to: {token_path}")
            return
    
    # Need to authenticate
    if not os.path.exists(CLIENT_PATH):
        print("❌ No client_secrets.json found!")
        print(f"   Expected at: {CLIENT_PATH}")
        print()
        print("To create one (2 minutes):")
        print()
        print("1. Go to https://console.cloud.google.com/apis/credentials")
        print("2. If no project exists, click 'CREATE PROJECT' → name it 'Family HQ'")
        print("3. Click '+ CREATE CREDENTIALS' → 'OAuth client ID'")
        print("   - If asked for consent screen: choose 'External', fill in")
        print("     App name: 'Family HQ', Email: your email")
        print("   - Application type: 'Desktop app'")
        print("   - Name: 'Family HQ Desktop'")
        print("4. Click 'DOWNLOAD JSON'")
        print(f"5. Save the file to: {CLIENT_PATH}")
        print()
        print("Then enable these APIs:")
        print("  APIs & Services → Library → Search each and click Enable:")
        print("  - Google Calendar API")
        print("  - Google Sheets API")
        print()
        print("Then run this script again: python3 scripts/google_auth.py")
        sys.exit(1)
    
    print("🌐 Opening browser for Google authorization...")
    print("   Sign in with simon.stimson@gmail.com")
    print()
    
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_PATH, SCOPES)
    creds = flow.run_local_server(port=0)
    
    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, 'w') as f:
        f.write(creds.to_json())
    
    print(f"✅ Token saved to: {token_path}")
    print()
    print("Google Calendar + Sheets access is now configured!")
    print("The Family HQ dashboard can now sync with your Google Calendar.")

if __name__ == '__main__':
    main()
