#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asr_pipeline.py — orchestrates the Sure & Share transcription labelling pipeline.

Runs where the database is. The GPU work happens in `asr_worker.py` on
lighthouse-gpu01; this script prepares its input, scores its output against
human labels, and applies accepted results.

Subcommands
-----------
    prepare   build a task list (JSONL) for the worker
    validate  score worker output against human labels -- run this BEFORE apply
    apply     write accepted labels into the database as verdict_origin='llm'

The validate step is not optional courtesy. There are 115 human-labelled
sure_share episodes, which is a ready-made answer key; nothing should be written
across ~7,000 episodes until the pipeline has been measured against it.

Typical run
-----------
    python scripts/asr/asr_pipeline.py prepare --validation -o tasks.jsonl
    scp tasks.jsonl gpu:~/th-verify-asr/
    ssh gpu 'cd th-verify-asr && LD_LIBRARY_PATH=... .venv/bin/python asr_worker.py \\
             --tasks tasks.jsonl --out results.jsonl'
    scp gpu:~/th-verify-asr/results.jsonl .
    python scripts/asr/asr_pipeline.py validate results.jsonl
    python scripts/asr/asr_pipeline.py apply results.jsonl --dry-run
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from build_dataset import normalize_verdict  # noqa: E402
from _canonical import assert_canonical  # noqa: E402

DB = "data/th_verify.db"


# Sure & Share publishes several formats under one channel and they are not
# equally labellable. Only the standard "จริงหรือ?" episode ends with an explicit
# verdict; LIVE shows, PODCASTs, CHECK-LIST compilations, HIGHLIGHT cuts and
# #shorts are excerpts or discussions that often never state one.
#
# This matters because the 115 human-labelled episodes are 88% standard format
# and contain zero shorts, while the unlabelled backlog is 51% shorts. Measuring
# the pipeline on the human set and extrapolating to the whole queue overstated
# coverage badly -- 83% predicted against 25% observed on a mixed sample.
NON_VERDICT_MARKERS = ("LIVE", "PODCAST", "CHECK-LIST", "HIGHLIGHT",
                       "#shorts", "#Shorts", "Motor Check")


def is_standard_episode(title: str) -> bool:
    title = title or ""
    if any(m in title for m in NON_VERDICT_MARKERS):
        return False
    return "จริงหรือ" in title


def cmd_prepare(args) -> int:
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    if args.validation:
        # The answer key: episodes a human already judged. Used to measure the
        # pipeline, never to overwrite the human's verdict.
        rows = con.execute(
            "SELECT id, source_url, title, verdict FROM fact_checks "
            "WHERE source='sure_share' AND verdict_origin='human' "
            "ORDER BY id").fetchall()
    else:
        rows = con.execute(
            "SELECT id, source_url, title, verdict FROM fact_checks "
            "WHERE source='sure_share' AND verdict_origin='' "
            "ORDER BY id").fetchall()
    rows = list(rows)
    if args.standard_only:
        before = len(rows)
        rows = [r for r in rows if is_standard_episode(r["title"])]
        print(f"format filter: {before} -> {len(rows)} standard episodes")
    if args.limit:
        # Spread across the archive rather than taking the newest block, so a
        # sample is not dominated by one period's presenting style.
        step = max(1, len(rows) / args.limit)
        rows = [rows[int(i * step)] for i in range(min(args.limit, len(rows)))]

    with args.out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({"id": r["id"], "url": r["source_url"],
                                 "title": r["title"]}, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} tasks -> {args.out}")
    if args.validation:
        print("mode: VALIDATION (human-labelled episodes; results must be scored, not applied)")
    return 0


def cmd_validate(args) -> int:
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    truth = {r[0]: normalize_verdict("sure_share", r[1]) for r in con.execute(
        "SELECT id, verdict FROM fact_checks WHERE verdict_origin='human'")}

    results = [json.loads(l) for l in args.results.read_text(encoding="utf-8").splitlines() if l.strip()]
    status = Counter(r["status"] for r in results)
    scored = [r for r in results if r["status"] == "labelled" and r["id"] in truth]

    correct = 0
    confusion: dict[tuple[str, str], int] = defaultdict(int)
    per_class = Counter()
    for r in scored:
        t, p = truth[r["id"]], r["verdict"]
        per_class[t] += 1
        confusion[(t, p)] += 1
        correct += (t == p)

    print(f"worker outcomes: {dict(status)}")
    print(f"scored against human labels: {len(scored)}")
    if not scored:
        print("nothing to score")
        return 0
    acc = correct / len(scored)
    print(f"\nACCURACY: {acc:.1%}  ({correct}/{len(scored)})\n")

    print("per class (human label -> how often the pipeline agreed):")
    for label in sorted(per_class):
        hits = confusion[(label, label)]
        print(f"   {label:14} {hits:3}/{per_class[label]:<3} {hits/per_class[label]:6.0%}")

    wrong = {k: v for k, v in confusion.items() if k[0] != k[1]}
    if wrong:
        print("\ndisagreements (human -> pipeline):")
        for (t, p), n in sorted(wrong.items(), key=lambda x: -x[1]):
            print(f"   {t:14} -> {p:14} {n}")

    # Coverage matters as much as accuracy: a pipeline that is 95% accurate on
    # 10% of episodes barely dents a 7,000-item queue.
    attempted = len(results)
    print(f"\ncoverage: {status.get('labelled',0)}/{attempted} "
          f"({status.get('labelled',0)/attempted:.0%}) produced a usable label")
    print(f"effective yield = accuracy x coverage = "
          f"{acc * status.get('labelled',0)/attempted:.0%}")
    return 0


def cmd_apply(args) -> int:
    # Applying labels mutates the archive, so it only happens on the one
    # authoritative database. A dry run inspects and is therefore unrestricted.
    if not args.dry_run:
        assert_canonical(args.db, action="apply labels to")
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    results = [json.loads(l) for l in args.results.read_text(encoding="utf-8").splitlines() if l.strip()]
    accepted = [r for r in results if r["status"] == "labelled"]
    print(f"{len(accepted)} labelled results of {len(results)}")

    applied = skipped_human = 0
    stamp = datetime.now(timezone.utc).isoformat()
    for r in accepted:
        row = con.execute("SELECT verdict_origin FROM fact_checks WHERE id=?",
                          (r["id"],)).fetchone()
        if row is None:
            continue
        if str(row["verdict_origin"]).startswith("human"):
            skipped_human += 1  # a human label always outranks the pipeline
            continue
        applied += 1
        if not args.dry_run:
            con.execute(
                "UPDATE fact_checks SET verdict=?, verdict_origin='llm', labeled_at=? "
                "WHERE id=? AND verdict_origin NOT LIKE 'human%'",
                (r["verdict"], stamp, r["id"]))
    if not args.dry_run:
        con.commit()
    con.close()
    print(f"{'would apply' if args.dry_run else 'applied'}: {applied}")
    print(f"skipped (human-labelled, protected): {skipped_human}")
    if args.dry_run:
        print("\ndry run - nothing written. Re-run without --dry-run to commit.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DB)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("-o", "--out", type=Path, default=Path("tasks.jsonl"))
    p.add_argument("--validation", action="store_true",
                   help="use human-labelled episodes as an answer key")
    p.add_argument("--limit", type=int)
    p.add_argument("--standard-only", action="store_true",
                   help="only the 'จริงหรือ?' format, which actually states a verdict")
    p.set_defaults(fn=cmd_prepare)

    p = sub.add_parser("validate")
    p.add_argument("results", type=Path)
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("apply")
    p.add_argument("results", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_apply)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
