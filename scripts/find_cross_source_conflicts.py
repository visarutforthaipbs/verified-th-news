#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
find_cross_source_conflicts.py — where two Thai fact-checkers looked at the same
claim and did not agree.

Why this exists
---------------
The archive treats a publisher's verdict as gold. An audit in August 2026 showed
we copy those verdicts faithfully -- 100% match against AFNC's status_label and
AFP's textualRating. But fidelity is not correctness, and the two were being
conflated. On 2026-08-03 AFNC stamped a photo of a senior officer bowing to a
politician ข่าวปลอม, AI-generated, "ยืนยันโดย สำนักงานตำรวจแห่งชาติ". On 2026-08-04
Thai PBS Verify checked the same photo and found it genuine -- เนวิน ชิดชอบ at
ศาลหลักเมืองนครศรีธรรมราช in 2561. Both records sit in the archive. The AFNC one is
in classification_test.jsonl labelled `false` and tagged `native`, so a model
that answered correctly would be scored wrong.

Nothing in the pipeline would ever have surfaced that. claim_clusters uses
trigram Jaccard and the two headlines share too little wording; the recirculation
check runs at 0.95 similarity and this pair sits at 0.925.

What it looks for
-----------------
Pairs of claims from DIFFERENT publishers that are semantically close, then
classifies how the two verdicts relate:

  contradiction  one says false/altered, the other says true. A real dispute.
  degree         false vs misleading. Both think something is wrong, they
                 disagree about how much. Common and usually not newsworthy.
  one_declined   one publisher ruled, the other examined and declined
                 (ไม่สแตมป์ข่าว) or has no verdict yet. This is the category the
                 August case falls into -- Thai PBS declined to stamp its own
                 correction, so a pure label comparison would miss it.

Output is a review list, never an automatic change. Deciding between two
fact-checkers is an editorial act, not a script's job.

Usage:
    python scripts/find_cross_source_conflicts.py --threshold 0.90
    python scripts/find_cross_source_conflicts.py --kind contradiction --limit 40
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

INDEX = Path("data/index")
NEGATIVE = {"false", "altered_media"}
POSITIVE = {"true"}
SOFT = {"misleading"}
NO_RULING = {"unknown"}


def relation(a: str, b: str) -> str | None:
    """How two normalised verdicts relate. None = not interesting."""
    pair = {a, b}
    if a == b:
        return None
    if pair & NEGATIVE and pair & POSITIVE:
        return "contradiction"
    if (pair & NEGATIVE or pair & POSITIVE) and pair & SOFT:
        return "degree"
    if pair & NO_RULING and (pair & NEGATIVE or pair & POSITIVE or pair & SOFT):
        return "one_declined"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threshold", type=float, default=0.90)
    ap.add_argument("--kind", choices=["contradiction", "degree", "one_declined"])
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--out", type=Path, default=Path("data/reports/cross_source_conflicts.json"))
    ap.add_argument("--qa", action="store_true",
                    help="also write the label-QA queue: OUR labels contradicted "
                         "by a publisher's own verdict on the same claim")
    ap.add_argument("--qa-out", type=Path, default=Path("data/reports/label_conflicts.json"))
    ap.add_argument("--qa-threshold", type=float, default=0.94)
    args = ap.parse_args()

    import numpy as np
    vecs = np.load(INDEX / "embeddings.npy")
    meta = [json.loads(l) for l in (INDEX / "meta.jsonl").open(encoding="utf-8")]
    n = len(meta)
    print(f"{n:,} indexed claims, threshold {args.threshold}")

    src = np.array([m["source"] for m in meta])
    found: list[dict] = []
    seen: set[tuple[int, int]] = set()

    # Chunked so the full n x n similarity matrix is never held in memory.
    CH = 512
    for start in range(0, n, CH):
        block = vecs[start:start + CH]
        sims = block @ vecs.T
        for bi in range(block.shape[0]):
            i = start + bi
            row = sims[bi]
            cand = np.where(row >= args.threshold)[0]
            for j in cand:
                j = int(j)
                if j == i or src[i] == src[j]:
                    continue          # same publisher: not a cross-check
                key = (min(i, j), max(i, j))
                if key in seen:
                    continue
                seen.add(key)
                rel = relation(meta[i]["label"], meta[j]["label"])
                if rel is None or (args.kind and rel != args.kind):
                    continue
                found.append({
                    "similarity": round(float(row[j]), 4), "relation": rel,
                    "a": {k: meta[i][k] for k in ("id", "source", "label", "published_at", "claim_text", "url")},
                    "b": {k: meta[j][k] for k in ("id", "source", "label", "published_at", "claim_text", "url")},
                })
        if start % 4096 == 0:
            print(f"  scanned {min(start + CH, n):,}/{n:,} — {len(found)} so far", flush=True)

    found.sort(key=lambda d: -d["similarity"])
    kinds = Counter(f["relation"] for f in found)
    pairs = Counter(tuple(sorted((f["a"]["source"], f["b"]["source"]))) for f in found)

    print(f"\n{len(found)} cross-publisher pairs above {args.threshold}")
    for k, v in kinds.most_common():
        print(f"   {k:14} {v:5}")
    print("\npublisher pairs:")
    for (x, y), v in pairs.most_common(8):
        print(f"   {x:11} x {y:11} {v:5}")

    print(f"\ntop {min(args.limit, len(found))}:")
    for f in found[:args.limit]:
        a, b = f["a"], f["b"]
        print(f"\n  [{f['relation']}] sim {f['similarity']}")
        print(f"    {a['source']:10} {a['published_at'][:10]} [{a['label']:13}] {a['claim_text'][:60]}")
        print(f"    {b['source']:10} {b['published_at'][:10]} [{b['label']:13}] {b['claim_text'][:60]}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"threshold": args.threshold, "counts": dict(kinds), "pairs": found},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwritten: {args.out}")

    if args.qa:
        # The tool's real value is not editorial disputes -- those turned out to
        # be framing artefacts -- but our own errors. A publisher who already
        # ruled on the same claim is free marking for labels nobody could
        # otherwise check.
        import sqlite3
        con = sqlite3.connect("file:data/th_verify.db?mode=ro", uri=True)
        origin = dict(con.execute("SELECT id, verdict_origin FROM fact_checks"))
        OURS = {"llm", "heuristic"}
        qa = []
        for f in found:
            if f["relation"] != "contradiction" or f["similarity"] < args.qa_threshold:
                continue
            a, b = f["a"], f["b"]
            oa, ob = origin.get(a["id"], ""), origin.get(b["id"], "")
            if oa in OURS and ob == "source":
                mine, theirs, morg = a, b, oa
            elif ob in OURS and oa == "source":
                mine, theirs, morg = b, a, ob
            else:
                continue
            qa.append({"similarity": f["similarity"], "our_origin": morg,
                       "ours": mine, "theirs": theirs})
        qa.sort(key=lambda d: -d["similarity"])
        args.qa_out.write_text(json.dumps(qa, ensure_ascii=False, indent=1),
                               encoding="utf-8")
        print(f"label-QA queue: {len(qa)} pairs -> {args.qa_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
