#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backfill_thaipbs_unstamped.py — store the verdict Thai PBS actually published
for records still carrying the placeholder 'unknown'.

Why these were missed
---------------------
The 2026-07-31 repair skipped changes whose *normalised* meaning did not move,
to avoid churn. 'unknown' -> 'ไม่สแตมป์ข่าว' both normalise to unknown, so it
looked cosmetic. It was not: ไม่สแตมป์ข่าว is Thai PBS stating that they examined
the item and decline to stamp it, and discarding that left the archive unable to
tell "we never got a verdict" apart from "the publisher declined to give one".

These records predate the ClaimReview-reading collector and delta syncs never
revisit old listing pages, so nothing else would ever have corrected them.

Scope is deliberately narrow: only rows whose stored verdict is empty or
'unknown'. Nothing with a real verdict is touched.
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
from th_verify.collectors.thaipbs import parse_claim_review  # noqa: E402
from _canonical import assert_canonical  # noqa: E402

SQL = ("SELECT source_id, source_url, title, verdict FROM fact_checks "
       "WHERE source='thaipbs' AND verdict IN ('unknown', '') "
       "AND verdict_origin NOT LIKE 'human%'")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.apply:
        assert_canonical(args.db, action="backfill verdicts in")

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(SQL).fetchall()
    print(f"{len(rows)} records with a placeholder verdict\n")

    updates, failed = [], 0
    with httpx.Client(timeout=30, follow_redirects=True,
                      headers={"user-agent": "Mozilla/5.0"}) as cl:
        for r in rows:
            try:
                v, _ = parse_claim_review(HTMLParser(cl.get(r["source_url"]).text))
            except Exception as exc:
                print(f"  {r['source_id']:>6}  FAILED: {exc}")
                failed += 1
                continue
            if not v:
                print(f"  {r['source_id']:>6}  no ClaimReview — left alone")
                continue
            updates.append((v, r["source_id"]))
            print(f"  {r['source_id']:>6}  {r['verdict']!r} -> {v!r}   {r['title'][:44]}")
            time.sleep(0.4)

    print(f"\n{len(updates)} to update, {failed} failed")
    if not args.apply:
        print("dry run — nothing written. Re-run with --apply.")
        return 0
    with con:
        for verdict, sid in updates:
            # verdict_origin stays 'source': this IS the publisher's own value,
            # just one we failed to record the first time.
            con.execute("UPDATE fact_checks SET verdict=?, verdict_origin='source' "
                        "WHERE source='thaipbs' AND source_id=? "
                        "AND verdict_origin NOT LIKE 'human%'", (verdict, sid))
    print(f"applied {len(updates)} updates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
