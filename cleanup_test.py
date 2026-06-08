#!/usr/bin/env python3
"""Clean up test row from shopping list."""
import json, os, sys

venv_path = "/Users/simonstimson/.hermes/hermes-agent/venv/lib/python3.11/site-packages"
if venv_path not in sys.path:
    sys.path.insert(0, venv_path)

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

TOKEN_FILE = "/Users/simonstimson/.hermes/profiles/home/google_token.json"
SPREADSHEET_ID = "1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA"

creds = Credentials.from_authorized_user_file(TOKEN_FILE)
service = build("sheets", "v4", credentials=creds)

# Get shopping list
result = service.spreadsheets().values().get(
    spreadsheetId=SPREADSHEET_ID,
    range="'🛒 Shopping List!A1:E10"
).execute()
values = result.get("values", [])

print("Shopping list:")
for i, row in enumerate(values):
    print(f"  Row {i+1}: {row}")

# Find and delete test row
for i, row in enumerate(values):
    if row and row[0] == "Test item from dashboard":
        # Get sheet metadata to find sheet ID
        meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheet_id = None
        for s in meta["sheets"]:
            if s["properties"]["title"].startswith("🛒"):
                sheet_id = s["properties"]["sheetId"]
                break
        
        if sheet_id:
            service.spreadsheets().batchUpdate(
                spreadsheetId=SPREADSHEET_ID,
                body={
                    "requests": [{
                        "deleteDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": i,
                                "endIndex": i + 1
                            }
                        }
                    }]
                }
            ).execute()
            print(f"✅ Deleted test row {i+1}")
        break
