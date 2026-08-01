#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_fonts.py — regenerate assets/brand/fnl-fonts.css with embedded webfonts.

Kanit and Prompt (Cadson Demak, SIL Open Font License 1.1) are the brand faces:
loopless Thai/Latin moderns. Kanit's squarish geometry matches the heading spec
in the identity guide; Prompt is the lighter companion for body copy.

Why the fonts are base64-embedded rather than linked
----------------------------------------------------
* **No CDN.** Loading them from fonts.gstatic.com would leak every visitor's IP
  to Google. This is a fact-checking service that promises not to log queries, so
  a third-party font request would quietly undermine that promise.
* **No static route exists.** api.py serves its two pages with individual
  FileResponse calls; there is no mounted static directory to put font files in.
* **Reports must survive being moved.** The weekly report is a standalone HTML
  file that also gets printed to PDF from a `file://` URL and emailed around.
  A relative font path would break the moment the file left data/reports/.

Only the `latin` and `thai` subsets are kept -- latin-ext and vietnamese are
dropped, roughly halving the payload for a Thai-language service. Each face keeps
Google's own `unicode-range`, so a browser downloads nothing it cannot use.

Usage:
    python scripts/brand/fetch_fonts.py            # regenerate
    python scripts/brand/fetch_fonts.py --check    # verify without writing
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "brand" / "fnl-fonts.css"

GF_URL = ("https://fonts.googleapis.com/css2"
          "?family=Kanit:wght@500;600;700"
          "&family=Prompt:wght@400;500;600"
          "&display=swap")
# A modern UA is required or Google returns legacy TTF instead of woff2.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
KEEP_SUBSETS = {"latin", "thai"}

FACE_RE = re.compile(
    r"/\*\s*(?P<subset>[a-z-]+)\s*\*/\s*@font-face\s*\{(?P<body>[^}]+)\}", re.S)
PROP_RE = {
    "family": re.compile(r"font-family:\s*'([^']+)'"),
    "style": re.compile(r"font-style:\s*(\w+)"),
    "weight": re.compile(r"font-weight:\s*(\d+)"),
    "url": re.compile(r"url\((https://[^)]+\.woff2)\)"),
    "range": re.compile(r"unicode-range:\s*([^;]+);"),
}


def fetch(url: str, ua: bool = False) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA} if ua else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report what would be built without writing")
    args = ap.parse_args()

    css = fetch(GF_URL, ua=True).decode("utf-8")
    faces = []
    for m in FACE_RE.finditer(css):
        subset, body = m.group("subset"), m.group("body")
        if subset not in KEEP_SUBSETS:
            continue
        got = {k: rx.search(body) for k, rx in PROP_RE.items()}
        if not all(got.values()):
            print(f"  skipped a malformed face in subset {subset}", file=sys.stderr)
            continue
        faces.append({k: v.group(1) for k, v in got.items()} | {"subset": subset})

    if not faces:
        print("no usable faces parsed — Google may have changed its CSS format",
              file=sys.stderr)
        return 1

    out = [
        "/* Fake News Lab — brand webfonts.",
        " * Kanit + Prompt by Cadson Demak, SIL Open Font License 1.1.",
        " * GENERATED FILE — do not hand-edit; run scripts/brand/fetch_fonts.py.",
        " * Embedded rather than linked so no visitor request reaches a third",
        " * party and so standalone report files keep their typography when moved.",
        " */", ""]
    total = 0
    for f in sorted(faces, key=lambda x: (x["family"], int(x["weight"]), x["subset"])):
        data = fetch(f["url"])
        total += len(data)
        b64 = base64.b64encode(data).decode("ascii")
        out += [
            f"/* {f['family']} {f['weight']} — {f['subset']} */",
            "@font-face {",
            f"  font-family: '{f['family']}';",
            f"  font-style: {f['style']};",
            f"  font-weight: {f['weight']};",
            "  font-display: swap;",
            f"  src: url(data:font/woff2;base64,{b64}) format('woff2');",
            f"  unicode-range: {f['range']};",
            "}", ""]
        print(f"  {f['family']:8} {f['weight']}  {f['subset']:6} {len(data)/1024:6.1f} KB")

    print(f"\n{len(faces)} faces, {total/1024:.0f} KB raw "
          f"-> ~{total*4/3/1024:.0f} KB base64")
    if args.check:
        print("--check: nothing written")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
