#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""narrative_shift.py — find the periods where a topic's narrative changed.

The Issue Focus Report answers "how much" — volume, verdict mix, categories. The
more interesting question, and the one an analyst has so far had to answer by
eye, is **what the claims were about, and when that changed**. The migrant
report's "four eras" insight was written by hand from the per-year category
matrix. This finds those eras from the data instead, and can find the ones the
taxonomy never named.

Method, and why each step
-------------------------
1. **Embed the claim text** (`intfloat/multilingual-e5-small`, the model already
   behind /check). Embeddings rather than keywords because Thai has no word
   spaces — every term-frequency method needs a tokenizer this environment does
   not have, and because a *new* narrative by definition has no keyword in any
   config yet.
2. **k-means on the normalized vectors.** Average-linkage agglomerative was
   tried first and chained 312 of 337 migrant records into one cluster; on
   normalized embeddings within an already-narrow topic, k-means partitions
   where linkage collapses. k is chosen by silhouette over a small range unless
   --k is given.
3. **Locate each cluster in time** — a year histogram, and its share of the
   early half of the archive against its share of the late half.
4. **Permutation-test the gap.** Shuffle the dates 2,000 times and ask how often
   chance alone moves a cluster's share that far. With 300-odd records a share
   swing of ten points is not automatically a trend, and this is the difference
   between "the narrative changed" as a finding and as an impression.
5. **Report coherence against a baseline.** Mean cosine to the centroid is
   useless raw — e5 vectors sit in a narrow cone, so every cluster scores ~0.93
   and looks excellent. What separates a narrative from a leftovers bin is how
   much tighter it is than the topic as a whole, and the loosest cluster in the
   partition is flagged so it is not written up as a narrative.

What it deliberately does NOT do
--------------------------------
**Name the clusters.** It prints the medoid — the single real claim closest to
the cluster centre — plus exemplars, and a human reads them and writes the name
into the story file. Cluster labels invented by a machine are exactly the kind
of confident-sounding artefact this project fences everywhere else, and a wrong
name here would propagate into a published headline.

Usage
-----
    python scripts/narrative_shift.py migrant
    python scripts/narrative_shift.py migrant --k 8 --min-size 5
    python scripts/narrative_shift.py political_state --json-only
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np  # noqa: E402

from build_issue_report import build_where, load_topic  # noqa: E402
import build_issue_feature as feat  # noqa: E402
from _freshness import assert_fresh  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "th_verify.db"
OUT_DIR = ROOT / "data" / "reports"
EMBED_MODEL = "intfloat/multilingual-e5-small"

# AFNC and Cofact publish periodic round-ups: a single record whose text is a
# list of that week's headlines. They are not claims, they cluster together on
# their boilerplate, and left in they produce a confident-looking "narrative"
# made entirely of digest posts. Dropped before clustering, and reported.
DIGEST_PATTERNS = [
    r"ข่าวเด่นประจำสัปดาห์",
    r"สรุปข่าว(จริง|ปลอม|จริง ลวง)",
    r"ประจำวันที่\s*\d",
    r"ประจำสัปดาห์",
    r"Cofact\s*(Special\s*)?Report",
    r"รายงานประจำปี",
    r"\d+\s*เรื่องเด่น",
]


def is_digest(text: str) -> bool:
    return any(re.search(p, text, re.I) for p in DIGEST_PATTERNS)


def load_records(cfg: dict, db: str) -> tuple[list[dict], int]:
    con = sqlite3.connect(db)
    assert_fresh(con)
    con.row_factory = sqlite3.Row
    try:
        recs = feat.fetch(con, cfg)
    finally:
        con.close()
    keep, dropped = [], 0
    for r in recs:
        text = (r["claim"] or r["title"] or "").strip()
        if not text or not r["date"]:
            continue
        if is_digest(f"{r['title']} {r['claim']}"):
            dropped += 1
            continue
        keep.append(r)
    keep.sort(key=lambda r: r["date"])
    return keep, dropped


def embed(records: list[dict]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL)
    # "passage:" is the prefix the index and /check already use for stored text;
    # keeping it identical means these vectors live in the same space.
    return model.encode(["passage: " + (r["claim"] or r["title"]) for r in records],
                        normalize_embeddings=True, batch_size=128,
                        show_progress_bar=False)


def choose_k(X: np.ndarray, lo: int, hi: int) -> int:
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    best, best_k = -1.0, lo
    for k in range(lo, min(hi, len(X) - 1) + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(X)
        if len(set(labels)) < 2:
            continue
        s = silhouette_score(X, labels, metric="cosine")
        print(f"    k={k}: silhouette {s:.3f}", file=sys.stderr)
        if s > best:
            best, best_k = s, k
    return best_k


def analyse(records: list[dict], X: np.ndarray, k: int, *, min_size: int,
            n_perm: int = 2000, seed: int = 0) -> dict:
    from sklearn.cluster import KMeans
    rng = np.random.default_rng(seed)
    labels = KMeans(n_clusters=k, n_init=20, random_state=seed).fit_predict(X)
    years = np.array([int(r["date"][:4]) for r in records])
    y0, y1 = int(years.min()), int(years.max())
    span = list(range(y0, y1 + 1))
    # Split the timeline in half by *year*, not by record count: the archive
    # grows over time, so a median-record split would put the boundary in the
    # last two years and call almost everything "early".
    cut = y0 + (y1 - y0 + 1) // 2
    early, late = years < cut, years >= cut

    # Coherence has to be read against a baseline. e5 vectors sit in a narrow
    # cone — every cluster in a single topic scores ~0.93 against its own
    # centroid, which looks excellent and means nothing. What distinguishes a
    # real narrative from a leftovers bin is how much *tighter* it is than the
    # topic as a whole.
    topic_cen = X.mean(0)
    topic_cen /= np.linalg.norm(topic_cen)
    baseline = float((X @ topic_cen).mean())

    out = []
    for c in range(k):
        idx = np.where(labels == c)[0]
        if len(idx) < min_size:
            continue
        cen = X[idx].mean(0)
        cen /= np.linalg.norm(cen)
        sims = X[idx] @ cen
        order = idx[np.argsort(-sims)]
        share_e = float((labels[early] == c).mean()) if early.any() else 0.0
        share_l = float((labels[late] == c).mean()) if late.any() else 0.0
        gap = share_l - share_e
        perm = np.array([
            (labels[rng.permutation(len(labels))][late] == c).mean()
            - (labels[rng.permutation(len(labels))][early] == c).mean()
            for _ in range(n_perm)])
        p = float((np.abs(perm) >= abs(gap)).mean())
        hist = Counter(int(y) for y in years[idx])
        peak = max(span, key=lambda y: hist.get(y, 0))
        out.append({
            "cluster": int(c),
            "n": int(len(idx)),
            "coherence": round(float(sims.mean()), 3),
            "coherence_excess": round(float(sims.mean()) - baseline, 3),
            "share_early": round(share_e, 4),
            "share_late": round(share_l, 4),
            "shift_pts": round(gap * 100, 1),
            "p_value": round(p, 4),
            "peak_year": peak,
            "first_year": int(min(hist)), "last_year": int(max(hist)),
            "by_year": {str(y): hist.get(y, 0) for y in span},
            "medoid": (records[order[0]]["claim"] or records[order[0]]["title"]),
            "medoid_id": records[order[0]]["id"],
            "exemplar_ids": [records[i]["id"] for i in order[:8]],
            "exemplars": [(records[i]["claim"] or records[i]["title"])[:140]
                          for i in order[:5]],
        })
    # Which cluster is a leftovers bin is a question about *this* partition, so
    # the flag is relative: absolute excess-coherence values sit in a band whose
    # width depends on the topic, and any fixed threshold either flags all of
    # them or none.
    if out:
        med = float(np.median([c["coherence_excess"] for c in out]))
        for c in out:
            c["loose"] = bool(c["coherence_excess"] < med / 2)
    out.sort(key=lambda d: -abs(d["shift_pts"]))

    # How much the whole mix moves from one year to the next. A spike here is a
    # candidate turning point even when no single cluster crosses on its own.
    def mix(y: int) -> np.ndarray:
        v = np.zeros(k)
        for i, yy in enumerate(years):
            if yy == y:
                v[labels[i]] += 1
        return v / v.sum() if v.sum() else v

    def jsd(p_: np.ndarray, q: np.ndarray) -> float:
        m = (p_ + q) / 2
        def kl(a, b):
            mask = a > 0
            return float(np.sum(a[mask] * np.log2(a[mask] / np.clip(b[mask], 1e-12, None))))
        return (kl(p_, m) + kl(q, m)) / 2

    counts = Counter(int(y) for y in years)
    turns = []
    for a, b in zip(span, span[1:]):
        # Two thin years produce a large divergence for free; require enough
        # records on both sides for the number to mean anything.
        if counts.get(a, 0) >= 8 and counts.get(b, 0) >= 8:
            turns.append({"from": a, "to": b, "jsd": round(jsd(mix(a), mix(b)), 3),
                          "n_from": counts[a], "n_to": counts[b]})

    return {
        "k": k, "n_records": len(records), "years": [y0, y1], "split_year": cut,
        "baseline_coherence": round(baseline, 3),
        "clusters": out, "year_counts": {str(y): counts.get(y, 0) for y in span},
        "turning_points": sorted(turns, key=lambda t: -t["jsd"]),
    }


def report(res: dict, cfg: dict, dropped: int) -> None:
    span = [str(y) for y in range(res["years"][0], res["years"][1] + 1)]
    print(f"\n{cfg['slug']}: {res['n_records']} records "
          f"{res['years'][0]}–{res['years'][1]}, k={res['k']}, "
          f"early/late split at {res['split_year']} "
          f"({dropped} digest posts dropped)\n")
    print("Each cluster is a candidate narrative. Read the exemplars and name it "
          "yourself —\nthe tool does not name them.\n")
    for c in res["clusters"]:
        stars = ("***" if c["p_value"] < 0.01 else
                 "**" if c["p_value"] < 0.05 else "   ")
        flag = ("  ⚠ loosest cluster here — read it as a leftovers bin until "
                "the exemplars prove otherwise" if c.get("loose") else "")
        print(f"[c{c['cluster']}] n={c['n']:<4} "
              f"coherence={c['coherence']:.2f} (+{c['coherence_excess']:.3f} vs topic){flag}")
        print(f"      share {c['share_early']*100:5.1f}% → {c['share_late']*100:5.1f}%  "
              f"({c['shift_pts']:+.1f} pts, p={c['p_value']:.3f}) {stars}   peak {c['peak_year']}")
        print("      " + " ".join(f"{y[2:]}:{c['by_year'][y]:<3}" for y in span))
        print(f"      medoid [{c['medoid_id']}]: {c['medoid'][:100]}")
        for ex in c["exemplars"][1:4]:
            print(f"              · {ex[:96]}")
        print()
    print("Note: silhouette scores for short-text embeddings are low in absolute "
          "terms (~0.1),\nso k is a weak choice, not a strong one. Re-run with a "
          "different --k before\ntreating any single partition as the answer.\n")
    if res["turning_points"]:
        print("Largest year-to-year moves in the overall mix (Jensen-Shannon):")
        for t in res["turning_points"][:4]:
            print(f"  {t['from']}→{t['to']}  JSD={t['jsd']:.3f}  "
                  f"(n {t['n_from']}→{t['n_to']})")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("topic", help="topic slug in scripts/issue_topics/ or a path")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--k", type=int, help="number of clusters (default: by silhouette)")
    ap.add_argument("--k-range", default="5,10", help="search range for k, e.g. 5,10")
    ap.add_argument("--min-size", type=int, default=4,
                    help="ignore clusters smaller than this")
    ap.add_argument("--out", help="JSON output path "
                                  "(default data/reports/<slug>_narratives.json)")
    ap.add_argument("--json-only", action="store_true")
    args = ap.parse_args()

    cfg = load_topic(args.topic)
    records, dropped = load_records(cfg, args.db)
    if len(records) < 40:
        sys.exit(f"only {len(records)} usable records — too few to read shifts from")

    print(f"  embedding {len(records)} claims with {EMBED_MODEL} …", file=sys.stderr)
    X = embed(records)

    if args.k:
        k = args.k
    else:
        lo, hi = (int(v) for v in args.k_range.split(","))
        print("  choosing k by silhouette …", file=sys.stderr)
        k = choose_k(X, lo, hi)
        print(f"  k={k}", file=sys.stderr)

    res = analyse(records, X, k, min_size=args.min_size)
    res["slug"] = cfg["slug"]
    res["digests_dropped"] = dropped

    out = Path(args.out) if args.out else OUT_DIR / f"{cfg['slug']}_narratives.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    if not args.json_only:
        report(res, cfg, dropped)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
