#!/usr/bin/env python3
"""Score a single coder's Story 2 coding: self-consistency (test-retest) and an AI second look.

Why this exists: the method (docs/METHODOLOGY_BERTOPIC_V2.md 9.5) asks for two coders and
inter-coder agreement. With one coder, that is replaced by test-retest: the same person
re-codes a sample blind after a wait, and agreement between the two passes is the
reliability figure. This is NOT inter-coder reliability and must be described that way.

Usage:
  python scripts/score_story2_single_coder.py coder_main_*.csv coder_retest_*.csv [--master master_key.csv] [--out DIR]

Writes to --out (default: next to the main file), read-only on the inputs:
  self_consistency_report.json   agreement and Cohen's kappa between the coder's two passes
  self_disagreements.csv         rows where the coder differed from themself, for a final decision
  ai_second_look.csv             rows where the coder and the assistant's provisional reading differ
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score_story2_coding as sc  # noqa: E402  (kappa, constants, reader)

MIN_KAPPA = 0.6      # below this a category is not stable enough to report
MIN_YES = 5          # a frame used fewer times than this in either pass cannot be judged


def frames_of(row: dict) -> str:
    return ";".join(f for f in sc.FRAMES if row.get(f, "").strip() == "1")


def verdict(k, a, b) -> str:
    """a, b: the two passes as lists of booleans over the same rows."""
    yes_a, yes_b = sum(a), sum(b)
    if k is None and (len(set(a)) < 2 and len(set(b)) < 2):
        return "no variation in either pass: not computable"
    if min(yes_a, yes_b) < MIN_YES:
        return "too few uses to judge"
    if len(set(a)) < 2 or len(set(b)) < 2:
        return "no variation in one pass: kappa uninformative (kappa paradox), judge by agreement"
    return "stable" if k >= MIN_KAPPA else "NOT stable: do not report"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("main", type=Path)
    ap.add_argument("retest", type=Path)
    ap.add_argument("--master", type=Path, help="master_key.csv (assistant's provisional scope), for the second-look list")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    out = args.out or args.main.parent
    out.mkdir(parents=True, exist_ok=True)

    P1, P2 = sc.read(args.main), sc.read(args.retest)
    coded1 = {i for i, r in P1.items() if r["scope"].strip()}
    ids = [i for i, r in P2.items() if r["scope"].strip() and i in coded1]
    if not ids:
        raise SystemExit("no rows coded in both passes")
    bad = [(i, P2[i]["scope"]) for i in ids if P2[i]["scope"] not in sc.SCOPES] + [(i, P1[i]["scope"]) for i in ids if P1[i]["scope"] not in sc.SCOPES]
    if bad:
        raise SystemExit(f"invalid scope values (first 5): {bad[:5]}")

    s1, s2 = [P1[i]["scope"] for i in ids], [P2[i]["scope"] for i in ids]
    i1, i2 = [x in sc.IN_SCOPE for x in s1], [x in sc.IN_SCOPE for x in s2]
    rep: dict = {
        "what": "test-retest agreement of ONE coder between two passes; not inter-coder reliability",
        "rows_pass1": len(coded1), "rows_retest": len(ids),
        "retest_share_of_pass1_pct": round(len(ids) / len(coded1) * 100, 1),
        "scope_4way": {"agreement": round(sum(a == b for a, b in zip(s1, s2)) / len(ids), 3), "kappa": sc.kappa(s1, s2)},
        "scope_in_vs_out": {"agreement": round(sum(a == b for a, b in zip(i1, i2)) / len(ids), 3), "kappa": sc.kappa(i1, i2)},
        "thresholds": {"stable_kappa_at_least": MIN_KAPPA, "min_uses_per_pass": MIN_YES},
    }
    both = [i for i in ids if P1[i]["scope"] in sc.IN_SCOPE and P2[i]["scope"] in sc.IN_SCOPE]
    rep["rows_in_scope_in_both_passes"] = len(both)
    rep["frames"] = {}
    for f in sc.FRAMES:
        a = [P1[i][f].strip() == "1" for i in both]
        b = [P2[i][f].strip() == "1" for i in both]
        k = sc.kappa(a, b)
        rep["frames"][f] = {"kappa": k, "pass1_yes": sum(a), "retest_yes": sum(b),
                            "agreement": round(sum(x == y for x, y in zip(a, b)) / len(both), 3) if both else None,
                            "verdict": verdict(k, a, b)}
    for col in ("target_group", "blamed_actor", "victim_actor"):
        if both and col in P1[both[0]]:
            k = sc.kappa([P1[i][col] for i in both], [P2[i][col] for i in both])
            rep[col] = {"kappa": k, "verdict": "stable" if (k is not None and k >= MIN_KAPPA) else "NOT stable: do not report"}
    dh1, dh2 = [P1[i]["dehumanizing_language"].strip() == "1" for i in both], [P2[i]["dehumanizing_language"].strip() == "1" for i in both]
    rep["dehumanizing_language"] = {"kappa": sc.kappa(dh1, dh2), "pass1_yes": sum(dh1), "retest_yes": sum(dh2),
                                    "verdict": verdict(sc.kappa(dh1, dh2), dh1, dh2)}
    u1 = [i for i in ids if P1[i]["scope"] == "unclear"]
    rep["unclear_in_pass1"] = {"rows": len(u1), "decided_in_retest": sum(P2[i]["scope"] != "unclear" for i in u1)}

    # ---- rows where the coder differed from themself
    extra = ["target_group"] if both and "target_group" in P1[both[0]] else []
    cols_cmp = ["scope"] + extra + sc.FRAMES + ["blamed_actor", "victim_actor", "dehumanizing_language"]
    diff_rows = []
    for i in ids:
        both_in = i in both
        diffs = [c for c in cols_cmp if P1[i][c].strip() != P2[i][c].strip() and (c == "scope" or both_in)]
        if diffs:
            diff_rows.append({"id": i, "url": P1[i]["url"], "claim_text": P1[i]["claim_text"], "differs_on": "|".join(diffs),
                              "pass1_scope": P1[i]["scope"], "retest_scope": P2[i]["scope"],
                              "pass1_target_group": P1[i].get("target_group", ""), "retest_target_group": P2[i].get("target_group", ""),
                              "pass1_frames": frames_of(P1[i]), "retest_frames": frames_of(P2[i]),
                              "pass1_note": P1[i]["note"], "retest_note": P2[i]["note"],
                              "final_scope": "", "final_target_group": "", "final_frames": "", "owner_note": ""})
    rep["rows_differing_from_self"] = len(diff_rows)
    cols = ["id", "url", "claim_text", "differs_on", "pass1_scope", "retest_scope", "pass1_target_group", "retest_target_group", "pass1_frames",
            "retest_frames", "pass1_note", "retest_note", "final_scope", "final_target_group", "final_frames", "owner_note"]
    with (out / "self_disagreements.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(diff_rows)

    # ---- AI second look (pass 1 only; the AI is a second reader, not a validator)
    if args.master and args.master.exists():
        M = sc.read(args.master)
        known = [i for i in coded1 if i in M]
        h_in = [P1[i]["scope"] in sc.IN_SCOPE for i in known]
        a_in = [M[i]["assistant_scope"] in sc.IN_SCOPE for i in known]
        rep["human_vs_assistant_in_out"] = {
            "rows": len(known), "agreement": round(sum(x == y for x, y in zip(h_in, a_in)) / len(known), 3), "kappa": sc.kappa(h_in, a_in),
            "caveat": "NOT an independent check: the coder had read the assistant's draft, and the assistant's scope calls were made from the same titles"}
        look = []
        for i in sorted(known, key=int):
            h, a = P1[i]["scope"], M[i]["assistant_scope"]
            if (h in sc.IN_SCOPE) != (a in sc.IN_SCOPE) or h == "unclear":
                direction = ("coder_out_assistant_in" if a in sc.IN_SCOPE and h not in sc.IN_SCOPE and h != "unclear" else
                             "coder_in_assistant_out" if h in sc.IN_SCOPE else "coder_unclear")
                look.append({"id": i, "url": P1[i]["url"], "claim_text": P1[i]["claim_text"], "direction": direction, "coder_scope": h,
                             "assistant_scope": a, "coder_target_group": P1[i].get("target_group", ""), "coder_frames": frames_of(P1[i]),
                             "coder_note": P1[i]["note"], "final_scope": "", "owner_note": ""})
        rep["ai_second_look_rows"] = {"total": len(look), **{d: sum(r["direction"] == d for r in look) for d in
                                                              ("coder_out_assistant_in", "coder_in_assistant_out", "coder_unclear")}}
        with (out / "ai_second_look.csv").open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["id", "url", "claim_text", "direction", "coder_scope", "assistant_scope", "coder_target_group",
                                               "coder_frames", "coder_note", "final_scope", "owner_note"])
            w.writeheader(); w.writerows(look)

    (out / "self_consistency_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("rows_pass1", "rows_retest", "scope_4way", "scope_in_vs_out", "rows_in_scope_in_both_passes", "rows_differing_from_self")
                      if k in rep}, ensure_ascii=False))
    for f, v in rep["frames"].items():
        print(f"  {f:28s} kappa={v['kappa']}  uses {v['pass1_yes']}/{v['retest_yes']}  {v['verdict']}")
    if "ai_second_look_rows" in rep:
        print("  second look:", rep["ai_second_look_rows"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
