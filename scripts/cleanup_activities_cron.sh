#!/bin/bash
# Family HQ — weekly activity-list cleanup wrapper for no_agent cron.
# Runs cleanup_activities.py --commit. Prints a short summary ONLY if rows
# were actually deleted; prints nothing on a clean run so the watchdog stays
# quiet. Exits 0 either way (deletion is best-effort housekeeping, not a
# failure worth alerting on).
set -euo pipefail
cd /Users/simonstimson/FamilyHQ

OUT="$(python3 scripts/cleanup_activities.py --commit 2>/dev/null)" || true

# If it deleted something, the output contains "Deleted N row(s)".
if printf '%s' "$OUT" | grep -q "Deleted"; then
  printf '🧹 Activity list cleanup\n\n%s\n' "$OUT"
fi
