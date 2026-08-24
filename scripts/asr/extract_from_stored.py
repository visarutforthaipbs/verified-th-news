#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_from_stored.py — run verdict extraction over transcripts already held.

Why this exists
---------------
asr_worker fetches and extracts in one pass, so improving the model or the
prompt meant re-downloading everything -- and downloading is the rate-limited,
fragile half. That is why the two ASR models could not be compared in August:
the baseline transcripts were six weeks old and half the audio would not come
down again.

This reads asr_evidence.transcript and writes a verdict. It touches YouTube not
at all, so it runs flat out whenever the GPU is awake, and can be re-run as many
times as the prompt changes.

Three populations are eligible, all of which HAVE a transcript but no usable
verdict:

  captions_only                     harvested by harvest_captions.py, never extracted
  unclear                           the model declined, on the old qwen2.5:14b
  rejected_quote_not_in_transcript  the verbatim-quote guard refused the answer

The last two are worth retrying specifically because they were produced by
qwen2.5:14b, which scored 59.0% overall and 32.4% on `misleading` in the
2026-08-17 bake-off. Typhoon-S scored 67.6% and 51.4%. Some of those refusals
are the old model's weakness, not a genuinely unclear episode.

Human labels are never touched: the query excludes them and the write is
guarded again at UPDATE time.

Usage:
    python scripts/asr/extract_from_stored.py --dry-run
    python scripts/asr/extract_from_stored.py --apply
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asr_worker as W  # noqa: E402
from _canonical import assert_canonical  # noqa: E402

OLLAMA = "http://lighthouse-gpu01:11434/api/generate"
MODEL = ("hf.co/mradermacher/typhoon-s-thaillm-8b-instruct-research-preview"
         "-GGUF:Q4_K_M")


def ask(title: str, transcript: str, model: str) -> dict:
    body = {
        "model": model,
        "prompt": W.PROMPT.format(title=title, transcript=transcript),
        "stream": False, "format": "json",
        # think=False is not optional: Typhoon-S is Qwen3-based and Ollama
        # enables reasoning by default, which with format=json returns an EMPTY
        # response on every record. num_predict is 1600 because Typhoon quotes
        # whole passages where Qwen quotes a clause, and a truncated quote makes
        # the JSON unparseable -- both cost a full run to discover in August.
        "think": False,
        "options": {"temperature": 0, "num_predict": 1600},
    }
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(json.loads(r.read())["response"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.apply:
        assert_canonical(args.db, action="write verdicts into")

    from th_verify.models import utc_now  # noqa: E402

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """SELECT f.id, f.title, e.transcript, e.status
           FROM asr_evidence e JOIN fact_checks f ON f.id = e.fact_check_id
           WHERE length(e.transcript) > 40
             AND f.verdict_origin NOT LIKE 'human%'
             AND (f.verdict='unknown' OR f.verdict='')
           ORDER BY f.published_at DESC LIMIT ?""", (args.limit,)).fetchall()
    print(f"{len(rows)} transcripts to extract from ({args.model.split('/')[-1]})\n")

    stats, applied = Counter(), []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        try:
            out = ask(r["title"], r["transcript"], args.model)
        except Exception as exc:
            stats[f"error ({type(exc).__name__})"] += 1
            continue
        verdict = str(out.get("verdict", "")).strip()
        quote = str(out.get("quote", ""))
        if verdict not in W.VALID:
            stats["unclear"] += 1
            continue
        # Same verbatim-quote guard production uses: a quote that does not
        # literally occur in the transcript means the model composed it, and a
        # composed quote cannot be checked by the reviewer it is shown to.
        if W.norm(quote) not in W.norm(r["transcript"]):
            stats["rejected_quote_not_in_transcript"] += 1
            continue
        stats["labelled"] += 1
        applied.append((verdict, quote, r["id"]))
        if i % 25 == 0:
            print(f"  {i}/{len(rows)}  {dict(stats)}", flush=True)

    el = time.time() - t0
    print(f"\n{dict(stats)}   {el/max(len(rows),1):.1f}s/record")
    if not args.apply:
        print("\ndry run — nothing written.")
        return 0

    stamp = utc_now()
    with con:
        for verdict, quote, fid in applied:
            con.execute(
                "UPDATE fact_checks SET verdict=?, verdict_origin='llm', labeled_at=?"
                " WHERE id=? AND verdict_origin NOT LIKE 'human%'",
                (verdict, stamp, fid))
            con.execute(
                "UPDATE asr_evidence SET quote=?, raw_verdict=?, status='labelled',"
                " model=? WHERE fact_check_id=?",
                (quote, verdict, args.model, fid))
    print(f"\napplied {len(applied)} verdicts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
