#!/bin/bash
# Resume the ASR batch run after a reboot. Wired to @reboot in crontab.
#
# The GPU box restarted on its own mid-run on 2026-08-17, which stopped
# everything silently -- no error, just a cold card and a stalled job. Resuming
# is safe because asr_worker skips records already in the output file and
# AUDIO_CACHE means nothing is re-downloaded, so at worst this repeats the
# handful of records that were in flight.
#
# Two refusals, both deliberate. A duplicate scheduler is exactly what was
# removed from lighthouse-core's crontab the day before this was written --
# launchd and cron were both firing daily_sync at 03:30, and two processes were
# writing the exports and the search index at once. So:
#
#   * if a batch runner is already alive, do nothing;
#   * if the queue is finished, do nothing.
#
# Neither condition is trusted from a flag file. Both are read from the system.
cd "$(dirname "$0")" || exit 0

if ps -eo command | awk '/run_batches\.sh/ && !/awk/' | grep -q .; then
  echo "$(date -Is) already running, not starting a second copy" >> resume.log
  exit 0
fi

TOTAL=$(wc -l < standard_all.jsonl 2>/dev/null || echo 0)
DONE=$(wc -l < standard_results.jsonl 2>/dev/null || echo 0)
if [ "$TOTAL" -eq 0 ] || [ "$DONE" -ge "$TOTAL" ]; then
  echo "$(date -Is) nothing left to do ($DONE/$TOTAL)" >> resume.log
  exit 0
fi

# Ollama needs a moment after boot before it will answer.
sleep 60

if ! ps -eo command | awk '/thermal_guard\.sh/ && !/awk/' | grep -q .; then
  setsid bash -c 'nohup ./thermal_guard.sh >> guard.out 2>&1 &'
fi
setsid bash -c 'nohup ./run_batches.sh >> batches.log 2>&1 &'
echo "$(date -Is) resumed at $DONE/$TOTAL" >> resume.log
