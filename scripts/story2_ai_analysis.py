#!/usr/bin/env python3
"""Tables for Story 2 from the assistant's (AI) coding of the 513 queue rows. AI-coded, unvalidated.

Usage: python scripts/story2_ai_analysis.py [--out runs/20261007_story2_aicoded_v001]
Reads deliverables/story2_coding/ai_coded/ai_coding_v1.csv; year denominators and subtopic labels come from the 20261004 interim run.
"""
import argparse, csv, json
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(10**9)
ROOT = Path(__file__).resolve().parent.parent
IN = ("resident_refugee_status", "crossborder_people_services")


def rd(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=str(ROOT / "runs/20261007_story2_aicoded_v001")); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    ai = rd(ROOT / "deliverables/story2_coding/ai_coded/ai_coding_v1.csv")
    interim = {r["id"]: r for r in rd(ROOT / "runs/20261004_story2_interim_v002/in_scope_records_interim.csv")}
    denom = {r["year"]: int(r["all_records"]) for r in rd(ROOT / "runs/20261004_story2_interim_v002/in_scope_by_year.csv")}
    inn = [r for r in ai if r["scope"] in IN]
    for r in inn:
        r["year"] = r["date"][:4]
        r["subtopic_v2"] = interim.get(r["id"], {}).get("subtopic_v2", "")
    cols = ["id", "source", "date", "year", "verdict", "scope", "target_group", "subtopic_v2", "blamed_actor", "victim_actor", "claim_text", "url"]
    with open(out / "ai_in_scope_records.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(inn)
    yrs = sorted(denom)
    rows = []
    for y in yrs:
        s = [r for r in inn if r["year"] == y]
        n = len(s); nk = sum(1 for r in s if r["target_group"] != "cambodia")
        nki = sum(1 for r in s if r["target_group"] not in ("cambodia", "israel"))
        rows.append({"year": y, "all_records": denom[y], "in_scope": n, "share_pct": round(100 * n / denom[y], 2),
                     "excl_cambodia": nk, "excl_cambodia_pct": round(100 * nk / denom[y], 2),
                     "excl_cambodia_israel": nki, "excl_cambodia_israel_pct": round(100 * nki / denom[y], 2),
                     "resident": sum(1 for r in s if r["scope"] == IN[0]), "crossborder": sum(1 for r in s if r["scope"] == IN[1]),
                     **{f"src_{k}": sum(1 for r in s if r["source"] == k) for k in ("afnc", "cofact", "thaipbs", "afp", "sure")},
                     **{f"grp_{g}": sum(1 for r in s if r["target_group"] == g) for g in ("myanmar", "cambodia", "laos_vietnam", "china", "israel", "other_foreign", "generic", "mixed", "stateless_ethnic")}})
    with open(out / "ai_by_year.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    sub = defaultdict(lambda: Counter())
    for r in inn:
        sub[r["subtopic_v2"] or "new"][r["year"]] += 1
    with open(out / "ai_subtopic_by_year.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["subtopic_v2", "total"] + yrs)
        for k in sorted(sub, key=lambda x: (x == "new", int(x) if x.lstrip("-").isdigit() else 99)):
            w.writerow([k, sum(sub[k].values())] + [sub[k][y] for y in yrs])
    two = sum(1 for r in inn if r["year"] in ("2025", "2026"))
    summ = {"coded_by": "assistant (AI), unvalidated", "in_scope": len(inn), "in_2025_2026": two,
            "by_source": dict(Counter(r["source"] for r in inn)), "verdict": dict(Counter(r["verdict"] for r in inn)),
            "from_expanded_queue": sum(1 for r in inn if r.get("queue_round") == "2" or interim.get(r["id"], {}).get("queue_round") == "2"),
            "cambodia_2025_26": sum(1 for r in inn if r["year"] in ("2025", "2026") and r["target_group"] == "cambodia"),
            "israel": Counter(r["year"] for r in inn if r["target_group"] == "israel"),
            "china": sum(1 for r in inn if r["target_group"] == "china"),
            "llm_claim_text": sum(1 for r in inn if r.get("claim_text_basis") == "llm")}
    (out / "ai_summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    print(json.dumps(summ, ensure_ascii=False, indent=2, default=dict)); print(open(out / "ai_by_year.csv", encoding="utf-8-sig").read())
    print(open(out / "ai_subtopic_by_year.csv", encoding="utf-8-sig").read())


if __name__ == "__main__":
    main()
