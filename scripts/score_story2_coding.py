#!/usr/bin/env python3
"""Score two coders' Story 2 sheets: agreement, disagreements, and agreement with the models.

Usage: python scripts/score_story2_coding.py [coder_A.csv coder_B.csv] [--master master_key.csv]
Writes agreement_report.json and adjudication.csv next to the inputs. Read-only on the sheets.

Scope is scored on all coded rows; frames only on rows both coders put in scope
(resident_refugee_status or crossborder_people_services). Kappa is Cohen's kappa;
treat < 0.6 as "codebook not yet reliable" and revise before coding the main set.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "deliverables/story2_coding"
SCOPES = {"resident_refugee_status", "crossborder_people_services", "out_of_scope", "unclear"}
IN_SCOPE = {"resident_refugee_status", "crossborder_people_services"}
FRAMES = ["frame_disease_vector", "frame_job_competition", "frame_undeserved_benefits",
          "frame_security_threat", "frame_criminality", "frame_victim_exploitation", "frame_other", "frame_none"]
ACTORS = {"migrants", "thai_state", "employers_brokers", "foreign_state", "thai_public", "other", "none"}


def read(p: Path) -> dict[str, dict]:
    with p.open(encoding="utf-8-sig", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def kappa(a: list, b: list) -> float | None:
    n = len(a)
    if not n:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", nargs="?", type=Path, default=DEFAULT / "coder_A.csv")
    ap.add_argument("b", nargs="?", type=Path, default=DEFAULT / "coder_B.csv")
    ap.add_argument("--master", type=Path, default=DEFAULT / "master_key.csv")
    args = ap.parse_args()
    A, B = read(args.a), read(args.b)
    if set(A) != set(B):
        raise SystemExit("coder sheets cover different ids")
    bad = [(i, r["scope"]) for s in (A, B) for i, r in s.items() if r["scope"] and r["scope"] not in SCOPES]
    if bad:
        raise SystemExit(f"invalid scope values (first 5): {bad[:5]}")
    done = [i for i in A if A[i]["scope"] and B[i]["scope"]]
    report: dict = {"rows_total": len(A), "rows_coded_by_both": len(done)}
    if not done:
        raise SystemExit("no rows coded by both coders yet")

    sa, sb = [A[i]["scope"] for i in done], [B[i]["scope"] for i in done]
    report["scope"] = {"agreement": round(sum(x == y for x, y in zip(sa, sb)) / len(done), 3), "kappa": kappa(sa, sb)}
    ia = [x in IN_SCOPE for x in sa]
    ib = [x in IN_SCOPE for x in sb]
    report["scope_in_vs_out"] = {"agreement": round(sum(x == y for x, y in zip(ia, ib)) / len(done), 3), "kappa": kappa(ia, ib)}

    both_in = [i for i in done if A[i]["scope"] in IN_SCOPE and B[i]["scope"] in IN_SCOPE]
    report["frame_rows"] = len(both_in)
    report["frames"] = {}
    for f in FRAMES:
        va = [A[i][f].strip() == "1" for i in both_in]
        vb = [B[i][f].strip() == "1" for i in both_in]
        report["frames"][f] = {"kappa": kappa(va, vb), "A_yes": sum(va), "B_yes": sum(vb),
                               "agreement": round(sum(x == y for x, y in zip(va, vb)) / len(both_in), 3) if both_in else None}
    for col in ("blamed_actor", "victim_actor"):
        report[col] = {"kappa": kappa([A[i][col] for i in both_in], [B[i][col] for i in both_in])}
    if both_in and "target_group" in A[both_in[0]]:
        ga, gb = [A[i]["target_group"].strip() for i in both_in], [B[i]["target_group"].strip() for i in both_in]
        report["target_group"] = {"kappa": kappa(ga, gb), "agreement": round(sum(x == y for x, y in zip(ga, gb)) / len(both_in), 3)}
    report["dehumanizing_language"] = {"kappa": kappa([A[i]["dehumanizing_language"].strip() == "1" for i in both_in],
                                                      [B[i]["dehumanizing_language"].strip() == "1" for i in both_in])}

    if args.master.exists():
        M = read(args.master)
        for name, S in (("A", A), ("B", B)):
            ys = [S[i]["scope"] in IN_SCOPE for i in done]
            ms = [M[i]["assistant_scope"] in IN_SCOPE for i in done]
            report[f"coder_{name}_vs_assistant_in_out"] = {
                "agreement": round(sum(x == y for x, y in zip(ys, ms)) / len(done), 3), "kappa": kappa(ys, ms)}

    rows = []
    for i in done:
        def val(S, c):
            v = S[i][c].strip()
            return (v == "1") if (c in FRAMES or c == "dehumanizing_language") else v

        extra = ["target_group"] if "target_group" in A[i] else []
        diffs = [c for c in ["scope"] + extra + FRAMES + ["blamed_actor", "victim_actor", "dehumanizing_language"]
                 if val(A, c) != val(B, c) and (c == "scope" or i in both_in)]
        if diffs:
            rows.append({"id": i, "url": A[i]["url"], "title": A[i]["title"], "differs_on": "|".join(diffs),
                         "A_scope": A[i]["scope"], "B_scope": B[i]["scope"], "A_note": A[i]["note"], "B_note": B[i]["note"],
                         "final_scope": "", "final_frames": "", "adjudicator_note": ""})
    report["disagreement_rows"] = len(rows)
    out_dir = args.a.parent
    (out_dir / "agreement_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out_dir / "adjudication.csv").open("w", encoding="utf-8-sig", newline="") as f:
        cols = ["id", "url", "title", "differs_on", "A_scope", "B_scope", "A_note", "B_note", "final_scope", "final_frames", "adjudicator_note"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(json.dumps({k: report[k] for k in ("rows_coded_by_both", "scope", "scope_in_vs_out", "disagreement_rows")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
