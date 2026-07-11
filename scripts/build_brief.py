"""Generate the monthly misinformation brief (Thai Misinfo Brief SKU).

Produces an editable Markdown skeleton in data/briefs/brief_YYYY-MM.md with
every quantitative section auto-filled from the database:

  - volume of new fact-checks by source and verdict
  - hot categories vs the previous month
  - narrative clusters (semantically grouped claims of the month)
  - recirculating hoaxes (claims re-debunked this month, first seen earlier)
  - AI-generated-content items
  - scam-pattern counts
  - appendix of all new false/misleading claims with source links

Analyst commentary slots are marked with `> ✍️`. Everything cites and links
to the original publisher (attribution is a product requirement).

Usage:
  python scripts/build_brief.py                # previous complete month
  python scripts/build_brief.py --month 2026-06
  python scripts/build_brief.py --month 2026-07 --no-clusters   # fast run
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_dataset import clean_claim, dedup_key, normalize_verdict  # noqa: E402

SOURCE_NAMES = {
    "afnc": "ศูนย์ต่อต้านข่าวปลอม", "sure_share": "ชัวร์ก่อนแชร์",
    "cofact": "Cofact", "afp": "AFP Fact Check", "thaipbs": "Thai PBS Verify",
}
LABEL_TH = {
    "false": "ข่าวปลอม", "true": "ข่าวจริง", "misleading": "บิดเบือน",
    "altered_media": "สื่อดัดแปลง/AI", "scam_alert": "เตือนภัยมิจฉาชีพ",
    "satire": "เสียดสี", "unknown": "ไม่ระบุ",
}
AI_RE = re.compile(r"AI|เอไอ|ปัญญาประดิษฐ์|deepfake|ดีพเฟค", re.IGNORECASE)
SCAM_PATTERNS = {
    "แอบอ้างหน่วยงานรัฐ/ธนาคาร": re.compile(r"ธนาคาร|กระทรวง|กรม|เพจปลอม|แอบอ้าง|ตำรวจ"),
    "ชวนลงทุน/หุ้น": re.compile(r"ลงทุน|หุ้น|ปันผล|ผลตอบแทน|เทรด"),
    "เงินกู้/สินเชื่อ": re.compile(r"เงินกู้|สินเชื่อ|กู้เงิน"),
    "สุขภาพ/ยารักษาโรค": re.compile(r"รักษา|โรค|มะเร็ง|สมุนไพร|ยา"),
    "แอป/ลิงก์อันตราย": re.compile(r"แอปพลิเคชัน|แอป|ลิงก์|ดาวน์โหลด|SMS"),
    "สิทธิ/เงินช่วยเหลือรัฐ": re.compile(r"เงินดิจิทัล|เยียวยา|ลงทะเบียน|สิทธิ|บัตรสวัสดิการ"),
}
NEG_LABELS = {"false", "misleading", "altered_media", "scam_alert"}


def month_bounds(ym: str) -> tuple[str, str]:
    y, m = int(ym[:4]), int(ym[5:7])
    nxt = f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"
    return f"{ym}-01", f"{nxt}-01"


def prev_month(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def fetch(con: sqlite3.Connection, start: str, end: str) -> list[dict]:
    rows = con.execute(
        "SELECT id, source, source_url, title, verdict, category, published_at,"
        "       verdict_origin "
        "FROM fact_checks WHERE published_at >= ? AND published_at < ? "
        "ORDER BY published_at",
        (start, end),
    ).fetchall()
    out = []
    for r in rows:
        label = normalize_verdict(r["source"], r["verdict"])
        # heuristic labels are keyword guesses - never present them in a
        # client-facing document as if the source issued that verdict
        if label != "unknown" and r["verdict_origin"] == "heuristic":
            label = "unknown"
        out.append({
            "id": r["id"], "source": r["source"], "url": r["source_url"],
            "claim": clean_claim(r["title"], r["source"]), "label": label,
            "category": r["category"], "date": (r["published_at"] or "")[:10],
        })
    return out


def cluster_claims(claims: list[dict]) -> list[list[dict]]:
    """Group this month's negative-label claims by embedding similarity.

    Union-find chains transitively, so a loose threshold merges everything
    into one blob; start at 0.93 and tighten until the largest cluster is
    a plausible narrative (< 15% of the month's claims).
    """
    import numpy as np
    from sentence_transformers import SentenceTransformer

    if len(claims) < 2:
        return []
    model = SentenceTransformer("intfloat/multilingual-e5-small")
    vecs = model.encode(["passage: " + c["claim"] for c in claims],
                        normalize_embeddings=True, batch_size=256)
    sims = vecs @ vecs.T
    max_size = max(4, int(len(claims) * 0.15))

    for threshold in (0.93, 0.94, 0.95, 0.96, 0.97):
        parent = list(range(len(claims)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i, j in zip(*np.where(np.triu(sims, 1) >= threshold)):
            ri, rj = find(int(i)), find(int(j))
            if ri != rj:
                parent[ri] = rj
        groups: defaultdict[int, list[dict]] = defaultdict(list)
        for idx in range(len(claims)):
            groups[find(idx)].append(claims[idx])
        clusters = sorted((g for g in groups.values() if len(g) >= 2),
                          key=len, reverse=True)
        if not clusters or len(clusters[0]) <= max_size:
            return clusters
    return clusters


def find_recirculating(claims: list[dict], month_start: str,
                       threshold: float = 0.95) -> list[tuple[dict, dict]]:
    """Claims of the month that closely match a fact-check published earlier.

    Uses the semantic index in data/index (catches mutated wording, e.g. the
    same loan scam with a different amount), so it needs `th-verify index`
    to have been run. Falls back to exact normalized-text matching if the
    index is missing.
    """
    if not claims:
        return []
    index_dir = Path("data/index")
    if (index_dir / "config.json").exists():
        import json

        import numpy as np
        from sentence_transformers import SentenceTransformer

        vecs = np.load(index_dir / "embeddings.npy")
        with open(index_dir / "meta.jsonl", encoding="utf-8") as f:
            meta = [json.loads(line) for line in f]
        old = np.array([i for i, m in enumerate(meta)
                        if (m["published_at"] or "")[:10] < month_start
                        and m["published_at"]])
        if len(old):
            model = SentenceTransformer("intfloat/multilingual-e5-small")
            q = model.encode(["passage: " + c["claim"] for c in claims],
                             normalize_embeddings=True, batch_size=256)
            sims = q @ vecs[old].T
            out = []
            for i, c in enumerate(claims):
                j = int(sims[i].argmax())
                if sims[i][j] >= threshold:
                    m = meta[old[j]]
                    out.append((c, {"date": (m["published_at"] or "")[:10],
                                    "url": m["url"],
                                    "claim": m["claim_text"],
                                    "score": float(sims[i][j])}))
            return sorted(out, key=lambda t: -t[1]["score"])
    # fallback: exact normalized text against the DB
    con = sqlite3.connect("data/th_verify.db")
    con.row_factory = sqlite3.Row
    hist: dict[str, dict] = {}
    for r in con.execute(
        "SELECT source, source_url, title, published_at FROM fact_checks "
        "WHERE published_at < ? ORDER BY published_at", (month_start,)
    ):
        k = dedup_key(clean_claim(r["title"], r["source"]))
        if k and k not in hist:
            hist[k] = {"date": (r["published_at"] or "")[:10],
                       "url": r["source_url"], "claim": r["title"], "score": 1.0}
    return [(c, hist[k]) for c in claims
            if (k := dedup_key(c["claim"])) in hist]


def li(c: dict) -> str:
    return (f"- {c['claim']} — [{SOURCE_NAMES.get(c['source'], c['source'])}]"
            f"({c['url']}) ({c['date']}, {LABEL_TH.get(c['label'], c['label'])})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM (default: previous complete month)")
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--no-clusters", action="store_true",
                    help="skip embedding clusters (faster)")
    args = ap.parse_args()

    if args.month:
        ym = args.month
    else:
        today = date.today()
        ym = prev_month(f"{today.year}-{today.month:02d}")

    start, end = month_bounds(ym)
    pm = prev_month(ym)
    pstart, pend = month_bounds(pm)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    cur = fetch(con, start, end)
    prev = fetch(con, pstart, pend)

    neg = [c for c in cur if c["label"] in NEG_LABELS]
    recirc = find_recirculating(neg, start)
    ai_items = [c for c in neg if AI_RE.search(c["claim"])]
    by_source = Counter(c["source"] for c in cur)
    by_label = Counter(c["label"] for c in cur)
    cat_cur = Counter(c["category"] for c in cur if c["category"])
    cat_prev = Counter(c["category"] for c in prev if c["category"])

    clusters = [] if args.no_clusters else cluster_claims(neg)

    L: list[str] = []
    L += [
        f"# Thai Misinfo Brief — {ym}",
        "",
        f"ช่วงข้อมูล: {start} ถึงสิ้นเดือน · จัดทำ {date.today().isoformat()}",
        "",
        "แหล่งข้อมูล: " + " · ".join(SOURCE_NAMES.values()),
        "",
        "> เอกสารนี้สรุปจากบันทึกการตรวจสอบข้อเท็จจริงที่เผยแพร่สาธารณะ พร้อมลิงก์ต้นทางทุกรายการ "
        "ระบบช่วยจัดกลุ่มและจัดลำดับเท่านั้น — ข้อสรุปทั้งหมดอ้างอิงผู้ตรวจสอบต้นทาง",
        "",
        "## 1. บทสรุปผู้บริหาร",
        "",
        "> ✍️ [นักวิเคราะห์เขียน 3–5 ย่อหน้า: ภาพรวมเดือนนี้ ประเด็นที่ต้องจับตา ข้อเสนอแนะ]",
        "",
        "## 2. ภาพรวมตัวเลข",
        "",
        f"การตรวจสอบใหม่เดือนนี้ **{len(cur)} รายการ** "
        f"(เดือนก่อนหน้า {len(prev)} รายการ, "
        f"{'เพิ่มขึ้น' if len(cur) >= len(prev) else 'ลดลง'} "
        f"{abs(len(cur) - len(prev))})",
        "",
        "| แหล่ง | รายการ |", "|---|---|",
        *[f"| {SOURCE_NAMES.get(s, s)} | {n} |" for s, n in by_source.most_common()],
        "",
        "| ผลตรวจสอบ | รายการ |", "|---|---|",
        *[f"| {LABEL_TH.get(k, k)} | {v} |" for k, v in by_label.most_common()],
        "",
        "## 3. หมวดหมู่ร้อนแรง (เทียบเดือนก่อน)",
        "",
        "| หมวด | เดือนนี้ | เดือนก่อน | เปลี่ยนแปลง |", "|---|---|---|---|",
    ]
    for cat, n in cat_cur.most_common(8):
        d = n - cat_prev.get(cat, 0)
        L.append(f"| {cat} | {n} | {cat_prev.get(cat, 0)} | {'+' if d >= 0 else ''}{d} |")
    L += ["", "> ✍️ [วิเคราะห์การเปลี่ยนแปลง: หมวดใดพุ่งขึ้น เพราะเหตุการณ์อะไร]", ""]

    L += ["## 4. กลุ่มประเด็นเด่นประจำเดือน", ""]
    if clusters:
        for i, g in enumerate(clusters[:8], 1):
            srcs = ", ".join(sorted({SOURCE_NAMES.get(c["source"], c["source"]) for c in g}))
            L += [f"### 4.{i} {g[0]['claim'][:80]} ({len(g)} รายการ · {srcs})", ""]
            L += [li(c) for c in g[:5]]
            L += ["", "> ✍️ [บริบทของกลุ่มประเด็นนี้]", ""]
    else:
        L += ["_(ไม่ได้สร้างกลุ่มประเด็น — รันโดยไม่ใส่ --no-clusters เพื่อจัดกลุ่มอัตโนมัติ)_", ""]

    L += [f"## 5. ข่าวลวงเวียนซ้ำ ({len(recirc)} รายการ)", "",
          "คำกล่าวอ้างที่เคยถูกตรวจสอบมาก่อน และกลับมาระบาดใหม่ในเดือนนี้:", ""]
    for c, first in recirc[:15]:
        L.append(f"- {c['claim']} — ตรวจสอบซ้ำ {c['date']} ([ลิงก์]({c['url']})) · "
                 f"ใกล้เคียงกับที่ตรวจไว้เมื่อ {first['date']} "
                 f"([ตรวจสอบเดิม]({first['url']}), ความคล้าย {first['score']:.0%})")
    L += ["", "> ✍️ [เหตุใดประเด็นเหล่านี้จึงกลับมา / ข้อสังเกต]", ""]

    L += [f"## 6. คอนเทนต์สร้างด้วย AI ({len(ai_items)} รายการ)", ""]
    L += [li(c) for c in ai_items[:12]]
    L += ["", "## 7. รูปแบบกลลวงที่พบ", "",
          "| รูปแบบ | รายการ | ตัวอย่าง |", "|---|---|---|"]
    for name, rx in SCAM_PATTERNS.items():
        hits = [c for c in neg if rx.search(c["claim"])]
        ex = hits[0]["claim"][:60] + "…" if hits else "—"
        L.append(f"| {name} | {len(hits)} | {ex} |")
    L += ["", "## 8. ข้อเสนอแนะการสื่อสาร", "",
          "> ✍️ [คำแนะนำสำหรับลูกค้า: ควรเตือนภัยเรื่องใด ช่องทางไหน ข้อความตัวอย่าง]", "",
          f"## ภาคผนวก ก. รายการตรวจสอบเชิงลบทั้งหมดเดือนนี้ ({len(neg)} รายการ)", ""]
    L += [li(c) for c in neg]
    L += ["", "---",
          "_จัดทำโดย TH Verify — ทุกข้อสรุปอ้างอิงผู้ตรวจสอบต้นทางตามลิงก์ที่แนบ "
          "เอกสารนี้เป็นเครื่องมือช่วยวิเคราะห์ ไม่ใช่คำตัดสินอัตโนมัติ_"]

    out_dir = Path("data/briefs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"brief_{ym}.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {out}")
    print(f"records={len(cur)} negative={len(neg)} recirculating={len(recirc)} "
          f"ai={len(ai_items)} clusters={len(clusters)}")


if __name__ == "__main__":
    main()
