#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_canonical.py — refuse to write to anything but the one real database.

There is exactly one authoritative TH Verify database and it lives on
lighthouse-core at ~/th-verify/data/th_verify.db. Everything else is a snapshot:
useful for generating reports, running audits and testing pipelines, and
catastrophic to write to, because a write to a snapshot is silently discarded the
next time someone refreshes it -- or worse, gets copied back over production.

Reads are unrestricted; snapshots exist to be read. Only mutation is gated.

Why this exists
---------------
The failure has already happened twice in milder forms. A "Week 31" report was
generated from a 16-day-old snapshot and published numbers that disagreed with
production. Labels were nearly applied to a local copy instead of the canonical
database. Neither produced an error at the time -- both looked like success.
A guard that fails loudly is cheaper than a divergence nobody notices.

Usage
-----
    from _canonical import assert_canonical
    assert_canonical(db_path)                 # exits unless this is the real DB
    assert_canonical(db_path, allow=args.force)
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

CANONICAL_HOST = "lighthouse-core"
CANONICAL_PATH = Path("/Users/visarutsankham/th-verify/data/th_verify.db")

# Escape hatch for tests and for deliberate work on a copy. Deliberately an
# environment variable rather than a quiet default: it has to be typed.
OVERRIDE_ENV = "TH_VERIFY_ALLOW_NONCANONICAL"


def is_canonical(db_path: Path | str) -> bool:
    host = socket.gethostname().split(".")[0].lower()
    if not host.startswith(CANONICAL_HOST):
        return False
    try:
        return Path(db_path).resolve() == CANONICAL_PATH.resolve()
    except OSError:
        return False


def assert_canonical(db_path: Path | str, *, allow: bool = False,
                     action: str = "write to") -> None:
    """Stop the process unless this is the authoritative database."""
    if is_canonical(db_path) or allow or os.getenv(OVERRIDE_ENV):
        return
    host = socket.gethostname().split(".")[0]
    sys.exit(
        f"\nREFUSING to {action} a non-canonical database.\n"
        f"  this host : {host}\n"
        f"  this file : {Path(db_path).resolve()}\n"
        f"  canonical : {CANONICAL_HOST}:{CANONICAL_PATH}\n\n"
        f"There is one authoritative database and it lives on {CANONICAL_HOST}.\n"
        f"Writing here would be discarded on the next snapshot refresh, or\n"
        f"copied over production later. Deploy and run it there instead:\n\n"
        f"    rsync -a --exclude .venv --exclude data/ ./ core:~/th-verify/\n"
        f"    ssh core 'cd ~/th-verify && .venv/bin/python <this command>'\n\n"
        f"If you genuinely mean to modify a copy, set {OVERRIDE_ENV}=1.\n")
