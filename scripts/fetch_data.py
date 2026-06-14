#!/usr/bin/env python3
"""
Fetch all data from Family HQ Google Sheet and output as JSON.
Works both locally and in GitHub Actions.

Environment variables:
    GOOGLE_TOKEN_JSON - Google OAuth token JSON string (GitHub Actions secret)
    Or reads from ~/.hermes/profiles/home/google_token.json (local)
"""
import json, os, sys, tempfile

SPREADSHEET_ID = "1zYs5s66J2nyv-LmaZWBL2Tzhu5vicrkOq3nDC5LSFXA"

# Handle token - either from env var (GitHub Actions) or file (local)
token_json = os.environ.get("GOOGLE_TOKEN_JSON")
if token_json:
    # Write token to temp file
    token_file = os.path.join(tempfile.gettempdir(), "google_token.json")
    with open(token_file, "w") as f:
        f.write(token_json)
elif os.path.exists("/Users/simonstimson/.hermes/profiles/home/google_token.json"):
    token_file = "/Users/simonstimson/.hermes/profiles/home/google_token.json"
else:
    print("ERROR: No Google token found", file=sys.stderr)
    sys.exit(1)

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file(token_file)
service = build("sheets", "v4", credentials=creds)

SHEETS = [
    "📅 Calendar",
    "🛒 Shopping List",
    "✅ Chores",
    "🍽️ Meal Plan",
    "📋 School & Activities",
    "💰 Budget",
    "📝 Announcements",
    "👨‍👩‍👧‍👧 Family Members",
    "📞 Important Contacts",
]

output = {}

for name in SHEETS:
    safe_name = "'" + name + "'"
    try:
        data = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{safe_name}!A1:Z100"
        ).execute()
        values = data.get("values", [])
        if values and len(values) > 1:
            headers = values[0]
            rows = []
            for row_idx, row in enumerate(values[1:], start=2):
                row_dict = {"_row": row_idx}
                for i, h in enumerate(headers):
                    row_dict[h] = row[i] if i < len(row) else ""
                rows.append(row_dict)
            output[name] = {"headers": headers, "rows": rows}
        elif values:
            output[name] = {"headers": [], "rows": values}
        else:
            output[name] = {"headers": [], "rows": []}
    except Exception as e:
        output[name] = {"error": str(e)}

# Output
print(json.dumps(output, ensure_ascii=False, indent=2))
