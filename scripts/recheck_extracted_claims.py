#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recheck_extracted_claims.py — re-judge claims the model already wrote.

The guards in extract_claims.py decide what enters the archive, and they were
wrong twice: the overlap test counted whitespace tokens, which is meaningless in
Thai, and the verdict list missed Thai PBS's พบเป็น construction. 916 claims were
written before either was fixed.

Rather than trust that the earlier run was fine, this replays the CURRENT guards
over every claim carrying claim_origin='llm' and reverts the ones that no longer
pass. Reverting means restoring `claim = title` and `claim_origin = ''`, which is
exactly the state an unextracted record is in -- so a reverted row is simply a
candidate again, and the next extraction pass will retry it with better rules.

Human-edited claims are never touched: claim_origin='human' is excluded, and so
is 'source', which is the publisher's own claimReviewed.

Usage:
    python scripts/recheck_extracted_claims.py            # dry run
    python scripts/recheck_extracted_claims.py --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_claims import judge  # noqa: E402
from _canonical import assert_canonical  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--show", type=int, default=12)
    args = ap.parse_args()
    if args.apply:
        assert_canonical(args.db, action="revert extracted claims in")

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, source, title, claim, explanation FROM fact_checks "
        "WHERE claim_origin = 'llm'").fetchall()
    print(f"{len(rows)} extracted claims to re-judge\n")

    bad, why = [], Counter()
    for r in rows:
        reason = judge(r["claim"], r["title"], r["explanation"] or "")
        if reason:
            bad.append((r["id"], r["title"], r["claim"], reason))
            why[reason] += 1

    for rid, title, claim, reason in bad[: args.show]:
        print(f"  [{rid}] {reason}")
        print(f"    หัวข้อ : {title[:80]}")
        print(f"    claim : {claim[:80]}\n")

    print(f"still good : {len(rows) - len(bad)}")
    print(f"to revert  : {len(bad)}")
    for k, v in why.most_common():
        print(f"  {k:26} {v}")
    if not args.apply:
        print("\ndry run — nothing written.")
        return 0
    with con:
        for rid, *_ in bad:
            con.execute(
                "UPDATE fact_checks SET claim = title, claim_origin = '' "
                "WHERE id = ? AND claim_origin = 'llm'", (rid,))
    print(f"\nreverted {len(bad)} to unextracted; they are candidates again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
