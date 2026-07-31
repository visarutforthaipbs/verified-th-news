# -*- coding: utf-8 -*-
"""Generate an Issue Focus Report (SKU): a 2-page A4 HTML deep-dive on one
misinformation topic, driven by a topic config in scripts/issue_topics/.

Each topic config defines the keyword filter, a category taxonomy, and the
analyst-written insight/findings slots; everything quantitative (stat pills,
yearly timeline, category bars, trend matrix, source distribution, example
cases) is computed from the database at build time.

Label policy follows the project invariant: verdicts whose origin is
`heuristic` are never presented as if the source issued them — they are
demoted to "อื่นๆ" in every client-facing count and never shown as examples.

Usage:
  python scripts/build_issue_report.py migrant
  python scripts/build_issue_report.py migrant --publish ~/Desktop/migrant_report.html
  python scripts/build_issue_report.py path/to/custom_topic.json
  python scripts/build_issue_report.py --list
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_dataset import normalize_verdict  # noqa: E402

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
from _freshness import assert_fresh  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TOPICS_DIR = Path(__file__).resolve().parent / "issue_topics"
DEFAULT_DB = ROOT / "data" / "th_verify.db"
OUT_DIR = ROOT / "data" / "reports"

SOURCE_NAMES = {
    "afnc": "ศูนย์ต่อต้านข่าวปลอม", "sure_share": "ชัวร์ก่อนแชร์",
    "cofact": "Cofact Thailand", "afp": "AFP Fact Check",
    "thaipbs": "Thai PBS Verify",
}
BUCKET_TH = {"false": "ปลอม", "misleading": "บิดเบือน", "true": "จริง", "other": "อื่นๆ"}
BUCKET_COLOR = {"false": "#c93b2b", "misleading": "#a86b1c", "true": "#21693e", "other": "#2c5980"}
THAI_MONTHS_ABBR = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def load_topic(name: str) -> dict:
    p = Path(name)
    if not p.suffix:
        p = TOPICS_DIR / f"{name}.json"
    if not p.exists():
        sys.exit(f"topic config not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def build_where(cfg: dict) -> tuple[str, list[str]]:
    """OR of: each keyword over title/claim/explanation, plus each combo
    (AND of any-of keyword groups over title/claim)."""
    clauses, params = [], []
    for kw in cfg.get("keywords_any", []):
        for field in ("title", "claim", "explanation"):
            clauses.append(f"{field} LIKE ?")
            params.append(f"%{kw}%")
    for combo in cfg.get("keyword_combos", []):
        groups = []
        for any_of in combo:
            alts = []
            for kw in any_of:
                for field in ("title", "claim"):
                    alts.append(f"{field} LIKE ?")
                    params.append(f"%{kw}%")
            groups.append("(" + " OR ".join(alts) + ")")
        clauses.append("(" + " AND ".join(groups) + ")")
    return " OR ".join(clauses), params


def fetch_records(con: sqlite3.Connection, cfg: dict) -> list[dict]:
    where, params = build_where(cfg)
    rows = con.execute(
        "SELECT id, source, source_url, title, claim, explanation, verdict,"
        "       verdict_origin, published_at "
        f"FROM fact_checks WHERE {where}", params).fetchall()

    cats = cfg["categories"]
    records = []
    for r in rows:
        text = " ".join(filter(None, (r["title"], r["claim"], r["explanation"]))).lower()
        matched = [c["name"] for c in cats if any(k in text for k in c["keywords"])]

        label = normalize_verdict(r["source"], r["verdict"] or "")
        if r["verdict_origin"] == "heuristic":
            label = "unknown"
        bucket = label if label in ("false", "misleading", "true") else "other"

        year = None
        if r["published_at"]:
            try:
                year = datetime.fromisoformat(
                    r["published_at"].replace("Z", "+00:00").split("+")[0]).year
            except ValueError:
                pass

        records.append({
            "title": r["title"], "source": r["source"], "url": r["source_url"],
            "bucket": bucket, "categories": matched, "year": year,
            "published_at": r["published_at"] or "",
        })
    records.sort(key=lambda r: r["published_at"], reverse=True)
    return records


# ── HTML rendering ──────────────────────────────────────────────────────

CSS = """
    @page { size: A4; margin: 18mm 20mm 16mm 20mm; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Sarabun', sans-serif; font-size: 9.5pt; color: #1a1a1a;
      line-height: 1.55; background: #f0efed;
      -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .page { width: 210mm; min-height: 297mm; background: #fff; margin: 12px auto;
      padding: 20mm 22mm 16mm 22mm; box-shadow: 0 2px 20px rgba(0,0,0,.08); position: relative; }
    .page + .page { page-break-before: always; }
    .dl-btn { position: fixed; bottom: 24px; right: 24px; z-index: 999; background: #2b1f1d;
      color: #fff; border: none; padding: 12px 24px; border-radius: 8px;
      font-family: 'Sarabun', sans-serif; font-size: 11pt; font-weight: 600; cursor: pointer;
      box-shadow: 0 4px 16px rgba(0,0,0,.2); transition: background .15s, transform .15s;
      display: flex; align-items: center; gap: 8px; }
    .dl-btn:hover { background: #8f3429; transform: translateY(-1px); }
    @media print {
      body { background: #fff; }
      .page { box-shadow: none; margin: 0; padding: 0; width: auto; min-height: auto; }
      .dl-btn { display: none !important; } }
    .rpt-header { border-bottom: 3px solid #2b1f1d; padding-bottom: 10px; margin-bottom: 14px; }
    .rpt-kicker { font-family: 'Outfit', sans-serif; font-size: 7pt; letter-spacing: 0.3em;
      text-transform: uppercase; color: #8f3429; font-weight: 600; margin-bottom: 2px; }
    .rpt-title { font-size: 18pt; font-weight: 700; line-height: 1.25; color: #1a1a1a; }
    .rpt-title em { font-style: normal; color: #8f3429; }
    .rpt-subtitle { font-size: 9pt; color: #666; margin-top: 4px; }
    .rpt-date { font-family: 'Outfit', sans-serif; font-size: 7.5pt; color: #999; margin-top: 4px; }
    .stats-row { display: flex; gap: 8px; margin-bottom: 14px; }
    .pill { flex: 1; border: 1px solid #e5e2dc; border-radius: 6px; padding: 8px 10px; text-align: center; }
    .pill-num { font-family: 'Outfit', sans-serif; font-size: 16pt; font-weight: 700; line-height: 1.1; }
    .pill-label { font-size: 7pt; color: #888; text-transform: uppercase;
      letter-spacing: .04em; margin-top: 2px; }
    .pill-pct { font-size: 7pt; color: #aaa; }
    .pill.c-total { border-top: 3px solid #2b1f1d; } .pill.c-total .pill-num { color: #2b1f1d; }
    .pill.c-false { border-top: 3px solid #c93b2b; } .pill.c-false .pill-num { color: #c93b2b; }
    .pill.c-mis { border-top: 3px solid #a86b1c; } .pill.c-mis .pill-num { color: #a86b1c; }
    .pill.c-true { border-top: 3px solid #21693e; } .pill.c-true .pill-num { color: #21693e; }
    .pill.c-other { border-top: 3px solid #2c5980; } .pill.c-other .pill-num { color: #2c5980; }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 14px; }
    .sec-title { font-size: 9pt; font-weight: 700; color: #2b1f1d; margin-bottom: 8px;
      padding-bottom: 3px; border-bottom: 1.5px solid #e5e2dc; }
    .timeline { display: flex; align-items: flex-end; justify-content: space-between;
      height: 125px; border-bottom: 1.5px solid #e5e2dc; padding-top: 16px; }
    .tb-col { display: flex; flex-direction: column; align-items: center; flex: 1; margin: 0 2px; }
    .tb-val { font-family: 'Outfit', sans-serif; font-size: 7pt; font-weight: 700;
      color: #444; margin-bottom: 2px; }
    .tb-bar { width: 100%; max-width: 32px; background: #c4a68a; border-radius: 2px 2px 0 0; }
    .tb-bar.sp { background: #8f3429; }
    .tb-yr { font-family: 'Outfit', sans-serif; font-size: 7pt; color: #888; margin-top: 3px; }
    .tl-note { font-size: 7pt; color: #aaa; margin-top: 3px; }
    .cb-row { display: flex; align-items: center; margin-bottom: 5px; font-size: 8.5pt; }
    .cb-label { width: 115px; color: #555; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .cb-track { flex: 1; height: 10px; background: #f0ede6; border-radius: 5px;
      overflow: hidden; margin: 0 6px; }
    .cb-fill { display: block; height: 100%; background: #8f3429; border-radius: 5px; }
    .cb-val { font-family: 'Outfit', sans-serif; font-weight: 700; width: 28px;
      text-align: right; font-size: 8pt; }
    .trend-tbl { width: 100%; border-collapse: collapse; font-size: 7.5pt; margin-top: 6px; }
    .trend-tbl th, .trend-tbl td { padding: 4px 6px; border: 1px solid #e5e2dc; text-align: center; }
    .trend-tbl th { background: #f7f4ee; font-weight: 600; font-size: 7pt; color: #444; }
    .trend-tbl td.yr { text-align: left; font-weight: 600; background: #faf9f7; }
    .trend-tbl td.hl { background: #fcecea; color: #8f3429; font-weight: 700; }
    .trend-tbl td.tot { background: #f7f4ee; font-weight: 600; }
    .insight { background: #faf8f3; border-left: 3px solid #8f3429; padding: 10px 12px;
      margin-top: 14px; border-radius: 0 4px 4px 0; font-size: 8.5pt; line-height: 1.6; color: #444; }
    .insight strong { color: #2b1f1d; }
    .src-row { display: flex; align-items: center; margin-bottom: 4px; font-size: 8pt; }
    .src-name { width: 120px; color: #555; }
    .src-bar { flex: 1; height: 8px; background: #f0ede6; border-radius: 4px;
      overflow: hidden; margin: 0 6px; }
    .src-fill { display: block; height: 100%; background: #2c5980; border-radius: 4px; }
    .src-val { font-family: 'Outfit', sans-serif; font-weight: 700; width: 28px;
      text-align: right; font-size: 7.5pt; }
    .method { margin-top: 14px; padding-top: 10px; border-top: 1.5px solid #e5e2dc;
      font-size: 7.5pt; color: #999; line-height: 1.55; }
    .method strong { color: #666; }
    .rpt-footer { margin-top: 12px; padding-top: 8px; border-top: 2px solid #2b1f1d;
      display: flex; justify-content: space-between; font-size: 7pt; color: #aaa; }
"""


def render(cfg: dict, records: list[dict]) -> str:
    total = len(records)
    if total == 0:
        sys.exit("no records matched this topic's keywords — nothing to report")

    now = datetime.now()
    buddhist = now.year + 543
    year_floor = cfg.get("year_floor", 2020)
    years = list(range(year_floor, now.year + 1))
    cats = cfg["categories"]
    cat_names = [c["name"] for c in cats]
    cat_short = {c["name"]: c["short"] for c in cats}

    buckets = Counter(r["bucket"] for r in records)
    fc, mc, tc = buckets["false"], buckets["misleading"], buckets["true"]
    oc = total - fc - mc - tc

    yearly = Counter(r["year"] for r in records if r["year"] in set(years))
    cat_counts = Counter(c for r in records for c in r["categories"])
    src_counts = Counter(r["source"] for r in records)
    matrix = {y: Counter() for y in years}
    for r in records:
        if r["year"] in matrix:
            matrix[r["year"]]["total"] += 1
            for c in r["categories"]:
                matrix[r["year"]][c] += 1

    # timeline bars
    max_y = max(yearly.values()) if yearly else 1
    tl = []
    for y in years:
        c = yearly.get(y, 0)
        h = max(2, round(c / max_y * 110))
        sp = " sp" if y >= now.year - 1 else ""
        star = "*" if y == now.year else ""
        tl.append(f'<div class="tb-col"><div class="tb-val">{c}{star}</div>'
                  f'<div class="tb-bar{sp}" style="height:{h}px"></div>'
                  f'<div class="tb-yr">{y + 543}</div></div>')

    # category bars
    sorted_cats = [(n, cat_counts[n]) for n in
                   sorted(cat_names, key=lambda n: -cat_counts[n])]
    max_c = sorted_cats[0][1] or 1
    cb = [f'<div class="cb-row"><span class="cb-label">{cat_short[n]}</span>'
          f'<span class="cb-track"><span class="cb-fill" style="width:{v / max_c * 100:.1f}%"></span></span>'
          f'<span class="cb-val">{v}</span></div>' for n, v in sorted_cats]

    # trend matrix rows
    trend = []
    for y in years:
        vals = [matrix[y][n] for n in cat_names]
        mx = max(vals) if vals else 0
        # The highlight attribute is built outside the f-string: escaped quotes
        # inside an f-string expression are a syntax error before Python 3.12
        # (PEP 701), and this project's venv is 3.11.
        highlight = ' class="hl"'
        cells = "".join(
            f'<td{highlight if v == mx and mx > 0 else ""}>{v}</td>' for v in vals)
        trend.append(f'<tr><td class="yr">พ.ศ. {y + 543}</td>{cells}'
                     f'<td class="tot"><strong>{matrix[y]["total"]}</strong></td></tr>')
    trend_head = "".join(f"<th>{c.get('th', c['short'])}</th>" for c in cats)

    # source bars
    sb = []
    for src, cnt in src_counts.most_common():
        name = SOURCE_NAMES.get(src, src)
        sb.append(f'<div class="src-row"><span class="src-name">{name}</span>'
                  f'<span class="src-bar"><span class="src-fill" style="width:{cnt / total * 100:.1f}%"></span></span>'
                  f'<span class="src-val">{cnt}</span></div>')

    # findings (analyst slots, with computed fallback)
    findings = cfg.get("findings_html") or [
        f"ตรวจสอบแล้ว {total} คดี เป็นข่าวปลอม {fc / total * 100:.0f}%",
        f"ประเด็นที่พบมากที่สุด: {cat_short[sorted_cats[0][0]]} ({sorted_cats[0][1]} เรื่อง)",
        f"แหล่งตรวจสอบหลัก: {SOURCE_NAMES.get(src_counts.most_common(1)[0][0], '-')}",
    ]
    markers = "①②③④⑤⑥⑦⑧⑨"
    fh = "".join(
        f'<p style="margin-bottom:6px;"><strong style="color:#8f3429;">{markers[i]}</strong> {f}</p>'
        for i, f in enumerate(findings[:9]))

    insight = cfg.get("insight_html") or (
        "<strong>💡 วิเคราะห์แนวโน้ม:</strong> <em>✍️ (ช่องสำหรับนักวิเคราะห์ — "
        "เติมบทวิเคราะห์แนวโน้มก่อนส่งลูกค้า)</em>")

    # example cases: labeled records only, newest first
    examples = [r for r in records if r["bucket"] != "other"][:8]
    ex_rows = "".join(
        f'<tr><td style="text-align:left">{r["title"][:75]}{"…" if len(r["title"]) > 75 else ""}</td>'
        f'<td style="color:{BUCKET_COLOR[r["bucket"]]}">{BUCKET_TH[r["bucket"]]}</td>'
        f'<td>{cat_short.get(r["categories"][0], "-") if r["categories"] else "-"}</td>'
        f'<td>{SOURCE_NAMES.get(r["source"], r["source"])}</td></tr>'
        for r in examples)

    date_str = f"{now.day:02d}/{now.month:02d}/{buddhist}"
    partial_note = (f'* ข้อมูลปี พ.ศ. {buddhist} ถึง {now.day} '
                    f'{THAI_MONTHS_ABBR[now.month - 1]} เท่านั้น')
    n_src = len(src_counts)

    def pct(n: int) -> str:
        return f"{n / total * 100:.1f}%"

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>รายงานสถานการณ์ข่าวลวง — {cfg["slug"]}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700&family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
  <style>{CSS}</style>
</head>
<body>

  <button class="dl-btn" onclick="window.print()">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    ดาวน์โหลด PDF
  </button>

  <div class="page">
    <div class="rpt-header">
      <div class="rpt-kicker">{cfg["kicker"]}</div>
      <h1 class="rpt-title">{cfg["title_html"]}</h1>
      <p class="rpt-subtitle">วิเคราะห์จากฐานข้อมูลการตรวจสอบข้อเท็จจริง {total} คดี ระหว่างปี พ.ศ. {year_floor + 543} – {buddhist}</p>
      <p class="rpt-date">ข้อมูล ณ วันที่ {date_str} | สร้างโดย TH Verify Database Engine</p>
    </div>

    <div class="stats-row">
      <div class="pill c-total"><div class="pill-num">{total}</div><div class="pill-label">คดีทั้งหมด</div></div>
      <div class="pill c-false"><div class="pill-num">{fc}</div><div class="pill-label">ข่าวปลอม</div><div class="pill-pct">{pct(fc)}</div></div>
      <div class="pill c-mis"><div class="pill-num">{mc}</div><div class="pill-label">บิดเบือน</div><div class="pill-pct">{pct(mc)}</div></div>
      <div class="pill c-true"><div class="pill-num">{tc}</div><div class="pill-label">ข่าวจริง</div><div class="pill-pct">{pct(tc)}</div></div>
      <div class="pill c-other"><div class="pill-num">{oc}</div><div class="pill-label">อื่นๆ</div><div class="pill-pct">{pct(oc)}</div></div>
    </div>

    <div class="two-col">
      <div>
        <div class="sec-title">สถิติรายปี (พ.ศ. {year_floor + 543} – {buddhist})</div>
        <div class="timeline">
          {"".join(tl)}
        </div>
        <div class="tl-note">{partial_note}</div>
      </div>
      <div>
        <div class="sec-title">สัดส่วนประเภทข่าวลวง</div>
        <div style="margin-top:6px;">
          {"".join(cb)}
        </div>
      </div>
    </div>

    <div class="sec-title">ตารางแนวโน้มประเด็นข่าวลวงรายปี</div>
    <table class="trend-tbl">
      <thead><tr><th style="text-align:left">ปี</th>{trend_head}<th>รวม</th></tr></thead>
      <tbody>
        {"".join(trend)}
      </tbody>
    </table>

    <div class="insight">{insight}</div>
  </div>

  <div class="page">
    <div class="rpt-header" style="margin-bottom:12px;">
      <div class="rpt-kicker">{cfg["kicker"]} (ต่อ)</div>
      <h1 class="rpt-title" style="font-size:13pt;">{cfg.get("page2_title", "ข้อมูลเชิงลึกและตัวอย่างข่าวลวงที่พบบ่อย")}</h1>
    </div>

    <div class="two-col">
      <div>
        <div class="sec-title">แหล่งข้อมูลที่ตรวจสอบ</div>
        <div style="margin-top:6px;">
          {"".join(sb)}
        </div>
        <p style="font-size:7pt; color:#aaa; margin-top:6px;">
          ข้อมูลจาก {n_src} หน่วยงานตรวจสอบข้อเท็จจริง<br>
          ครอบคลุมทั้งหน่วยงานรัฐ (AFNC) และภาคประชาสังคม
        </p>
      </div>
      <div>
        <div class="sec-title">ข้อค้นพบสำคัญ {len(findings[:9])} ประการ</div>
        <div style="font-size:8.5pt; color:#444; line-height:1.65;">
          {fh}
        </div>
      </div>
    </div>

    <div class="sec-title">ตัวอย่างข่าวลวงที่พบบ่อย (จากฐานข้อมูลจริง)</div>
    <table class="trend-tbl" style="font-size:8pt; margin-bottom:12px;">
      <thead>
        <tr>
          <th style="text-align:left;width:55%">หัวข้อข่าวลวง</th>
          <th style="width:12%">ผลตรวจสอบ</th>
          <th style="width:15%">ประเด็น</th>
          <th style="width:18%">แหล่งตรวจสอบ</th>
        </tr>
      </thead>
      <tbody>
        {ex_rows}
      </tbody>
    </table>

    <div class="method">
      <strong>ระเบียบวิธี:</strong> รายงานฉบับนี้ใช้ข้อมูลจากฐานข้อมูล TH Verify ซึ่งรวบรวมผลการตรวจสอบข้อเท็จจริงจาก 5 หน่วยงาน
      ได้แก่ ศูนย์ต่อต้านข่าวปลอม (AFNC), Cofact Thailand, Thai PBS Verify, ชัวร์ก่อนแชร์ (MCOT), และ AFP Fact Check
      {cfg.get("methodology_note", "")}
      การจัดหมวดหมู่ดำเนินการโดยอัตโนมัติด้วยการวิเคราะห์คำสำคัญ (keyword-based classification) ทำให้บางคดีอาจถูกจัดอยู่ในมากกว่า 1 หมวดหมู่
      คำตัดสินที่มาจากการเดาด้วยระบบอัตโนมัติ (heuristic) จะถูกจัดเป็น "อื่นๆ" เสมอ ไม่นับเป็นคำตัดสินของหน่วยงาน
      <br><br>
      <strong>ข้อจำกัด:</strong> ข้อมูลครอบคลุมเฉพาะคดีที่ได้รับการตรวจสอบโดยหน่วยงานข้างต้นเท่านั้น อาจไม่ได้สะท้อนข่าวลวงทั้งหมดที่แพร่หลายในสังคม
      ข้อมูลปี พ.ศ. {buddhist} เป็นข้อมูลบางส่วน (ถึง {now.day} {THAI_MONTHS_ABBR[now.month - 1]} พ.ศ. {buddhist})
    </div>

    <div class="rpt-footer">
      <span>© พ.ศ. {buddhist} TH Verify Database Engine</span>
      <span>รายงานสร้างอัตโนมัติ — ห้ามใช้อ้างอิงทางกฎหมาย</span>
    </div>
  </div>

</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Build an Issue Focus Report")
    ap.add_argument("topic", nargs="?", help="topic slug in scripts/issue_topics/ or a path to a config JSON")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", help="output HTML path (default data/reports/<slug>_report.html)")
    ap.add_argument("--publish", help="also copy the finished report to this path (e.g. the web-served folder)")
    ap.add_argument("--list", action="store_true", help="list available topics")
    args = ap.parse_args()

    if args.list or not args.topic:
        for p in sorted(TOPICS_DIR.glob("*.json")):
            print(p.stem)
        if not args.topic:
            sys.exit(0 if list(TOPICS_DIR.glob("*.json")) else "no topics defined yet")
        return

    cfg = load_topic(args.topic)
    con = sqlite3.connect(args.db)
    assert_fresh(con)
    con.row_factory = sqlite3.Row
    try:
        records = fetch_records(con, cfg)
    finally:
        con.close()

    html = render(cfg, records)
    out = Path(args.out) if args.out else OUT_DIR / f"{cfg['slug']}_report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(records)} records)")

    if args.publish:
        dest = Path(args.publish).expanduser()
        shutil.copy2(out, dest)
        print(f"published to {dest}")


if __name__ == "__main__":
    main()
