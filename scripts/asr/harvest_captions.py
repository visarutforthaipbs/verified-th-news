#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
harvest_captions.py — collect Thai captions into asr_evidence, paced.

Why this is separate from asr_worker
------------------------------------
asr_worker does the whole job in one pass: fetch, transcribe, extract a verdict.
That couples the two halves, and they have opposite constraints.

  fetching    needs the network, is rate-limited by YouTube, needs NO GPU
  extracting  needs the GPU, is not rate-limited, needs NO network

On 2026-08-17 a flat-out run made ~1,858 downloads plus ~160 caption fetches in
a day and YouTube throttled the household IP for two days -- captions included,
which had been assumed exempt. Splitting them means the network half can run
slowly in the background on any machine while the GPU is asleep, and the GPU
half can later re-run over stored transcripts without touching YouTube at all.

Pacing, measured not guessed. The first version assumed the limit was daily and
tried 300 records at 3s apart; YouTube throttled it at record 27. The real
constraint is PER BURST -- roughly 30 caption fetches in close succession,
largely regardless of the gap between them. Meanwhile the hourly probe has read
CLEAR 116 times running, so recovery takes well under an hour.

So the shape is small-batch-hourly, not one big daily run: --batch of 20 (safely
under the observed ~30) driven by cron every hour gives ~480/day and clears the
~4,800 backlog in about ten days. On a 429 it stops immediately rather than
pushing through -- the block gets longer, not shorter, if you keep knocking.

Stores the transcript with an empty quote/verdict. The verdict extraction is a
separate pass (asr_worker with USE_CAPTIONS reading these, or bench-validated
prompt work), so a reviewer never sees a proposal nobody generated.

Usage:
    python scripts/asr/harvest_captions.py --dry-run
    python scripts/asr/harvest_captions.py --batch 20     # one hourly slice
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import asr_worker as W  # noqa: E402
from _canonical import assert_canonical  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--batch", type=int, default=20, dest="per_day",
                    help="records per run; keep under ~30, the observed burst "
                         "limit. Designed to be run hourly by cron.")
    ap.add_argument("--delay", type=float, default=3.0,
                    help="seconds between records")
    ap.add_argument("--since", default="2022",
                    help="only records published on/after this; captions are "
                         "reliable from 2022 and patchy before (2018: 0/7)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.dry_run:
        assert_canonical(args.db, action="store captions in")

    from th_verify.models import utc_now  # noqa: E402

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT f.id, f.source_url, f.title FROM fact_checks f
           WHERE f.source='sure_share'
             AND f.verdict_origin NOT LIKE 'human%'
             AND (f.verdict='unknown' OR f.verdict='')
             AND f.published_at >= ?
             AND NOT EXISTS (SELECT 1 FROM asr_evidence e
                             WHERE e.fact_check_id = f.id
                               AND length(e.transcript) > 0)
           ORDER BY f.published_at DESC LIMIT ?""",
        (args.since, args.per_day)).fetchall()

    print(f"{len(rows)} records to harvest (paced: {args.delay}s apart)")
    if args.dry_run:
        for r in rows[:5]:
            print(f"  {r['id']}  {r['title'][:70]}")
        print("\ndry run — nothing fetched or written.")
        return 0

    got = none = 0
    stamp = utc_now()
    for i, r in enumerate(rows, 1):
        try:
            text = W.fetch_tail_captions(r["source_url"], 45)
        except W.CaptionsRateLimited:
            # Stop, do not push through. The block lengthens if you keep asking.
            print(f"\nrate limited at record {i} — stopping cleanly. "
                  f"{got} stored this run; the next hourly run continues.", flush=True)
            break
        if text:
            with con:
                con.execute(
                    "INSERT INTO asr_evidence (fact_check_id, transcript, quote,"
                    " raw_verdict, status, model, created_at)"
                    " VALUES (?,?,'','','captions_only','youtube-captions',?)"
                    " ON CONFLICT(fact_check_id) DO UPDATE SET"
                    " transcript=excluded.transcript, status=excluded.status,"
                    " model=excluded.model, created_at=excluded.created_at",
                    (r["id"], text, stamp))
            got += 1
        else:
            none += 1
        if i % 25 == 0:
            print(f"  {i}/{len(rows)}  stored={got} no-captions={none}", flush=True)
        time.sleep(args.delay)

    print(f"\nstored {got} transcripts, {none} had no Thai captions.")
    print("Verdict extraction is a separate pass and needs the GPU node.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
