#!/usr/bin/env python3
"""Build blind human-coding sheets for Story 2 (migrant narratives).

Reads a review queue (default: the 332-row queue of the canonical BERTopic run;
the current kit uses the 513-row v2 queue via --queue) and writes, under
deliverables/story2_coding/:

  coder_A.csv, coder_B.csv   identical rows, independently shuffled, NO model labels
  master_key.csv             row -> assistant scope / retrieval route (do not give to coders)

Coders must not see assistant_scope, subtopic, similarity or TypeSafe output, so
their judgements are independent of the models they are meant to check.
Does not modify anything under runs/. Re-running with the same seed is
deterministic; refuses to overwrite existing sheets (coders may have started).
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/20260908_bertopic_v001"
QUEUE = RUN / "migrant_scope_decisions.csv"  # override with --queue (e.g. runs/20261004_story2_queue_v002/review_queue_v2.csv)
OUT = ROOT / "deliverables/story2_coding"
SEED = 20261004
CALIBRATION = {"resident_refugee_status": 10, "crossborder_people_services": 6, "unclear": 4, "out_of_scope": 10}

SHOW = ["id", "source", "date", "verdict", "title", "claim_text", "url"]
CODE = [
    "phase", "scope", "target_group",
    "frame_disease_vector", "frame_job_competition", "frame_undeserved_benefits",
    "frame_security_threat", "frame_criminality", "frame_victim_exploitation",
    "frame_other", "frame_other_text", "frame_none",
    "blamed_actor", "victim_actor", "dehumanizing_language",
    "needs_source_check", "note",
]


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path: Path, rows: list[dict], cols: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    rows = read(QUEUE)
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        sys.exit("duplicate ids in review queue")
    OUT.mkdir(parents=True, exist_ok=True)
    targets = [OUT / n for n in ("coder_A.csv", "coder_B.csv", "master_key.csv")]
    if any(t.exists() for t in targets):
        sys.exit(f"{OUT} already has sheets; move them aside before rebuilding")

    rng = random.Random(SEED)
    by_scope: dict[str, list[dict]] = {}
    for r in rows:
        by_scope.setdefault(r["assistant_scope"], []).append(r)
    calib = []
    for scope, n in CALIBRATION.items():
        pool = sorted(by_scope.get(scope, []), key=lambda r: int(r["id"]))
        calib += rng.sample(pool, min(n, len(pool)))
    calib_ids = {r["id"] for r in calib}
    rest = [r for r in rows if r["id"] not in calib_ids]

    def sheet(seed_offset: int) -> list[dict]:
        r2 = random.Random(SEED + seed_offset)
        c, t = calib[:], rest[:]
        r2.shuffle(c)
        r2.shuffle(t)
        out = []
        for phase, group in (("calibration", c), ("main", t)):
            for r in group:
                row = {k: r[k] for k in SHOW}
                row.update({k: "" for k in CODE})
                row["phase"] = phase
                out.append(row)
        return out

    write(OUT / "coder_A.csv", sheet(1), SHOW + CODE)
    write(OUT / "coder_B.csv", sheet(2), SHOW + CODE)
    write(OUT / "master_key.csv",
          [{"id": r["id"], "assistant_scope": r["assistant_scope"], "retrieval_route": r["retrieval_route"],
            "phase": "calibration" if r["id"] in calib_ids else "main", "queue_round": r.get("queue_round", "1")} for r in rows],
          ["id", "assistant_scope", "retrieval_route", "phase", "queue_round"])
    print(f"wrote {len(rows)} rows x 2 coder sheets ({len(calib)} calibration) to {OUT}")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queue", type=Path, help="review queue CSV with assistant_scope + retrieval_route (default: canonical 332-row queue)")
    ap.add_argument("--out", type=Path, help="output directory (default: deliverables/story2_coding)")
    a = ap.parse_args()
    if a.queue:
        QUEUE = a.queue if a.queue.is_absolute() else ROOT / a.queue
    if a.out:
        OUT = a.out if a.out.is_absolute() else ROOT / a.out
    raise SystemExit(main())
