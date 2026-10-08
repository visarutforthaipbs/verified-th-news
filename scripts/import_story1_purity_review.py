#!/usr/bin/env python3
"""Validate (and optionally apply) the CSVs exported from deliverables/story1_review/purity_review_app.html.

Usage:  python scripts/import_story1_purity_review.py EXPORT.csv [EXPORT2.csv ...] [--apply]

The sheet is detected from the columns (claim_text present -> topic0_samples.csv, else named_topic_samples.csv).
Checks: identical header and row order to the original sheet; every non-human column unchanged; human_pure in {1, 0, ?, empty}.
Prints per-topic counts and a 95% Wilson interval for the share of "1" among decided (1/0) rows - reported as interim, human-read.
--apply backs up the original to deliverables/story1_review/backup/ and writes the validated export over it (UTF-8 with BOM, like the original).
"""
import argparse, csv, math, shutil, sys, time
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(10**9)
ROOT = Path(__file__).resolve().parent.parent
SHEETS = {"A": ROOT / "runs/20261004_story1_by_publisher_v001/topic0_samples.csv", "B": ROOT / "runs/20261004_purity_v001/named_topic_samples.csv"}
BACKUP = ROOT / "deliverables/story1_review/backup"
OK = {"1", "0", "?", ""}


def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        h = next(r)
        return h, [dict(zip(h, row)) for row in r]


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)


def validate(export_path, sheets=SHEETS):
    h, rows = rd(export_path)
    sh = "A" if "claim_text" in h else "B"
    oh, orows = rd(sheets[sh])
    errs = []
    if h != oh:
        errs.append(f"header differs: {h} vs {oh}")
        return sh, rows, errs
    if len(rows) != len(orows):
        errs.append(f"row count {len(rows)} != {len(orows)}")
    for i, (r, o) in enumerate(zip(rows, orows), 2):
        for c in oh:
            if c in ("human_pure", "human_note"):
                continue
            if r[c] != o[c]:
                errs.append(f"line {i}: column {c} changed (id {o['id']})")
        if r["human_pure"].strip() not in OK:
            errs.append(f"line {i}: human_pure={r['human_pure']!r} not in 1/0/?/empty (id {o['id']})")
        if o["human_pure"] or o["human_note"]:
            errs.append(f"original already has an answer at line {i}; refusing to overwrite")
    return sh, rows, errs


def report(sh, rows):
    by = defaultdict(lambda: {"1": 0, "0": 0, "?": 0, "": 0})
    for r in rows:
        by[r["topic_id"]][r["human_pure"].strip()] += 1
    print(f"sheet {sh} ({SHEETS[sh].name}): {len(rows)} rows")
    print(f"{'topic':>6} {'1':>4} {'0':>4} {'?':>4} {'blank':>6}   share of 1 among 1/0 (95% Wilson)")
    for t, c in sorted(by.items(), key=lambda x: int(x[0])):
        n = c["1"] + c["0"]
        w = wilson(c["1"], n)
        s = f"{c['1']}/{n} = {c['1']/n:.0%}  [{w[0]:.0%}, {w[1]:.0%}]" if n else "-"
        print(f"{t:>6} {c['1']:>4} {c['0']:>4} {c['?']:>4} {c['']:>6}   {s}")


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("exports", nargs="+"); ap.add_argument("--apply", action="store_true"); a = ap.parse_args(argv)
    bad = False
    for e in a.exports:
        sh, rows, errs = validate(e)
        if errs:
            bad = True
            print(f"FAIL {e}: {len(errs)} problem(s)"); [print("  -", x) for x in errs[:15]]
            continue
        report(sh, rows)
        if a.apply:
            BACKUP.mkdir(parents=True, exist_ok=True)
            bk = BACKUP / f"{SHEETS[sh].name}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
            shutil.copy2(SHEETS[sh], bk)
            shutil.copyfile(e, SHEETS[sh])
            raw = SHEETS[sh].read_bytes()
            if not raw.startswith(b"\xef\xbb\xbf"):
                SHEETS[sh].write_bytes(b"\xef\xbb\xbf" + raw)
            print(f"applied -> {SHEETS[sh]} (backup: {bk})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
