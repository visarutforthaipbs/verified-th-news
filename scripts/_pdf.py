#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_pdf.py — print a finished HTML report to PDF with headless Chrome.

Chrome rather than a Python PDF library: none is installed here, and more
importantly Chrome shapes Thai correctly. Most lightweight PDF writers place
Thai vowels and tone marks wrongly — above the following consonant, or stacked
on top of each other — which is invisible to a non-Thai reader reviewing the
output and obvious to every recipient.

Shared by the report builders so there is one Chrome invocation in the repo,
with one set of flags, to fix when Chrome's headless flags change again.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# The macOS install path. Both report hosts (this MacBook and lighthouse-core)
# are Macs; on a Linux host set CHROME to the binary in the environment.
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
]


def chrome_path() -> str | None:
    import os
    env = os.getenv("CHROME")
    if env and Path(env).exists():
        return env
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    return None


def write_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Render `html_path` to `pdf_path`. Returns False (with a note on stderr)
    rather than raising: a missing Chrome should cost the PDF, not the HTML."""
    chrome = chrome_path()
    if not chrome:
        print("  (PDF skipped: no Chrome/Chromium found — set $CHROME)",
              file=sys.stderr)
        return False
    try:
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri()],
            check=True, capture_output=True, timeout=180)
        return pdf_path.exists()
    except Exception as exc:
        print(f"  (PDF failed: {exc})", file=sys.stderr)
        return False
