#!/usr/bin/env python3
"""
DbCaretaker — Daily monitor for the th-verify production server.

Connects to the production server via SSH (host alias from ~/.ssh/config),
checks the launchd daily-sync cron job status, reads the latest sync log,
and queries the verify database for news records added in the last 24 hours.

Saves a Markdown report to:
    ~/teamwork_projects/lighthouse_monitor/report_YYYYMMDD.md

Usage:
    python scripts/daily_monitor.py [--host <ssh-host>] [--output-dir <path>]

Defaults:
    --host       lighthouse-core (updated default)
    --output-dir ~/teamwork_projects/lighthouse_monitor
"""

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path


# ── SSH helpers ──────────────────────────────────────────────────────────────

def ssh(host: str, cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a command on the remote host via SSH. Returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


# ── Cron / launchd checks ────────────────────────────────────────────────────

LAUNCHD_LABEL = "com.thverify.daily-sync"
LOG_GLOB = "~/th-verify/data/logs/daily_sync_*.log"


def check_launchd(host: str) -> dict:
    """Return launchd service info for the daily-sync job."""
    # Try print system/label first since it is a LaunchDaemon
    rc, out, err = ssh(host, f"launchctl print system/{LAUNCHD_LABEL} 2>&1")
    if rc == 0 and "last exit code" in out:
        info = {"found": True, "pid": None, "last_exit_code": None, "raw": out}
        for line in out.splitlines():
            line = line.strip()
            if "last exit code = " in line:
                try:
                    info["last_exit_code"] = int(line.split("=")[1].strip())
                except (IndexError, ValueError):
                    pass
            if "pid = " in line:
                try:
                    info["pid"] = int(line.split("=")[1].strip())
                except (IndexError, ValueError):
                    pass
        return info

    rc, out, err = ssh(host, f"launchctl list {LAUNCHD_LABEL} 2>&1")
    if rc != 0 or "Could not find service" in out or "Could not find service" in err:
        return {"found": False, "pid": None, "last_exit_code": None, "raw": out or err}

    info: dict = {"found": True, "pid": None, "last_exit_code": None, "raw": out}
    for line in out.splitlines():
        line = line.strip().strip("{}")
        if '"PID"' in line:
            try:
                info["pid"] = int(line.split("=")[1].strip().rstrip(";"))
            except (IndexError, ValueError):
                pass
        if '"LastExitStatus"' in line:
            try:
                info["last_exit_code"] = int(line.split("=")[1].strip().rstrip(";"))
            except (IndexError, ValueError):
                pass
    return info


def get_latest_log(host: str) -> dict:
    """Retrieve the filename and tail of the most-recent daily_sync log."""
    rc, filename, _ = ssh(host, f"ls -t {LOG_GLOB} 2>/dev/null | head -1")
    if rc != 0 or not filename:
        return {"filename": None, "tail": None}
    rc2, tail, _ = ssh(host, f"tail -30 {filename}")
    return {"filename": filename, "tail": tail if rc2 == 0 else None}


# ── Database query ────────────────────────────────────────────────────────────

DB_PATH = "~/th-verify/data/th_verify.db"

_SQL_TOTAL = "SELECT COUNT(*) FROM fact_checks;"
_SQL_NEW24H = (
    "SELECT COUNT(*), "
    "SUM(CASE WHEN verdict != 'unknown' THEN 1 ELSE 0 END), "
    "SUM(CASE WHEN verdict = 'unknown' THEN 1 ELSE 0 END) "
    "FROM fact_checks WHERE first_seen_at >= datetime('now', '-24 hours');"
)
_SQL_BY_SRC = (
    "SELECT source, COUNT(*) FROM fact_checks "
    "WHERE first_seen_at >= datetime('now', '-24 hours') "
    "GROUP BY source ORDER BY COUNT(*) DESC;"
)


def query_db(host: str, sql: str) -> tuple[int, str]:
    cmd = f'sqlite3 {DB_PATH} "{sql}"'
    rc, out, _ = ssh(host, cmd)
    return rc, out


def get_db_stats(host: str) -> dict:
    stats: dict = {
        "db_reachable": False,
        "total_records": None,
        "new_24h": None,
        "labeled_new": None,
        "unknown_new": None,
        "by_source": [],
    }

    rc, out = query_db(host, _SQL_TOTAL)
    if rc != 0:
        return stats
    try:
        stats["total_records"] = int(out.strip())
        stats["db_reachable"] = True
    except ValueError:
        return stats

    rc, out = query_db(host, _SQL_NEW24H)
    if rc == 0 and out:
        parts = out.strip().split("|")
        if len(parts) >= 3:
            try:
                stats["new_24h"] = int(parts[0])
                stats["labeled_new"] = int(parts[1]) if parts[1] else 0
                stats["unknown_new"] = int(parts[2]) if parts[2] else 0
            except ValueError:
                pass

    rc, out = query_db(host, _SQL_BY_SRC)
    if rc == 0 and out:
        for line in out.strip().splitlines():
            parts = line.split("|")
            if len(parts) == 2:
                try:
                    stats["by_source"].append({"source": parts[0], "count": int(parts[1])})
                except ValueError:
                    pass

    return stats


# ── Report rendering ──────────────────────────────────────────────────────────

def render_report(host: str, launchd: dict, log: dict, db: dict) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Cron status
    if not launchd["found"]:
        cron_icon = "❌"
        cron_status = "MISSING — launchd service not found or not loaded"
    else:
        pid = launchd["pid"]
        exit_code = launchd["last_exit_code"]
        running = f"Running (PID {pid})" if pid else "Idle (not currently running)"
        run_icon = "🟢" if pid else "⚪"
        if exit_code == 0:
            last_run = "Last exit: success (0) ✅"
        elif exit_code is None:
            last_run = "No exit recorded yet ⚪"
        else:
            last_run = f"Last exit: code {exit_code} ⚠️"
        cron_icon = "🟢" if exit_code in (0, None) else "⚠️"
        cron_status = f"{run_icon} {running} | {last_run}"

    cron_detail = launchd.get("raw") or "(no output)"

    # Log section
    if log["filename"]:
        log_section = (
            f"**Latest log:** `{log['filename']}`\n\n"
            f"```\n{log['tail'] or '(empty)'}\n```"
        )
    else:
        log_section = "_No log files found._"

    # DB section
    if not db["db_reachable"]:
        db_section = "❌ Could not connect to the database."
    else:
        new = db["new_24h"] if db["new_24h"] is not None else "?"
        labeled = db["labeled_new"] if db["labeled_new"] is not None else "?"
        unknown = db["unknown_new"] if db["unknown_new"] is not None else "?"
        total = db["total_records"] if db["total_records"] is not None else "?"

        src_rows = "".join(
            f"| {r['source']} | {r['count']} |\n" for r in db["by_source"]
        ) or "| — | 0 |\n"

        db_section = (
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| **New articles (last 24 h)** | **{new}** |\n"
            f"| ↳ Labeled | {labeled} |\n"
            f"| ↳ Unknown verdict | {unknown} |\n"
            f"| Total records in DB | {total:,} |\n"
            f"\n**Breakdown by source (last 24 h):**\n\n"
            f"| Source | New records |\n"
            f"|--------|-------------|\n"
            f"{src_rows}"
        )

    return f"""# 📋 DbCaretaker Daily Report — {date_str}

> Generated: {now}
> Host: `{host}` | Service: `{LAUNCHD_LABEL}`

---

## {cron_icon} Cron Job Status

**{cron_status}**

<details>
<summary>launchd raw output</summary>

```
{cron_detail}
```

</details>

---

## 📰 Verify Database — New Articles (Last 24 h)

{db_section}

---

## 📄 Latest Sync Log

{log_section}
"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="DbCaretaker: daily monitor for the th-verify production server."
    )
    ap.add_argument(
        "--host", default="lighthouse-core",
        help="SSH host alias from ~/.ssh/config (default: lighthouse-core)"
    )
    ap.add_argument(
        "--output-dir",
        default=str(Path.home() / "teamwork_projects" / "lighthouse_monitor"),
        help="Directory to save the report (default: ~/teamwork_projects/lighthouse_monitor)",
    )
    args = ap.parse_args()

    host = args.host
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    report_path = output_dir / f"report_{date_str}.md"

    print(f"-> Connecting to {host}...")
    print("  Checking launchd service...")
    launchd = check_launchd(host)

    print("  Reading latest sync log...")
    log = get_latest_log(host)

    print("  Querying verify database...")
    db = get_db_stats(host)

    print("  Rendering report...")
    report = render_report(host, launchd, log, db)

    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport saved -> {report_path}\n")
    print(report)


if __name__ == "__main__":
    main()
