#!/usr/bin/env python3
"""Assemble the assistant's (AI) coding of the 513 Story 2 queue rows into one CSV + summary tables.

Usage: python scripts/story2_build_ai_coded.py CODES_FILE [CODES_FILE ...] [--out DIR]
Rows keep coder_A.csv order. Every row carries coded_by=assistant: this is AI coding, never human coding.
"""
import argparse, csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import story2_ai_coding_tools as t

csv.field_size_limit(10**9)
ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "deliverables/story2_coding/coder_A.csv"
MASTER = ROOT / "deliverables/story2_coding/master_key.csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="+")
    ap.add_argument("--out", default=str(ROOT / "deliverables/story2_coding/ai_coded"))
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    codes = t.load_codes(a.codes)
    rows = list(csv.DictReader(open(SHEET, encoding="utf-8-sig")))
    assert [r["id"] for r in rows] == list(codes), "codes do not match sheet order"
    cols = list(rows[0].keys()) + ["coded_by"]
    done = []
    for r in rows:
        r.update(codes[r["id"]]); r["coded_by"] = "assistant"; done.append(r)
    with open(out / "ai_coding_v1.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(done)

    master = {r["id"]: r for r in csv.DictReader(open(MASTER, encoding="utf-8-sig"))}
    scope = Counter(r["scope"] for r in done)
    inn = [r for r in done if r["scope"] in ("resident_refugee_status", "crossborder_people_services")]
    by_year = defaultdict(Counter)
    for r in done:
        by_year[r["date"][:4]][r["scope"]] += 1
    frames = {k: sum(1 for r in inn if r[k]) for k in t.FRAME.values()}
    groups = Counter(r["target_group"] for r in inn)
    blamed = Counter(r["blamed_actor"] for r in inn); victim = Counter(r["victim_actor"] for r in inn)
    other_txt = Counter(r["frame_other_text"] for r in inn if r["frame_other_text"])
    # agreement with the earlier keyword/assistant screening (scope only; both are the assistant's judgements)
    prior_in = {i for i, m in master.items() if m["assistant_scope"] in ("resident_refugee_status", "crossborder_people_services")}
    now_in = {r["id"] for r in inn}
    summary = {
        "coded_by": "assistant (AI) - not human-coded, not human-validated",
        "n_rows": len(done), "scope": dict(scope), "in_scope": len(inn),
        "in_scope_by_year": {y: dict(c) for y, c in sorted(by_year.items())},
        "target_group": dict(groups), "frames": frames, "frame_other_text": dict(other_txt),
        "blamed_actor": dict(blamed), "victim_actor": dict(victim),
        "dehumanizing": sum(1 for r in inn if r["dehumanizing_language"]),
        "vs_prior_screening": {"prior_in": len(prior_in), "now_in": len(now_in),
                               "both": len(prior_in & now_in), "only_prior": len(prior_in - now_in), "only_now": len(now_in - prior_in)},
    }
    (out / "ai_coding_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
