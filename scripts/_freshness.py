"""Guard against building client-facing reports from a stale database snapshot.

Why this exists
---------------
Reports are generated on whichever machine the analyst happens to be sitting at,
but the canonical database lives on lighthouse-core and only that copy is synced
nightly. On 2026-07-31 a report titled "Week 31 (Ending July 31, 2026)" was found
to have been built on the MacBook dev copy, whose last sync was 2026-07-15 — the
title claimed the current week while the numbers were sixteen days old. Nothing
in the pipeline objected.

The failure is silent and the output looks perfectly plausible, which is exactly
what makes it dangerous for anything that reaches a client. So report builders
call `assert_fresh()` and get a loud warning, or a hard stop, when the snapshot
they are about to summarise is older than they think.

Usage
-----
    from _freshness import assert_fresh
    assert_fresh(conn)                      # warn if > 2 days old
    assert_fresh(conn, max_age_days=1, strict=True)   # refuse instead
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone

DEFAULT_MAX_AGE_DAYS = 2


class StaleDatabaseError(RuntimeError):
    """The database snapshot is older than the report is willing to claim."""


def snapshot_age(conn: sqlite3.Connection) -> tuple[datetime | None, timedelta | None]:
    """Return (last ingest time, age). Both None when the table is empty."""
    row = conn.execute("SELECT MAX(first_seen_at) FROM fact_checks").fetchone()
    raw = row[0] if row else None
    if not raw:
        return None, None
    text = str(raw).replace("Z", "+00:00")
    try:
        last = datetime.fromisoformat(text)
    except ValueError:
        return None, None
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return last, datetime.now(timezone.utc) - last


def assert_fresh(
    conn: sqlite3.Connection,
    *,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    strict: bool = False,
    stream=sys.stderr,
) -> timedelta | None:
    """Warn (or raise, when strict) if the newest record is too old.

    Returns the snapshot age so callers can stamp it into their output.
    """
    last, age = snapshot_age(conn)
    if age is None:
        message = "database has no ingest timestamps - cannot verify freshness"
    elif age <= timedelta(days=max_age_days):
        return age
    else:
        message = (
            f"database snapshot is {age.days} days old "
            f"(newest record ingested {last:%Y-%m-%d %H:%M UTC}).\n"
            f"    The canonical copy lives on lighthouse-core and syncs nightly at 03:30.\n"
            f"    Build there, or refresh this copy first:\n"
            f"      rsync -a core:~/th-verify/data/ ./data/"
        )

    banner = "!" * 72
    print(f"\n{banner}\n  STALE DATA: {message}\n{banner}\n", file=stream)
    if strict:
        raise StaleDatabaseError(message)
    return age
