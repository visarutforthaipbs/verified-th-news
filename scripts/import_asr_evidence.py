#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_asr_evidence.py — bring the ASR transcripts and quotes into the archive.

The 2026-08-01 run transcribed 1,735 Sure & Share videos and applied 1,332
verdicts, then left its evidence behind on lighthouse-gpu01 in
`~/th-verify-asr/full_results.jsonl`. Only the verdict reached the database.

That is the wrong half to keep. A verdict with no evidence is something a
reviewer must either trust blind or re-derive by watching the video, and
watching is 2-3 minutes against 6,665 clips. The quote is what makes the label
checkable in ten seconds, and the transcript is what makes the failures
diagnosable at all -- reading the 302 non-verdicts is how we learned the
failures were a WINDOW problem (the worker transcribes the last 45 seconds, and
for LIVE episodes and podcasts those seconds are the sign-off) rather than a
prompt problem.

Records are matched on the YouTube video id, which is the `source_id` for this
source, so a re-run with a longer window replaces the evidence in place.
Nothing about the verdict is touched here: this imports evidence only, and a
human label already on the record is never affected by it.

Usage:
    # on the GPU node, or after copying the file across
    python scripts/import_asr_evidence.py --results ~/th-verify-asr/full_results.jsonl
    python scripts/import_asr_evidence.py --results full_results.jsonl --apply
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _canonical import assert_canonical  # noqa: E402


def video_id(row: dict) -> str | None:
    """The YouTube id, which is source_id for sure_share."""
    url = row.get("url") or ""
    q = parse_qs(urlparse(url).query).get("v")
    if q:
        return q[0]
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1] or None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--model", default="faster-whisper large-v3 + qwen2.5:14b v2")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.apply:
        assert_canonical(args.db, action="import ASR evidence into")

    from th_verify.models import utc_now  # noqa: E402

    rows = [json.loads(l) for l in args.results.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{len(rows)} ASR results in {args.results}")

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    ids = {r["source_id"]: r["id"] for r in con.execute(
        "SELECT id, source_id FROM fact_checks WHERE source='sure_share'")}

    pending, missing, empty = [], 0, 0
    stats = Counter()
    for row in rows:
        vid = video_id(row)
        fid = ids.get(vid or "")
        if fid is None:
            missing += 1
            continue
        transcript = (row.get("transcript") or "").strip()
        if not transcript:
            empty += 1        # video unavailable; nothing to show a reviewer
            continue
        stats[row.get("status") or "?"] += 1
        pending.append((fid, transcript, (row.get("quote") or "").strip(),
                        (row.get("raw_verdict") or "").strip(),
                        (row.get("status") or "").strip(), args.model, utc_now()))

    print(f"  matched to a record   : {len(pending)}")
    print(f"  no matching record    : {missing}")
    print(f"  no transcript to store: {empty}")
    for k, v in stats.most_common():
        print(f"    {k:34} {v}")
    if not args.apply:
        print("\ndry run — nothing written.")
        return 0

    with con:
        con.execute("""CREATE TABLE IF NOT EXISTS asr_evidence (
          fact_check_id INTEGER PRIMARY KEY REFERENCES fact_checks(id) ON DELETE CASCADE,
          transcript TEXT NOT NULL DEFAULT '', quote TEXT NOT NULL DEFAULT '',
          raw_verdict TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '',
          model TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""")
        con.executemany(
            "INSERT INTO asr_evidence (fact_check_id, transcript, quote, raw_verdict,"
            " status, model, created_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(fact_check_id) DO UPDATE SET transcript=excluded.transcript,"
            " quote=excluded.quote, raw_verdict=excluded.raw_verdict,"
            " status=excluded.status, model=excluded.model,"
            " created_at=excluded.created_at", pending)
    print(f"\nstored evidence for {len(pending)} records.")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    raise SystemExit(main())
