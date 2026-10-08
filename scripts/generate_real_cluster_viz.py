#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_real_cluster_viz.py
Cluster maps built from the REAL discovered-clustering run
(runs/20260908_bertopic_v001: E5 vectors -> UMAP10 -> HDBSCAN), replacing the
hard-coded-position / random-scatter figures flagged by the 2026-09-08 audit.

What is real here
  * Every dot is one unique claim text with its original E5 embedding.
  * Cluster membership is the HDBSCAN/BERTopic topic_id in assignments.csv.
  * 2-D positions come from a SEPARATE 2-D UMAP of those vectors (seed 42) and
    are for display only. Axes have no units; distances between far-apart
    islands are not quantitative. Hulls/centroids are computed on those 2-D
    coordinates from real member points (inner 90% by distance to the median).
  * Cluster names are MACHINE KEYWORDS ONLY (human labels still pending).

Outputs (data/reports/assets/):
  real_clusters_story1.png   whole-corpus map, 14,429 records / 13,377 texts
  real_clusters_story2.png   migrant review queue (332) placed on that map,
                             with raw per-year counts per subtopic (no %)
  and runs/20261004_viz_v001/{umap2d.npy,manifest.json,story1_cluster_table.csv,
  story2_subtopic_year_counts.csv}
"""
import csv, json, hashlib
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "runs/20260908_bertopic_v001"
OUT_RUN = ROOT / "runs/20261004_viz_v001"
ASSETS = ROOT / "data/reports/assets"
OUT_RUN.mkdir(parents=True, exist_ok=True)
ASSETS.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.family"] = "Sarabun"
plt.rcParams["axes.unicode_minus"] = False
BLACK, WHITE, GRAY, RED, YELLOW = "#000000", "#F2F2F2", "#7A7A7A", "#F20D1B", "#FFD400"
PALETTE = ["#F20D1B", "#FFD400", "#38BDF8", "#10B981", "#A855F7", "#F59E0B",
           "#EC4899", "#22D3EE", "#84CC16", "#FB7185", "#818CF8", "#FDBA74"]
# display-only label offsets (points) so labels don't collide; no analytic meaning
OFFS = {6: (-120, -48), 10: (10, -52), 5: (14, 20), 7: (-30, -54), 4: (-20, 24), 13: (-30, -52)}


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def layout2d(X):
    cache = OUT_RUN / "umap2d.npy"
    if cache.exists():
        Y = np.load(cache)
        if Y.shape[0] == X.shape[0]:
            return Y
    from umap import UMAP
    Y = UMAP(n_neighbors=15, n_components=2, min_dist=0.1, metric="cosine",
             random_state=42).fit_transform(X)
    np.save(cache, Y)
    return Y


def core_hull(P, keep=0.9):
    c = np.median(P, axis=0)
    d = np.linalg.norm(P - c, axis=1)
    core = P[d <= np.quantile(d, keep)]
    if len(core) < 4:
        return None
    return core[ConvexHull(core).vertices]


def short(kw, n=3):
    return " · ".join([w.strip() for w in kw.split("|")][:n])


def style(ax):
    ax.set_facecolor(BLACK)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#222")


def main():
    records = read(ROOT / "data/reports/journalist_handoff_2026-09-08/02_false_misleading_altered_records.csv")
    unique = list(dict.fromkeys(r["claim_text"] for r in records))
    X = np.load(RUN / "unique_embeddings.npy")
    assert X.shape[0] == len(unique), (X.shape, len(unique))
    Y = layout2d(X)
    idx = {t: i for i, t in enumerate(unique)}

    assign = read(RUN / "assignments.csv")
    topic_of_text = {}
    for r in assign:
        topic_of_text.setdefault(r["claim_text"], int(r["topic_id"]))
    labels = np.array([topic_of_text[t] for t in unique])
    topics = {int(r["topic_id"]): r for r in read(RUN / "topics.csv")}
    rec_counts = {t: int(r["records"]) for t, r in topics.items()}
    total_records = sum(rec_counts.values())

    # ───────── Story 1 ─────────
    order = [t for t, _ in sorted(rec_counts.items(), key=lambda kv: -kv[1]) if t not in (-1, 0)]
    shown = order[:12]
    color = {t: PALETTE[i % len(PALETTE)] for i, t in enumerate(shown)}

    fig, ax = plt.subplots(figsize=(16, 10), dpi=200, facecolor=BLACK)
    style(ax)
    other = ~np.isin(labels, shown + [-1, 0])
    ax.scatter(*Y[labels == -1].T, s=2, c="#303030", alpha=.6, lw=0, label="_")
    ax.scatter(*Y[labels == 0].T, s=2, c="#5a5a5a", alpha=.45, lw=0, label="_")
    ax.scatter(*Y[other].T, s=3, c="#8a8a8a", alpha=.55, lw=0, label="_")
    rows = []
    for t in shown:
        P = Y[labels == t]
        ax.scatter(*P.T, s=5, c=color[t], alpha=.85, lw=0)
        h = core_hull(P)
        if h is not None:
            ax.add_patch(Polygon(h, closed=True, fc=color[t], ec=color[t], alpha=.12, lw=1.2, ls="--"))
        cx, cy = np.median(P, axis=0)
        ax.scatter([cx], [cy], s=70, c=color[t], ec=WHITE, lw=1.2, zorder=5)
        ax.annotate(f"T{t}  {short(topics[t]['machine_keywords'])}\nN={rec_counts[t]:,} records",
                    (cx, cy), xytext=OFFS.get(t, (10, 12)), textcoords="offset points", color=WHITE, fontsize=8.5,
                    bbox=dict(boxstyle="round,pad=.25", fc="#05070b", ec=color[t], alpha=.9, lw=.8), zorder=6)
        rows.append(dict(topic_id=t, machine_keywords=topics[t]["machine_keywords"], records=rec_counts[t],
                         share_pct=round(100 * rec_counts[t] / total_records, 2), unique_texts=len(P),
                         centroid_x=round(float(cx), 3), centroid_y=round(float(cy), 3)))
    ax.set_title("")
    fig.text(.03, .955, "Discovered claim clusters, 2015–2026 (exploratory, machine-named)", color=WHITE, fontsize=22, fontweight="bold")
    fig.text(.03, .92, f"{total_records:,} false / misleading / altered records · {len(unique):,} unique texts · E5 → UMAP → HDBSCAN (min_cluster_size=30)",
             color=YELLOW, fontsize=11, family="monospace")
    n0, nn = rec_counts[0], rec_counts[-1]
    fig.text(.03, .895, f"Dark grey = noise T-1 ({100*nn/total_records:.1f}%) and mixed health/food blob T0 ({100*n0/total_records:.1f}%); mid grey = {len(topics)-2-len(shown)} smaller clusters. "
             "Labels are machine keywords, not validated narratives.", color=GRAY, fontsize=9.5)
    fig.text(.03, .03, "2-D layout is for display only: axes have no units and distances between islands are not quantitative. "
             "Hulls = inner 90% of members. Source: TH Verify snapshot 2026-09-02 · run 20260908_bertopic_v001",
             color=GRAY, fontsize=8.5)
    fig.text(.97, .03, "FAKE NEWS LAB × PRACHATAI", color=RED, fontsize=9, fontweight="bold", ha="right")
    fig.savefig(ASSETS / "real_clusters_story1.png", facecolor=BLACK)
    plt.close(fig)
    with open(OUT_RUN / "story1_cluster_table.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

    # ───────── Story 2 ─────────
    sub = read(RUN / "migrant_screened_assignments.csv")
    sub_names = {int(r["subtopic_id"]): r for r in read(RUN / "migrant_screened_topics.csv")}
    pts, sid, years, ids = [], [], [], []
    for r in sub:
        i = idx.get(r["claim_text"])
        if i is None:
            continue
        pts.append(Y[i]); sid.append(int(r["screened_subtopic"])); years.append(int(r["year"])); ids.append(r["id"])
    missing = len(sub) - len(pts)
    pts = np.array(pts); sid = np.array(sid); years = np.array(years)
    subs = sorted(set(sid))
    scol = {s: ("#6a6a6a" if s == -1 else PALETTE[k % len(PALETTE)]) for k, s in enumerate(subs)}

    fig = plt.figure(figsize=(18, 9), dpi=200, facecolor=BLACK)
    ax = fig.add_axes([.03, .1, .5, .78]); style(ax)
    ax.scatter(*Y.T, s=1.5, c="#262626", lw=0)
    for s in subs:
        P = pts[sid == s]
        kw_label = short(sub_names[s]["machine_keywords"], 2) if s in sub_names else f"subtopic {s}"
        ax.scatter(*P.T, s=32, c=scol[s], ec=BLACK, lw=.5, alpha=.95,
                   label=f"S{s} ({kw_label}, n={len(P)})", zorder=4)
    ax.legend(loc="lower left", frameon=True, facecolor="#05070b", edgecolor="#333", labelcolor=WHITE, fontsize=8.5)
    ax.set_title("Where the 118-record screened migrant queue sits in the full corpus", color=WHITE, fontsize=12, loc="left")

    ax2 = fig.add_axes([.58, .1, .39, .78]); ax2.set_facecolor(BLACK)
    yrs = list(range(2015, 2027))
    bottom = np.zeros(len(yrs))
    yrows = []
    for s in subs:
        c = Counter(years[sid == s])
        vals = np.array([c.get(y, 0) for y in yrs])
        kw_label = short(sub_names[s]["machine_keywords"], 2) if s in sub_names else f"subtopic {s}"
        ax2.bar(yrs, vals, bottom=bottom, color=scol[s], width=.75, label=f"S{s} {kw_label}")
        bottom += vals
        for y, v in zip(yrs, vals):
            yrows.append(dict(subtopic_id=s, year=y, records=int(v)))
    for s in ax2.spines.values():
        s.set_color("#333")
    ax2.tick_params(colors=WHITE); ax2.set_xticks(yrs); ax2.set_xticklabels([str(y + 543) for y in yrs], rotation=60, fontsize=8)
    ax2.set_ylabel("screened candidate records (raw count)", color=WHITE)
    ax2.set_title("Raw counts per year (no percentages; 2558 and 2569 partial)", color=WHITE, fontsize=12, loc="left")
    ax2.grid(axis="y", color="#222")
    fig.text(.03, .95, "Migrant story: screened candidate queue on discovered clusters", color=WHITE, fontsize=22, fontweight="bold")
    kw = " | ".join(f"S{s}: {short(sub_names[s]['machine_keywords'], 2)}" for s in subs if s in sub_names and s != -1)
    fig.text(.03, .915, f"{len(pts)} screened candidates ({missing} unplaced) · subtopics (machine keywords): {kw}",
             color=YELLOW, fontsize=8.5)
    fig.text(.03, .035, "These are SCREENED CANDIDATES awaiting final editorial sign-off, not confirmed migrant fake news and not human-validated frames. "
             "Subtopics mix themes; an absent cluster is not proof a frame never existed.", color=GRAY, fontsize=9)
    fig.text(.97, .035, "FAKE NEWS LAB × PRACHATAI", color=RED, fontsize=9, fontweight="bold", ha="right")
    fig.savefig(ASSETS / "real_clusters_story2.png", facecolor=BLACK)
    plt.close(fig)
    with open(OUT_RUN / "story2_subtopic_year_counts.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["subtopic_id", "year", "records"]); w.writeheader(); w.writerows(yrows)

    manifest = dict(
        inputs={str(p.relative_to(ROOT)): sha(p) for p in [RUN / "unique_embeddings.npy", RUN / "assignments.csv", RUN / "topics.csv",
                                    RUN / "migrant_screened_assignments.csv", RUN / "migrant_screened_topics.csv"]},
        umap2d=dict(n_neighbors=15, min_dist=0.1, metric="cosine", random_state=42, display_only=True),
        story1=dict(records=total_records, unique_texts=len(unique), clusters_incl_noise=len(topics), labelled=shown),
        story2=dict(candidates=len(sub), placed=len(pts), unplaced=missing, subtopics=len(subs)),
        note="machine keywords only; human labels pending; layout not quantitative")
    (OUT_RUN / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str))
    print("ok", manifest["story1"], manifest["story2"])


if __name__ == "__main__":
    main()
