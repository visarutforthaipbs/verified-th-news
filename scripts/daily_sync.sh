#!/bin/zsh
# Nightly refresh: pull source deltas, rebuild dataset exports + search index.
# Run by launchd (com.thverify.daily-sync); logs to data/logs/.
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$PROJECT/.venv/bin/python"
LOG_DIR="$PROJECT/data/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily_sync_$(date +%Y%m%d).log"

cd "$PROJECT"
if [ -f .env ]; then set -a; source .env; set +a; fi
{
  echo "=== daily sync started $(date -u +%FT%TZ) ==="
  "$PY" -m th_verify.cli sync all --mode delta
  echo "--- rebuilding dataset exports ---"
  "$PY" scripts/build_dataset.py
  echo "--- rebuilding search index ---"
  "$PY" -m th_verify.cli index
  echo "--- auditing collectors ---"
  # Never fatal: a failed audit must not stop tomorrow's sync from running, and
  # `set -e` would do exactly that. The verdict is written for the review room
  # to surface -- a health check that only reaches a log file nobody opens is
  # worth as much as no health check.
  "$PY" scripts/audit_collectors.py --json data/reports/collector_health.json || true
  echo "=== done $(date -u +%FT%TZ) ==="
} >>"$LOG" 2>&1

# keep the last 14 logs
ls -t "$LOG_DIR"/daily_sync_*.log 2>/dev/null | tail -n +15 | xargs rm -f --
