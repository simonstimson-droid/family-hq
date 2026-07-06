#!/bin/bash
# Family HQ summary wrapper for no_agent cron jobs.
# Runs smart_reminders.py with the given flag and prints ONLY the message
# between the ==== separator lines (status/progress lines go to stderr/dropped).
# Usage: summary_for_cron.sh --weekend | --week-ahead | --month-ahead
# Exits 0 with the message on stdout, or non-zero (silent) on failure so the
# cron watchdog surfaces an error alert.

set -euo pipefail
FLAG="${1:---weekend}"
cd /Users/simonstimson/FamilyHQ

# Capture stdout only; progress lines print before the first ==== separator.
OUT="$(python3 scripts/smart_reminders.py "$FLAG" 2>/dev/null)" || exit 1

# Extract text strictly between the first and last ==== separator lines.
MSG="$(printf '%s\n' "$OUT" | awk '
  /^={10,}/ { c++; next }
  c==1 { print }
')"

# If nothing was captured, fail loudly (non-zero) so the watchdog alerts.
if [ -z "${MSG//[[:space:]]/}" ]; then
  exit 1
fi

printf '%s\n' "$MSG"
