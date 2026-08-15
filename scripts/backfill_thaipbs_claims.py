#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_thaipbs_claims.py — store the claim Thai PBS states, not the headline.

The archive keeps `title` and `claim` as separate columns, and AFP is the only
source that ever filled them differently: its Google ClaimReview payload carries
the review headline and `claim.text` apart, so we store
"ภาพเยาวชนโพสท่าถ่ายรูป...ถูกสร้างขึ้นด้วยเอไอ" as the title and
"ภาพเยาวชนโพสท่าแด๊บหลังขับรถชนขบวนพระธุดงค์" as the claim.

Every other source copied the headline into both. For Thai PBS that is actively
harmful, because their headlines are written for readers and routinely carry the
conclusion:

    headline       โพสต์อ้างข่าวปลอม ตำรวจยศสูงไหว้นักการเมือง ชี้เป็นภาพ AI
                   ตรวจสอบพบเป็นภาพจริง ปี 61
    claimReviewed  ตำรวจยศสูงไหว้นักการเมือง

Stored as the claim, the first version leaks the answer into training data and
shows a reviewer a summary where a claim should be. Thai PBS publishes the second
in ClaimReview.claimReviewed; we simply never read it.

Only `claim` is rewritten. `title` keeps the headline -- it is what the publisher
called the article and the review room still shows it as context.

Usage:
    python scripts/backfill_thaipbs_claims.py            # dry run
    python scripts/backfill_thaipbs_claims.py --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from th_verify.collectors.thaipbs import parse_claim_reviewed  # noqa: E402
from _canonical import assert_canonical  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--delay", type=float, default=0.35)
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()
    if args.apply:
        assert_canonical(args.db, action="rewrite claims in")

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, source_id, source_url, title, claim FROM fact_checks "
        "WHERE source='thaipbs' ORDER BY source_id").fetchall()
    if args.limit:
        rows = rows[: args.limit]
    print(f"{len(rows)} Thai PBS records\n")

    changes, unchanged, failed = [], 0, 0
    with httpx.Client(timeout=30, follow_redirects=True,
                      headers={"user-agent": "Mozilla/5.0"}) as cl:
        for i, r in enumerate(rows, 1):
            try:
                claim = parse_claim_reviewed(HTMLParser(cl.get(r["source_url"]).text))
            except Exception as exc:
                failed += 1
                print(f"  {r['source_id']:>6} FAILED {exc}")
                time.sleep(args.delay)
                continue
            if not claim or claim == r["claim"]:
                unchanged += 1
            else:
                changes.append((claim, r["id"]))
                saved = len(r["claim"]) - len(claim)
                print(f"  {r['source_id']:>6} -{saved:4} chars")
                print(f"         was: {r['claim'][:72]}")
                print(f"         now: {claim[:72]}")
            if i % 50 == 0:
                print(f"    …{i}/{len(rows)}  ({len(changes)} improved)", flush=True)
            time.sleep(args.delay)

    print(f"\nimproved  : {len(changes)}")
    print(f"unchanged : {unchanged}   (headline already claim-shaped)")
    print(f"failed    : {failed}")
    if not args.apply:
        print("\ndry run — nothing written. Re-run with --apply.")
        return 0
    with con:
        for claim, rid in changes:
            con.execute("UPDATE fact_checks SET claim=? WHERE id=?", (claim, rid))
    print(f"\napplied {len(changes)} claim rewrites. Rebuild exports and the index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
