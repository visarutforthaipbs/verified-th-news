#!/usr/bin/env python3
"""Interactive explorer for the discovered clusters (runs/20260908_bertopic_v001 on the 14,429 records).

Every dot = one unique claim text (13,377). Position = the display-only 2-D UMAP in runs/20261004_viz_v001/umap2d.npy
(axes have no units). Topic = the BERTopic/HDBSCAN topic_id in assignments.csv. Names = machine keywords; the eight
topics used in the Story 1 article also show the author's draft name and the human/AI purity read (from the review sheets).
Output: runs/20261007_cluster_explorer_v001/cluster_explorer.html (self-contained; light/dark; zoom, search, hover, table).
"""
import csv, json, hashlib
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

csv.field_size_limit(10**9)
ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "runs/20260908_bertopic_v001"
OUT = ROOT / "runs/20261007_cluster_explorer_v001"
RECORDS = ROOT / "data/reports/journalist_handoff_2026-09-08/02_false_misleading_altered_records.csv"
UMAP2D = ROOT / "runs/20261004_viz_v001/umap2d.npy"
SRC = {"sure_share": "ชัวร์ก่อนแชร์", "afnc": "AFNC", "afp": "AFP ประเทศไทย", "cofact": "Cofact", "thaipbs": "Thai PBS Verify"}
DRAFT = {0: "สุขภาพ อาหาร และเรื่องใกล้ตัว", 1: "ชวนลงทุน–ปันผล", 2: "รับทำใบขับขี่ออนไลน์", 4: "ป้องกัน/รักษาโควิด", 6: "ทหารและชายแดนไทย–กัมพูชา",
         7: "พบผู้ติดเชื้อ/การระบาด", 11: "อ้างคืนเงินให้ผู้เสียหาย", 18: "วัคซีน"}


def rd(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def purity():
    out = {}
    for p in (ROOT / "runs/20261004_story1_by_publisher_v001/topic0_samples.csv", ROOT / "runs/20261004_purity_v001/named_topic_samples.csv"):
        c = defaultdict(Counter)
        for r in rd(p):
            c[int(r["topic_id"])][r["human_pure"]] += 1
        for t, v in c.items():
            out[t] = {"yes": v["1"], "no": v["0"], "unsure": v["?"]}
    return out


def main():
    recs = rd(RECORDS)
    unique = list(dict.fromkeys(r["claim_text"] for r in recs))
    Y = np.load(UMAP2D)
    assert Y.shape == (len(unique), 2), (Y.shape, len(unique))
    idx = {t: i for i, t in enumerate(unique)}
    asg = rd(RUN / "assignments.csv")
    assert len(asg) == len(recs) == 14429
    per = defaultdict(list)
    for r in asg:
        per[r["claim_text"]].append(r)
    topics = {int(r["topic_id"]): r for r in rd(RUN / "topics.csv")}
    pur = purity()
    pts = []
    for i, t in enumerate(unique):
        rs = per[t]
        tid = {int(r["topic_id"]) for r in rs}; assert len(tid) == 1
        srcs = Counter(r["source"] for r in rs)
        first = min(rs, key=lambda r: r["date"])
        pts.append([round(float(Y[i, 0]), 2), round(float(Y[i, 1]), 2), tid.pop(), list(SRC).index(srcs.most_common(1)[0][0]), int(first["year"]), len(rs), t, first["id"], first["url"], int(first["year"]), int(max(r["year"] for r in rs)), "|".join(f"{k}:{v}" for k, v in srcs.most_common())])
    tinfo = []
    for t, r in sorted(topics.items(), key=lambda kv: -int(kv[1]["records"])):
        rows = [x for x in asg if int(x["topic_id"]) == t]
        by_year = Counter(int(x["year"]) for x in rows); by_src = Counter(x["source"] for x in rows)
        tinfo.append({"id": t, "kw": r["machine_keywords"], "records": int(r["records"]), "share": float(r["share_pct"]), "unique": int(r["unique_texts"]),
                      "years": {str(y): by_year[y] for y in range(2015, 2027)}, "src": {k: by_src[k] for k in SRC if by_src[k]},
                      "draft": DRAFT.get(t, ""), "purity": pur.get(t)})
    assert sum(x["records"] for x in tinfo) == 14429
    data = {"pts": pts, "topics": tinfo, "src": [{"key": k, "label": v} for k, v in SRC.items()], "n_records": 14429}
    tpl = (ROOT / "assets/cluster_explorer/template.html").read_text(encoding="utf-8")
    html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cluster_explorer.html").write_text(html, encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps({
        "inputs": {"records": str(RECORDS.relative_to(ROOT)), "assignments": "runs/20260908_bertopic_v001/assignments.csv", "topics": "runs/20260908_bertopic_v001/topics.csv",
                   "umap2d": str(UMAP2D.relative_to(ROOT)), "umap2d_sha256": hashlib.sha256(UMAP2D.read_bytes()).hexdigest()},
        "points": len(pts), "records": 14429, "topics_incl_noise": len(tinfo),
        "note": "positions are display-only 2-D UMAP (seed 42); clustering was done on 10-D UMAP; names are machine keywords; draft names and purity read apply to 8 topics only"},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT / "cluster_explorer.html", len(html) // 1024, "KB;", len(pts), "points")


if __name__ == "__main__":
    main()
