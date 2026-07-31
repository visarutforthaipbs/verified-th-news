# -*- coding: utf-8 -*-
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import Counter

db_path = "/Users/visarutsankham/th-verify/data/th_verify.db"

# Connect to database
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Query to find relevant fact checks
query = """
SELECT id, source, source_url, title, claim, explanation, verdict, published_at
FROM fact_checks
WHERE 
  title LIKE '%ต่างด้าว%' OR claim LIKE '%ต่างด้าว%' OR explanation LIKE '%ต่างด้าว%' OR
  title LIKE '%ผู้อพยพ%' OR claim LIKE '%ผู้อพยพ%' OR explanation LIKE '%ผู้อพยพ%' OR
  title LIKE '%โรฮิงญา%' OR claim LIKE '%โรฮิงญา%' OR explanation LIKE '%โรฮิงญา%' OR
  title LIKE '%แรงงานต่าง%' OR claim LIKE '%แรงงานต่าง%' OR explanation LIKE '%แรงงานต่าง%' OR
  title LIKE '%คนต่างชาติ%' OR claim LIKE '%คนต่างชาติ%' OR explanation LIKE '%คนต่างชาติ%' OR
  title LIKE '%migrant%' OR claim LIKE '%migrant%' OR
  title LIKE '%immigrant%' OR claim LIKE '%immigrant%' OR
  title LIKE '%refugee%' OR claim LIKE '%refugee%' OR
  (
    (title LIKE '%แรงงาน%' OR claim LIKE '%แรงงาน%') AND 
    (title LIKE '%พม่า%' OR claim LIKE '%พม่า%' OR title LIKE '%กัมพูชา%' OR claim LIKE '%กัมพูชา%' OR title LIKE '%ลาว%' OR claim LIKE '%ลาว%' OR title LIKE '%เขมร%' OR claim LIKE '%เขมร%')
  )
"""

rows = conn.execute(query).fetchall()

records = []
for r in rows:
    rec = dict(r)
    text = (rec['title'] + " " + (rec['claim'] or "") + " " + (rec['explanation'] or "")).lower()
    
    cats = []
    if any(k in text for k in ['สิทธิ', 'บัตรประชารัฐ', 'สวัสดิการ', 'รักษาฟรี', 'สิทธิรักษา', 'เงินอุดหนุน', 'เบี้ย', 'เงินช่วยเหลือ', 'welfare', 'benefit']):
        cats.append("สิทธิประโยชน์และสวัสดิการสังคม")
    if any(k in text for k in ['อาชีพ', 'แย่งงาน', 'ทำงาน', 'ธุรกิจ', 'ค้าขาย', 'แย่งอาชีพ', 'job', 'work', 'business']):
        cats.append("การแย่งอาชีพและการแย่งงาน")
    if any(k in text for k in ['เลือกตั้ง', 'บัตรประชาชน', 'สัญชาติ', 'เลือกตั้ง', 'สิทธิเลือกตั้ง', 'citizen', 'vote', 'nationality']):
        cats.append("สัญชาติและสิทธิทางการเมือง")
    if any(k in text for k in ['อาชญากรรม', 'ทำร้าย', 'ปล้น', 'ฆ่า', 'ลักขโมย', 'ยาเสพติด', 'ตบ', 'ทะเลาะ', 'crime', 'violence']):
        cats.append("อาชญากรรมและความปลอดภัยสาธารณะ")
    if any(k in text for k in ['หลบหนี', 'ลักลอบ', 'เข้าเมือง', 'ข้ามแดน', 'ทะลัก', 'illegal border', 'smuggle']):
        cats.append("การลักลอบเข้าเมืองและชายแดน")
    if any(k in text for k in ['โควิด', 'โรค', 'ระบาด', 'ติดเชื้อ', 'วัคซีน', 'disease', 'outbreak', 'covid']):
        cats.append("โรคระบาดและสาธารณสุข")
    if any(k in text for k in ['โรฮิงญา', 'rohingya']):
        cats.append("ประเด็นชาวโรฮิงญา")
        
    if not cats:
        cats.append("ประเด็นอื่นๆ")
        
    rec['categories'] = cats
    records.append(rec)

# Sort records by date descending
records.sort(key=lambda r: r.get('published_at') or '', reverse=True)

# ── Pre-compute stats in Python for hardcoding into the report ──
total = len(records)

def get_verdict(v):
    v = v.lower()
    if 'ปลอม' in v or 'false' in v or 'เท็จ' in v: return 'false'
    if 'จริง' in v or 'true' in v: return 'true'
    if 'บิดเบือน' in v or 'misleading' in v: return 'misleading'
    return 'other'

verdict_counts = Counter(get_verdict(r['verdict']) for r in records)
fc, mc, tc, oc = verdict_counts['false'], verdict_counts['misleading'], verdict_counts['true'], verdict_counts['other']

# Yearly counts
yearly = Counter()
for r in records:
    if r['published_at']:
        try:
            yr = datetime.fromisoformat(r['published_at'].replace('Z','+00:00').split('+')[0]).year
            if 2020 <= yr <= 2026:
                yearly[yr] += 1
        except: pass

# Category counts
cat_keys = [
    "การแย่งอาชีพและการแย่งงาน",
    "สัญชาติและสิทธิทางการเมือง",
    "สิทธิประโยชน์และสวัสดิการสังคม",
    "การลักลอบเข้าเมืองและชายแดน",
    "โรคระบาดและสาธารณสุข",
    "อาชญากรรมและความปลอดภัยสาธารณะ",
]
cat_short = {
    "การแย่งอาชีพและการแย่งงาน": "แย่งงาน/อาชีพ",
    "สัญชาติและสิทธิทางการเมือง": "สัญชาติ/การเมือง",
    "สิทธิประโยชน์และสวัสดิการสังคม": "สวัสดิการ/รักษาพยาบาล",
    "การลักลอบเข้าเมืองและชายแดน": "ลักลอบเข้าเมือง/ชายแดน",
    "โรคระบาดและสาธารณสุข": "โรคระบาด/สาธารณสุข",
    "อาชญากรรมและความปลอดภัยสาธารณะ": "อาชญากรรม/ความมั่นคง",
}
cat_counts = Counter()
for r in records:
    for c in r['categories']:
        if c in cat_keys:
            cat_counts[c] += 1
sorted_cats = sorted(cat_counts.items(), key=lambda x: -x[1])

# Source counts
src_counts = Counter(r['source'] for r in records)
src_names = {'afnc': 'ศูนย์ต่อต้านข่าวปลอม', 'cofact': 'Cofact Thailand', 'thaipbs': 'Thai PBS Verify', 'sure_share': 'ชัวร์ก่อนแชร์', 'afp': 'AFP Fact Check'}

# Yearly × Category matrix
years = list(range(2020, 2027))
matrix = {}
for y in years:
    matrix[y] = {c: 0 for c in cat_keys}
    matrix[y]['total'] = 0
for r in records:
    if r['published_at']:
        try:
            yr = datetime.fromisoformat(r['published_at'].replace('Z','+00:00').split('+')[0]).year
            if yr in matrix:
                matrix[yr]['total'] += 1
                for c in r['categories']:
                    if c in matrix[yr]:
                        matrix[yr][c] += 1
        except: pass

# Build trend table rows
def trend_rows_html():
    rows_html = []
    for y in years:
        rd = matrix[y]
        vals = [rd[c] for c in cat_keys]
        max_val = max(vals) if vals else 0
        cells = []
        for c in cat_keys:
            v = rd[c]
            cls = ' class="hl"' if v == max_val and max_val > 0 else ''
            cells.append(f'<td{cls}>{v}</td>')
        rows_html.append(f'<tr><td class="yr">พ.ศ. {y+543}</td>{"".join(cells)}<td class="tot"><strong>{rd["total"]}</strong></td></tr>')
    return "\n            ".join(rows_html)

# Build source list html
def source_list_html():
    items = []
    for src, cnt in src_counts.most_common():
        name = src_names.get(src, src)
        pct = cnt / total * 100
        items.append(f'<div class="src-row"><span class="src-name">{name}</span><span class="src-bar"><span class="src-fill" style="width:{pct}%"></span></span><span class="src-val">{cnt}</span></div>')
    return "\n          ".join(items)

# Build category bars html
def cat_bars_html():
    if not sorted_cats:
        return ''
    max_v = sorted_cats[0][1]
    items = []
    for cname, cnt in sorted_cats:
        short = cat_short.get(cname, cname)
        pct = cnt / max_v * 100 if max_v > 0 else 0
        items.append(f'<div class="cb-row"><span class="cb-label">{short}</span><span class="cb-track"><span class="cb-fill" style="width:{pct}%"></span></span><span class="cb-val">{cnt}</span></div>')
    return "\n            ".join(items)

# Build timeline bars html
def timeline_bars_html():
    max_v = max(yearly.values()) if yearly else 1
    items = []
    for y in years:
        c = yearly.get(y, 0)
        h = max(2, round(c / max_v * 110)) if max_v > 0 else 0
        special = ' sp' if y >= 2025 else ''
        suffix = '*' if y == 2026 else ''
        items.append(f'<div class="tb-col"><div class="tb-val">{c}{suffix}</div><div class="tb-bar{special}" style="height:{h}px"></div><div class="tb-yr">{y+543}</div></div>')
    return "\n              ".join(items)

now_thai = datetime.now().strftime("%d/%m/") + str(datetime.now().year + 543)

html = f"""<!DOCTYPE html>
<html lang="th">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>รายงานสถานการณ์ข่าวลวง — แรงงานและคนต่างด้าวในประเทศไทย</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700&family=Outfit:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    @page {{
      size: A4;
      margin: 18mm 20mm 16mm 20mm;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: 'Sarabun', sans-serif;
      font-size: 9.5pt;
      color: #1a1a1a;
      line-height: 1.55;
      background: #f0efed;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}

    /* ── A4 Page Container ── */
    .page {{
      width: 210mm;
      min-height: 297mm;
      background: #fff;
      margin: 12px auto;
      padding: 20mm 22mm 16mm 22mm;
      box-shadow: 0 2px 20px rgba(0,0,0,.08);
      position: relative;
    }}

    .page + .page {{ page-break-before: always; }}

    /* ── Download Button ── */
    .dl-btn {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 999;
      background: #2b1f1d;
      color: #fff;
      border: none;
      padding: 12px 24px;
      border-radius: 8px;
      font-family: 'Sarabun', sans-serif;
      font-size: 11pt;
      font-weight: 600;
      cursor: pointer;
      box-shadow: 0 4px 16px rgba(0,0,0,.2);
      transition: background .15s, transform .15s;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .dl-btn:hover {{ background: #8f3429; transform: translateY(-1px); }}

    @media print {{
      body {{ background: #fff; }}
      .page {{ box-shadow: none; margin: 0; padding: 0; width: auto; min-height: auto; }}
      .dl-btn {{ display: none !important; }}
    }}

    /* ── Header ── */
    .rpt-header {{
      border-bottom: 3px solid #2b1f1d;
      padding-bottom: 10px;
      margin-bottom: 14px;
    }}
    .rpt-kicker {{
      font-family: 'Outfit', sans-serif;
      font-size: 7pt;
      letter-spacing: 0.3em;
      text-transform: uppercase;
      color: #8f3429;
      font-weight: 600;
      margin-bottom: 2px;
    }}
    .rpt-title {{
      font-size: 18pt;
      font-weight: 700;
      line-height: 1.25;
      color: #1a1a1a;
    }}
    .rpt-title em {{ font-style: normal; color: #8f3429; }}
    .rpt-subtitle {{
      font-size: 9pt;
      color: #666;
      margin-top: 4px;
    }}
    .rpt-date {{
      font-family: 'Outfit', sans-serif;
      font-size: 7.5pt;
      color: #999;
      margin-top: 4px;
    }}

    /* ── Stat Pills ── */
    .stats-row {{
      display: flex;
      gap: 8px;
      margin-bottom: 14px;
    }}
    .pill {{
      flex: 1;
      border: 1px solid #e5e2dc;
      border-radius: 6px;
      padding: 8px 10px;
      text-align: center;
    }}
    .pill-num {{
      font-family: 'Outfit', sans-serif;
      font-size: 16pt;
      font-weight: 700;
      line-height: 1.1;
    }}
    .pill-label {{
      font-size: 7pt;
      color: #888;
      text-transform: uppercase;
      letter-spacing: .04em;
      margin-top: 2px;
    }}
    .pill-pct {{
      font-size: 7pt;
      color: #aaa;
    }}
    .pill.c-total {{ border-top: 3px solid #2b1f1d; }}
    .pill.c-total .pill-num {{ color: #2b1f1d; }}
    .pill.c-false {{ border-top: 3px solid #c93b2b; }}
    .pill.c-false .pill-num {{ color: #c93b2b; }}
    .pill.c-mis {{ border-top: 3px solid #a86b1c; }}
    .pill.c-mis .pill-num {{ color: #a86b1c; }}
    .pill.c-true {{ border-top: 3px solid #21693e; }}
    .pill.c-true .pill-num {{ color: #21693e; }}
    .pill.c-other {{ border-top: 3px solid #2c5980; }}
    .pill.c-other .pill-num {{ color: #2c5980; }}

    /* ── Two-Col Layout ── */
    .two-col {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 14px;
    }}

    .sec-title {{
      font-size: 9pt;
      font-weight: 700;
      color: #2b1f1d;
      margin-bottom: 8px;
      padding-bottom: 3px;
      border-bottom: 1.5px solid #e5e2dc;
    }}

    /* ── Timeline Bars ── */
    .timeline {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      height: 125px;
      border-bottom: 1.5px solid #e5e2dc;
      padding-top: 16px;
    }}
    .tb-col {{
      display: flex;
      flex-direction: column;
      align-items: center;
      flex: 1;
      margin: 0 2px;
    }}
    .tb-val {{
      font-family: 'Outfit', sans-serif;
      font-size: 7pt;
      font-weight: 700;
      color: #444;
      margin-bottom: 2px;
    }}
    .tb-bar {{
      width: 100%;
      max-width: 32px;
      background: #c4a68a;
      border-radius: 2px 2px 0 0;
    }}
    .tb-bar.sp {{ background: #8f3429; }}
    .tb-yr {{
      font-family: 'Outfit', sans-serif;
      font-size: 7pt;
      color: #888;
      margin-top: 3px;
    }}
    .tl-note {{
      font-size: 7pt;
      color: #aaa;
      margin-top: 3px;
    }}

    /* ── Category Bars ── */
    .cb-row {{
      display: flex;
      align-items: center;
      margin-bottom: 5px;
      font-size: 8.5pt;
    }}
    .cb-label {{ width: 115px; color: #555; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .cb-track {{ flex: 1; height: 10px; background: #f0ede6; border-radius: 5px; overflow: hidden; margin: 0 6px; }}
    .cb-fill {{ display: block; height: 100%; background: #8f3429; border-radius: 5px; }}
    .cb-val {{ font-family: 'Outfit', sans-serif; font-weight: 700; width: 28px; text-align: right; font-size: 8pt; }}

    /* ── Trend Table ── */
    .trend-tbl {{
      width: 100%;
      border-collapse: collapse;
      font-size: 7.5pt;
      margin-top: 6px;
    }}
    .trend-tbl th, .trend-tbl td {{
      padding: 4px 6px;
      border: 1px solid #e5e2dc;
      text-align: center;
    }}
    .trend-tbl th {{
      background: #f7f4ee;
      font-weight: 600;
      font-size: 7pt;
      color: #444;
    }}
    .trend-tbl td.yr {{
      text-align: left;
      font-weight: 600;
      background: #faf9f7;
    }}
    .trend-tbl td.hl {{
      background: #fcecea;
      color: #8f3429;
      font-weight: 700;
    }}
    .trend-tbl td.tot {{
      background: #f7f4ee;
      font-weight: 600;
    }}

    /* ── Insight Box ── */
    .insight {{
      background: #faf8f3;
      border-left: 3px solid #8f3429;
      padding: 10px 12px;
      margin-top: 14px;
      border-radius: 0 4px 4px 0;
      font-size: 8.5pt;
      line-height: 1.6;
      color: #444;
    }}
    .insight strong {{ color: #2b1f1d; }}

    /* ── Source Bars ── */
    .src-row {{
      display: flex;
      align-items: center;
      margin-bottom: 4px;
      font-size: 8pt;
    }}
    .src-name {{ width: 120px; color: #555; }}
    .src-bar {{ flex: 1; height: 8px; background: #f0ede6; border-radius: 4px; overflow: hidden; margin: 0 6px; }}
    .src-fill {{ display: block; height: 100%; background: #2c5980; border-radius: 4px; }}
    .src-val {{ font-family: 'Outfit', sans-serif; font-weight: 700; width: 28px; text-align: right; font-size: 7.5pt; }}

    /* ── Methodology ── */
    .method {{
      margin-top: 14px;
      padding-top: 10px;
      border-top: 1.5px solid #e5e2dc;
      font-size: 7.5pt;
      color: #999;
      line-height: 1.55;
    }}
    .method strong {{ color: #666; }}

    /* ── Footer ── */
    .rpt-footer {{
      margin-top: 12px;
      padding-top: 8px;
      border-top: 2px solid #2b1f1d;
      display: flex;
      justify-content: space-between;
      font-size: 7pt;
      color: #aaa;
    }}
  </style>
</head>
<body>

  <button class="dl-btn" onclick="window.print()">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    ดาวน์โหลด PDF
  </button>

  <!-- ═══════════════ PAGE 1 ═══════════════ -->
  <div class="page">

    <div class="rpt-header">
      <div class="rpt-kicker">TH Verify — Issue Focus Report</div>
      <h1 class="rpt-title">สถานการณ์ข่าวปลอมเรื่อง<em>แรงงานและคนต่างด้าว</em>ในประเทศไทย</h1>
      <p class="rpt-subtitle">วิเคราะห์จากฐานข้อมูลการตรวจสอบข้อเท็จจริง {total} คดี ระหว่างปี พ.ศ. 2563 – 2569</p>
      <p class="rpt-date">ข้อมูล ณ วันที่ {now_thai} | สร้างโดย TH Verify Database Engine</p>
    </div>

    <!-- Stats -->
    <div class="stats-row">
      <div class="pill c-total">
        <div class="pill-num">{total}</div>
        <div class="pill-label">คดีทั้งหมด</div>
      </div>
      <div class="pill c-false">
        <div class="pill-num">{fc}</div>
        <div class="pill-label">ข่าวปลอม</div>
        <div class="pill-pct">{fc/total*100:.1f}%</div>
      </div>
      <div class="pill c-mis">
        <div class="pill-num">{mc}</div>
        <div class="pill-label">บิดเบือน</div>
        <div class="pill-pct">{mc/total*100:.1f}%</div>
      </div>
      <div class="pill c-true">
        <div class="pill-num">{tc}</div>
        <div class="pill-label">ข่าวจริง</div>
        <div class="pill-pct">{tc/total*100:.1f}%</div>
      </div>
      <div class="pill c-other">
        <div class="pill-num">{oc}</div>
        <div class="pill-label">อื่นๆ</div>
        <div class="pill-pct">{oc/total*100:.1f}%</div>
      </div>
    </div>

    <!-- Charts Row -->
    <div class="two-col">
      <div>
        <div class="sec-title">สถิติรายปี (พ.ศ. 2563 – 2569)</div>
        <div class="timeline">
          {timeline_bars_html()}
        </div>
        <div class="tl-note">* ข้อมูลปี พ.ศ. 2569 ถึง 14 ก.ค. เท่านั้น</div>
      </div>
      <div>
        <div class="sec-title">สัดส่วนประเภทข่าวลวง</div>
        <div style="margin-top:6px;">
          {cat_bars_html()}
        </div>
      </div>
    </div>

    <!-- Trend Table -->
    <div class="sec-title">ตารางแนวโน้มประเด็นข่าวลวงรายปี</div>
    <table class="trend-tbl">
      <thead>
        <tr>
          <th style="text-align:left">ปี</th>
          <th>แย่งงาน</th>
          <th>สัญชาติ</th>
          <th>สวัสดิการ</th>
          <th>ชายแดน</th>
          <th>โรคระบาด</th>
          <th>อาชญากรรม</th>
          <th>รวม</th>
        </tr>
      </thead>
      <tbody>
        {trend_rows_html()}
      </tbody>
    </table>

    <!-- Trend Insight -->
    <div class="insight">
      <strong>💡 วิเคราะห์แนวโน้ม:</strong>
      ข่าวลวงเรื่องแรงงานต่างด้าวมีพัฒนาการชัดเจน 4 ยุค —
      <strong>ยุคโรคระบาด (พ.ศ. 2563–2564)</strong> กระแสหวาดระแวงว่าแรงงานเป็นต้นตอโควิด ·
      <strong>ช่วงเปลี่ยนผ่าน (พ.ศ. 2565–2566)</strong> "แย่งงาน" เสมอ "โรคระบาด" ที่ 21 เรื่องในปี 2565 ก่อนที่ "สัญชาติ" จะขึ้นอันดับ 1 ครั้งแรกในปี 2566 ·
      <strong>ยุคเศรษฐกิจ (พ.ศ. 2567)</strong> "แย่งงาน" ครอง 28 เรื่อง ·
      <strong>ยุคชาตินิยม (พ.ศ. 2568–2569)</strong> "สัญชาติ/สิทธิการเมือง" พุ่งสูงสุดที่ 44–48 เรื่อง สะท้อนความกังวลด้านอธิปไตยและความมั่นคง
    </div>

  </div>

  <!-- ═══════════════ PAGE 2 ═══════════════ -->
  <div class="page">

    <div class="rpt-header" style="margin-bottom:12px;">
      <div class="rpt-kicker">TH Verify — Issue Focus Report (ต่อ)</div>
      <h1 class="rpt-title" style="font-size:13pt;">ข้อมูลเชิงลึกและตัวอย่างข่าวลวงที่พบบ่อย</h1>
    </div>

    <div class="two-col">
      <!-- Source Distribution -->
      <div>
        <div class="sec-title">แหล่งข้อมูลที่ตรวจสอบ</div>
        <div style="margin-top:6px;">
          {source_list_html()}
        </div>
        <p style="font-size:7pt; color:#aaa; margin-top:6px;">
          ข้อมูลจาก 5 หน่วยงานตรวจสอบข้อเท็จจริงชั้นนำ<br>
          ครอบคลุมทั้งหน่วยงานรัฐ (AFNC) และภาคประชาสังคม (Cofact, ThaiPBS, ชัวร์ก่อนแชร์, AFP)
        </p>
      </div>

      <!-- Key Findings -->
      <div>
        <div class="sec-title">ข้อค้นพบสำคัญ 5 ประการ</div>
        <div style="font-size:8.5pt; color:#444; line-height:1.65;">
          <p style="margin-bottom:6px;"><strong style="color:#8f3429;">①</strong> ข่าวปลอมเรื่องต่างด้าว<strong>เพิ่มขึ้น 11 เท่า</strong>ในรอบ 6 ปี (8 เรื่องในปี 2563 → 88+ เรื่องในครึ่งแรกปี 2569)</p>
          <p style="margin-bottom:6px;"><strong style="color:#8f3429;">②</strong> เกือบครึ่ง ({fc/total*100:.0f}%) ของข่าวที่ตรวจสอบ<strong>เป็นข่าวปลอมทั้งหมด</strong> — สะท้อนว่าประเด็นนี้ถูกบิดเบือนอย่างหนัก</p>
          <p style="margin-bottom:6px;"><strong style="color:#8f3429;">③</strong> ประเด็น "สัญชาติ/นอมินี/สิทธิเลือกตั้ง" <strong>เติบโตเร็วที่สุด</strong>ในปี 2568–2569 แซงหน้าทุกประเด็นอื่น</p>
          <p style="margin-bottom:6px;"><strong style="color:#8f3429;">④</strong> ศูนย์ต่อต้านข่าวปลอม (AFNC) เป็นแหล่งตรวจสอบหลัก คิดเป็น {src_counts['afnc']/total*100:.0f}% ของข้อมูลทั้งหมด</p>
          <p><strong style="color:#8f3429;">⑤</strong> ข่าวลวงมีลักษณะ<strong>เปลี่ยนตามบริบทสังคม</strong> — จากโรคระบาด → แย่งงาน → ชาตินิยม สะท้อนความวิตกกังวลของสังคมในแต่ละช่วง</p>
        </div>
      </div>
    </div>

    <!-- Example Cases -->
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
        {"".join(
          f'<tr><td style="text-align:left">{r["title"][:75]}{"…" if len(r["title"])>75 else ""}</td>'
          f'<td style="color:{"#c93b2b" if get_verdict(r["verdict"])=="false" else "#a86b1c" if get_verdict(r["verdict"])=="misleading" else "#21693e"}">'
          f'{"ปลอม" if get_verdict(r["verdict"])=="false" else "บิดเบือน" if get_verdict(r["verdict"])=="misleading" else "จริง" if get_verdict(r["verdict"])=="true" else "อื่นๆ"}</td>'
          f'<td>{cat_short.get(r["categories"][0], r["categories"][0][:8])}</td>'
          f'<td>{src_names.get(r["source"], r["source"])}</td></tr>'
          for r in records[:8]
        )}
      </tbody>
    </table>

    <!-- Methodology -->
    <div class="method">
      <strong>ระเบียบวิธี:</strong> รายงานฉบับนี้ใช้ข้อมูลจากฐานข้อมูล TH Verify ซึ่งรวบรวมผลการตรวจสอบข้อเท็จจริงจาก 5 หน่วยงาน
      ได้แก่ ศูนย์ต่อต้านข่าวปลอม (AFNC), Cofact Thailand, Thai PBS Verify, ชัวร์ก่อนแชร์ (MCOT), และ AFP Fact Check
      โดยคัดกรองเฉพาะคดีที่เกี่ยวข้องกับคำค้นหา เช่น "ต่างด้าว", "ผู้อพยพ", "แรงงานต่างชาติ", "โรฮิงญา" เป็นต้น
      การจัดหมวดหมู่ดำเนินการโดยอัตโนมัติด้วยการวิเคราะห์คำสำคัญ (keyword-based classification) ทำให้บางคดีอาจถูกจัดอยู่ในมากกว่า 1 หมวดหมู่
      <br><br>
      <strong>ข้อจำกัด:</strong> ข้อมูลครอบคลุมเฉพาะคดีที่ได้รับการตรวจสอบโดยหน่วยงานข้างต้นเท่านั้น อาจไม่ได้สะท้อนข่าวลวงทั้งหมดที่แพร่หลายในสังคม
      ข้อมูลปี พ.ศ. 2569 เป็นข้อมูลเพียงครึ่งปีแรก (ถึง 14 กรกฎาคม พ.ศ. 2569) ตัวเลขทั้งปีคาดว่าจะสูงกว่านี้อย่างมีนัยสำคัญ
    </div>

    <div class="rpt-footer">
      <span>© พ.ศ. 2569 TH Verify Database Engine</span>
      <span>รายงานสร้างอัตโนมัติ — ห้ามใช้อ้างอิงทางกฎหมาย</span>
    </div>

  </div>

</body>
</html>
"""

# Save output
output_path = Path("/Users/visarutsankham/Desktop/migrant_report.html")
output_path.write_text(html, encoding="utf-8")

print(f"Successfully generated {output_path}")
conn.close()
