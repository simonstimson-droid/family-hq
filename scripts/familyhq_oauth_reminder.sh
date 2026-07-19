#!/bin/bash
# Family HQ — Google OAuth Re-auth Reminder
#
# Runs on a schedule (cron job 978fa36e7b8c). Self-contained: it checks
# whether the Google token (Sheets/Gmail/Calendar) can still refresh.
#   - If valid          -> prints a quiet "all good" line (no nag).
#   - If expired/revoked -> prints the consent URL + exact steps so Simon
#     can re-auth straight from the cron's Telegram message.
#
# After clicking the link and getting the code, Simon replies with the code
# (or runs:  python3 scripts/reauth_gmail.py exchange <CODE>) and the
# token is refreshed with all required scopes.

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN="$HOME/.hermes/profiles/home/google_token.json"

echo "🔐 Family HQ — Google token check ($(date '+%d %b %H:%M'))"

if [ ! -f "$TOKEN" ]; then
  echo "❌ No token file at $TOKEN — run: python3 $SCRIPT_DIR/reauth_gmail.py url"
  exit 0
fi

# Decide valid vs needs-reauth, and refresh the access token if possible.
NEED_REAUTH=$(python3 - "$TOKEN" <<'PY' 2>/dev/null
import json, sys, urllib.request, urllib.parse
tok_path = sys.argv[1]
try:
    t = json.load(open(tok_path))
except Exception:
    print("YES"); raise SystemExit
data = urllib.parse.urlencode({
    'client_id': t.get('client_id',''),
    'client_secret': t.get('client_secret',''),
    'refresh_token': t.get('refresh_token',''),
    'grant_type': 'refresh_token',
}).encode()
req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
try:
    r = json.load(urllib.request.urlopen(req, timeout=30))
    if 'access_token' in r:
        t['access_token'] = r['access_token']
        t['token'] = r['access_token']
        json.dump(t, open(tok_path,'w'), indent=2)
        print("NO")   # valid
    else:
        print("YES")
except Exception:
    print("YES")   # any failure => treat as expired
PY
)

if [ "$NEED_REAUTH" = "YES" ]; then
  echo ""
  echo "⚠️ **Google token expired/revoked** — Family HQ syncs (email, sheets, calendar) are failing."
  echo ""
  echo "👉 To re-auth, open this link (signed into stimsonfamilyhq@gmail.com):"
  echo ""
  python3 "$SCRIPT_DIR/reauth_gmail.py" url
  echo ""
  echo "Then either:"
  echo "  1) reply to me with just the AUTHORIZATION CODE, or"
  echo "  2) run:  python3 $SCRIPT_DIR/reauth_gmail.py exchange <CODE>"
  echo ""
  echo "Scopes refreshed: calendar + sheets + gmail.readonly + gmail.modify."
else
  echo "✅ Token still valid — no action needed. (Access token refreshed.)"
fi
