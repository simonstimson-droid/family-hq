import json
from datetime import datetime, timezone

with open('/Users/simonstimson/.hermes/profiles/home/google_token.json') as f:
    tok = json.load(f)

expiry_str = tok.get('expiry', '')
print(f'Token expiry: {expiry_str}')

if expiry_str:
    try:
        exp_dt = datetime.fromisoformat(expiry_str)
        now = datetime.now(timezone.utc)
        print(f'Expired? {exp_dt <= now}')
    except Exception as e:
        print(f'Error parsing expiry: {e}')

print(f'Token: {tok.get("access_token", "")[:20]}...')
print(f'Refresh token: {tok.get("refresh_token", "")[:20]}...')