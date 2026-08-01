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
import _brand  # noqa: E402

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
# verdict colours are palette roles: red = alert, yellow = indicator,
# white = plain statement, grey = residual
BUCKET_COLOR = {"false": "var(--fnl-red)", "misleading": "var(--fnl-yellow)",
                "true": "var(--fnl-white)", "other": "var(--fnl-gray)"}
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

# All visual styling now comes from assets/brand/fnl-design-system.css (see
# section 06 of that file, which styles exactly the class names this template
# emits). Nothing report-specific is left to override.


def render(cfg: dict, records: list[dict], *, economy: bool = False) -> str:
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
        f'<p style="margin-bottom:6px;"><strong style="color:var(--fnl-red);">{markers[i]}</strong> {f}</p>'
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

    return _brand.document(
        f'รายงานสถานการณ์ข่าวลวง — {cfg["slug"]}',
        f"""

  <button class="dl-btn" onclick="window.print()">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    ดาวน์โหลด PDF
  </button>

  <div class="page">
    <div class="rpt-header">
      <div class="rpt-brand">{_brand.mark(30)}<span>{_brand.ORG_TH} · {_brand.ORG_EN}</span></div>
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
        <p class="fnl-meta fnl-meta--tight" style="margin-top:6px;">
          ข้อมูลจาก {n_src} หน่วยงานตรวจสอบข้อเท็จจริง<br>
          ครอบคลุมทั้งหน่วยงานรัฐ (AFNC) และภาคประชาสังคม
        </p>
      </div>
      <div>
        <div class="sec-title">ข้อค้นพบสำคัญ {len(findings[:9])} ประการ</div>
        <div style="font-size:var(--fnl-fs-small); line-height:1.65;">
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
""",
        economy=economy)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build an Issue Focus Report")
    ap.add_argument("topic", nargs="?", help="topic slug in scripts/issue_topics/ or a path to a config JSON")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", help="output HTML path (default data/reports/<slug>_report.html)")
    ap.add_argument("--publish", help="also copy the finished report to this path (e.g. the web-served folder)")
    ap.add_argument("--list", action="store_true", help="list available topics")
    ap.add_argument("--print-economy", action="store_true",
                    help="render the opt-in light variant instead of the brand's "
                         "black base — for desk printing only")
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

    html = render(cfg, records, economy=args.print_economy)
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
