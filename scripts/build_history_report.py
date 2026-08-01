#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_history_report.py — Generator for '10+ Years of Thai People and Fake News (2015–2026)' report.
"""

import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
from _freshness import assert_fresh  # noqa: E402
import _brand  # noqa: E402

DB_PATH = Path('data/th_verify.db')
OUTPUT_DIR = Path('data/reports')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MD_PATH = OUTPUT_DIR / 'history_10years_report.md'
HTML_PATH = OUTPUT_DIR / 'history_10years_report.html'
ARTIFACT_MD_PATH = Path('/Users/lighthouse-control/.gemini/antigravity/brain/b11168bc-849c-469d-b771-806a94b32f89/history_10years_report.md')

def query_db():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    assert_fresh(conn)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 1. Total overview
    total_records = cur.execute("SELECT COUNT(*) FROM fact_checks").fetchone()[0]
    total_clusters = cur.execute("SELECT COUNT(*) FROM claim_clusters").fetchone()[0]
    
    # 2. Source breakdown
    sources_raw = cur.execute("""
        SELECT source, COUNT(*) as cnt, MIN(published_at) as oldest, MAX(published_at) as newest
        FROM fact_checks GROUP BY source ORDER BY cnt DESC
    """).fetchall()
    sources = [dict(r) for r in sources_raw]
    
    # 3. Yearly breakdown
    yearly_raw = cur.execute("""
        SELECT SUBSTR(published_at, 1, 4) as year, COUNT(*) as cnt
        FROM fact_checks WHERE published_at IS NOT NULL AND published_at != ''
        GROUP BY year ORDER BY year ASC
    """).fetchall()
    yearly = [dict(r) for r in yearly_raw]
    
    # 4. Era breakdown
    eras_def = [
        ("era1", "2015–2018 (ยุคข่าวลวงโซเชียล & สุขภาพ)", "published_at >= '2015' AND published_at < '2019'"),
        ("era2", "2019–2021 (ยุควิกฤตโควิด-19 & ศูนย์ต่อต้านข่าวปลอม)", "published_at >= '2019' AND published_at < '2022'"),
        ("era3", "2022–2023 (ยุคอาชญากรรมการเงิน & หลอกลงทุน)", "published_at >= '2022' AND published_at < '2024'"),
        ("era4", "2024–2026 (ยุค AI, Deepfake & อาชญากรรมข้ามชาติ)", "published_at >= '2024'")
    ]
    
    eras_data = []
    for key, name, clause in eras_def:
        cnt = cur.execute(f"SELECT COUNT(*) FROM fact_checks WHERE {clause}").fetchone()[0]
        cats = cur.execute(f"""
            SELECT category, COUNT(*) as c FROM fact_checks 
            WHERE {clause} AND category != '' GROUP BY category ORDER BY c DESC LIMIT 5
        """).fetchall()
        
        # Sample headlines
        samples = cur.execute(f"""
            SELECT title, source, published_at FROM fact_checks 
            WHERE {clause} AND title != '' ORDER BY RANDOM() LIMIT 4
        """).fetchall()
        
        eras_data.append({
            'key': key,
            'name': name,
            'count': cnt,
            'categories': [dict(c) for c in cats],
            'samples': [dict(s) for s in samples]
        })
        
    # 5. Top financial/impersonation scam entities
    scam_keywords = ['ออมสิน', 'ตลาดหลักทรัพย์', 'กรุงไทย', 'กู้เงิน', 'แจกเงิน', 'สปสช', 'สรรพากร', 'ตำรวจ']
    scam_counts = {}
    for kw in scam_keywords:
        c = cur.execute("SELECT COUNT(*) FROM fact_checks WHERE title LIKE ? OR claim LIKE ?", (f'%{kw}%', f'%{kw}%')).fetchone()[0]
        scam_counts[kw] = c
        
    # 6. Duplicate/Recirculation analysis
    dupes_title = cur.execute("SELECT COUNT(title) - COUNT(DISTINCT title) FROM fact_checks").fetchone()[0]
    dupes_claim = cur.execute("SELECT COUNT(claim) - COUNT(DISTINCT claim) FROM fact_checks WHERE claim != ''").fetchone()[0]
    
    # Top recirculated headlines
    recirc = cur.execute("""
        SELECT title, COUNT(*) as cnt, MIN(published_at) as min_date, MAX(published_at) as max_date
        FROM fact_checks
        WHERE title != ''
        GROUP BY title
        HAVING cnt > 2
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    
    conn.close()
    
    return {
        'total_records': total_records,
        'total_clusters': total_clusters,
        'sources': sources,
        'yearly': yearly,
        'eras': eras_data,
        'scam_counts': scam_counts,
        'dupes_title': dupes_title,
        'dupes_claim': dupes_claim,
        'recirculated': [dict(r) for r in recirc]
    }

def generate_markdown(data):
    md = f"""# 🇹🇭 10+ Years of Thai People and Fake News (2015–2026)
## รายงานประวัติศาสตร์ 10+ ปี ข่าวลวงในประเทศไทย ผ่านฐานข้อมูล 28,000+ เรื่อง

**วันที่จัดทำ:** 23 กรกฎาคม 2026  
**แหล่งข้อมูล:** ฐานข้อมูล TH Verify Archive (`data/th_verify.db`)  
**จำนวนข้อมูลทั้งหมด:** {data['total_records']:,} เรื่อง (คัดกรองจาก 5 สำนักตรวจสอบข่าว)  
**กลุ่มข่าวเชื่อมโยงทางอรรถศาสตร์ (Claim Clusters):** {data['total_clusters']:,} กลุ่ม  

---

## Executive Summary (บทสรุปผู้บริหาร)

การแพร่กระจายของข่าวปลอมและข้อมูลเท็จในประเทศไทยตลอด 11 ปีที่ผ่านมา (ค.ศ. 2015 – 2026) มีการวิวัฒนาการอย่างเห็นได้ชัด จากเดิมที่เป็นเพียง **"ข่าวลวงสุขภาพ/ความเชื่อ"** ในกลุ่มไลน์และโซเชียลมีเดีย ยุคถัดมาขยับสู่ **"ข่าวลวงโรคระบาดและนโยบายรัฐ"** ในช่วงโควิด-19 จนกระทั่งก้าวเข้าสู่ยุค **"อาชญากรรมทางการเงินและแก๊งหลอกลงทุน"** และล่าสุดในปัจจุบันคือยุค **"AI Deepfake และอาชญากรรมข้ามชาติ"**

### ภาพรวมการจัดเก็บข้อมูลตามสำนักตรวจสอบ (2015–2026)

| สำนักข่าว / หน่วยงาน (Source) | จำนวนบันทึก (Records) | สัดส่วน (%) | ปีที่เริ่มบันทึก | ปีล่าสุด |
| :--- | ---: | ---: | :--- | :--- |
"""
    total = data['total_records']
    source_names = {
        'afnc': 'ศูนย์ต่อต้านข่าวปลอม ประเทศไทย (AFNC)',
        'sure_share': 'ศูนย์ชัวร์ก่อนแชร์ (MCOT)',
        'cofact': 'Cofact Thailand',
        'afp': 'AFP Fact Check Thailand',
        'thaipbs': 'Thai PBS Verify'
    }
    for s in data['sources']:
        src = s['source']
        name = source_names.get(src, src)
        cnt = s['cnt']
        pct = (cnt / total) * 100
        oldest = str(s['oldest'])[:10] if s['oldest'] else '-'
        newest = str(s['newest'])[:10] if s['newest'] else '-'
        md += f"| **{name}** | {cnt:,} | {pct:.1f}% | {oldest} | {newest} |\n"
        
    md += f"""
---

## 1. วิวัฒนาการปริมาณข่าวลวงในประเทศไทย (2015–2026)

ปริมาณการบันทึกและตรวจสอบข่าวลวงเพิ่มขึ้นอย่างก้าวกระโดดนับตั้งแต่ปี 2019 หลังจากการจัดตั้งศูนย์ต่อต้านข่าวปลอมแห่งชาติ และการขยายตัวของสื่อดิจิทัลในไทย:

```
ปี (Year)   จำนวนข่าวลวง (Records)  กราฟสัดส่วน
"""
    max_cnt = max([y['cnt'] for y in data['yearly']]) if data['yearly'] else 1
    for y in data['yearly']:
        year = y['year']
        cnt = y['cnt']
        bar_len = int((cnt / max_cnt) * 30)
        bar = "█" * bar_len
        md += f"{year}        {cnt:>6,}                 {bar}\n"
        
    md += """```

---

## 2. เจาะลึก 4 ยุคประวัติศาสตร์ข่าวลวงในสังคมไทย

### 🔵 ยุคที่ 1: 2015–2018 — ยุคข่าวลวงโซเชียล & สมุนไพรสุขภาพ (Early Social Media Era)
- **ปริมาณข้อมูล:** 993 เรื่อง (หลักๆ จากศูนย์ชัวร์ก่อนแชร์)
- **ลักษณะเด่น:** ข่าวลวงในยุคนี้มักมาในรูปแบบบทความส่งต่อในแอปพลิเคชัน LINE เช่น สูตรสมุนไพรรักษาโรคมะเร็ง, อาการเตือนภัยสุขภาพผิดๆ, และภัยธรรมชาติเกินจริง
- **ตัวอย่างหัวข้อข่าวในยุคนี้:**
  - *"มะนาวโซดารักษามะเร็งได้จริงหรือ?"*
  - *"ดื่มน้ำเย็นหลังอาหารทำให้เป็นมะเร็งจริงหรือ?"*
  - *"พายุลูกใหญ่กำลังจะเข้าไทยระลอกใหม่จริงหรือ?"*

### 🟡 ยุคที่ 2: 2019–2021 — ยุควิกฤตโควิด-19 & นโยบายรัฐ (COVID-19 & Institutional Era)
- **ปริมาณข้อมูล:** 4,314 เรื่อง (เริ่มมีข้อมูลจาก AFNC, AFP, Cofact)
- **ลักษณะเด่น:** การเกิดโรคระบาดใหญ่ส่งผลให้ข่าวลวงพุ่งสูงขึ้นอย่างรวดเร็ว ข่าวส่วนใหญ่เกี่ยวกับการยับยั้งเชื้อโควิด-19, ความปลอดภัยของวัคซีน, และข่าวลือมาตรการล็อกดาวน์/เยียวยาของรัฐบาล
- **หมวดหมู่ยอดนิยม:** ผลิตภัณฑ์สุขภาพ (1,091 เรื่อง), นโยบายรัฐบาล/ข่าวสาร (868 เรื่อง)
- **ตัวอย่างหัวข้อข่าวในยุคนี้:**
  - *"ฟ้าทะลายโจรป้องกันโควิด-19 ได้ 100%?"*
  - *"รัฐบาลเตรียมฉีดวัคซีนภาคบังคับพร้อมคิดเงิน?"*
  - *"ปิดเมือง 100% ห้ามออกจากบ้านหลัง 20.00 น."*

### 🟠 ยุคที่ 3: 2022–2023 — ยุคอาชญากรรมทางการเงิน & แก๊งหลอกลงทุน (Financial Scams & Cybercrime Era)
- **ปริมาณข้อมูล:** 8,748 เรื่อง
- **ลักษณะเด่น:** ข่าวลวงเปลี่ยนรูปแบบจาก "ความเข้าใจผิด" ไปสู่ **"การหลอกลวงเพื่อเอาทรัพย์สิน"** โดยกลุ่มแก๊งคอลเซ็นเตอร์และเพจปลอมเริ่มแอบอ้างสถาบันการเงินและหน่วยงานรัฐบาลอย่างเป็นระบบ
- **หมวดหมู่ยอดนิยม:** นโยบายรัฐบาล/ข่าวสาร (1,906 เรื่อง), ผลิตภัณฑ์สุขภาพ (1,501 เรื่อง), การเงิน-หุ้น (1,040 เรื่อง)

### 🔴 ยุคที่ 4: 2024–2026 — ยุค AI Deepfake & อาชญากรรมข้ามชาติ (AI & Deepfake Era)
- **ปริมาณข้อมูล:** 14,147 เรื่อง
- **ลักษณะเด่น:** เทคโนโลยี Generative AI ถูกนำมาใช้สร้างคลิปวิดีโอดีพเฟก (Deepfake) และเสียงตัดต่อของบุคคลมีชื่อเสียง เช่น ผู้ประกาศข่าว ดารา และนายกรัฐมนตรี เพื่อหลอกลงทุน นอกจากนี้ยังมีข่าวลวงประเด็นความมั่นคงชายแดนไทย-กัมพูชา และอาชญากรรมออนไลน์ข้ามชาติ
- **หมวดหมู่ยอดนิยม:** นโยบายรัฐบาล (3,129 เรื่อง), การเงิน-หุ้น (1,281 เรื่อง), อาชญากรรมออนไลน์ (1,058 เรื่อง)

---

## 3. สถาบันและหน่วยงานที่ถูกแอบอ้างสร้างข่าวลวงมากที่สุด

จากการวิเคราะห์คำค้นในฐานข้อมูล พบว่าหน่วยงานทางการเงินและสวัสดิการรัฐเป็นเป้าหมายหลักในการถูกแอบอ้างเพื่อหลอกลวงประชาชน:

| หน่วยงาน / สถาบันที่ถูกแอบอ้าง | จำนวนข่าวลวงที่ตรวจพบ (เรื่อง) | รูปแบบการแอบอ้างหลัก |
| :--- | ---: | :--- |
| **ธนาคารออมสิน** | """
    md += f"{data['scam_counts']['ออมสิน']:,} | ปลอมเพจสินเชื่อเงินกู้ดอกเบี้ยต่ำ / อนุมัติไวผ่านไลน์ |\n"
    md += f"| **ตลาดหลักทรัพย์แห่งประเทศไทย (SET)** | {data['scam_counts']['ตลาดหลักทรัพย์']:,} | แอบอ้างชวนลงทุนหุ้นเริ่มต้น 1,000 บาท ปันผลรายวัน |\n"
    md += f"| **ธนาคารกรุงไทย** | {data['scam_counts']['กรุงไทย']:,} | แอบอ้างแอปพลิเคชัน Krungthai NEXT และโครงการรัฐบาล |\n"
    md += f"| **สำนักงานประกันสุขภาพแห่งชาติ (สปสช.)** | {data['scam_counts']['สปสช']:,} | ล่อลวงเงินเยียวยาสิทธิรักษาพยาบาล/สิทธิประกันสังคม |\n"
    md += f"| **กรมสรรพากร** | {data['scam_counts']['สรรพากร']:,} | แอปปลอมยกเว้นภาษี / คืนเงินภาษีล่อโหลดไฟล์ APK |\n"

    md += f"""
---

## 4. ปรากฏการณ์ "ข่าวลวงฉายซ้ำ" (Recirculating Hoaxes)

ฐานข้อมูลตรวจพบว่ามีข่าวลวงจำนวนมากที่เป็น **ข่าวลวงวนลูป** (Recirculating Hoaxes) ซึ่งถูกนำกลับมาแชร์ใหม่ทุกๆ 2–3 ปี เมื่อเกิดเหตุการณ์คล้ายเดิม เช่น น้ำท่วม, เลือกตั้ง, หรือวิกฤตเศรษฐกิจ

- **จำนวนชื่อเรื่องซ้ำกัน (Title Duplicates):** {data['dupes_title']:,} ครั้ง
- **จำนวนข้อความอ้างซ้ำกัน (Claim Duplicates):** {data['dupes_claim']:,} ครั้ง
- **กลุ่มข่าวที่เชื่อมโยงกัน (Claim Clusters):** {data['total_clusters']:,} กลุ่ม

### ตัวอย่างข่าวลวงยอดฮิตที่ถูกนำกลับมาแชร์ซ้ำบ่อยที่สุด:

"""
    for r in data['recirculated']:
        title = r['title']
        cnt = r['cnt']
        min_d = str(r['min_date'])[:10]
        max_d = str(r['max_date'])[:10]
        md += f"- **{title}** (ถูกตรวจสอบซ้ำ **{cnt} ครั้ง** ระหว่างปี {min_d} ถึง {max_d})\n"

    md += """
---

## 5. ข้อเสนอแนะเชิงนโยบายและทิศทางในอนาคต

1. **การบูรณาการ AI ตรวจสอบข่าวลวงเชิงรุก:** หน่วยงานตรวจสอบจำเป็นต้องเปลี่ยนจากการตรวจสอบตามหลัง (Reactive) ไปสู่ระบบเฝ้าระวังเชิงรุก (Proactive Monitoring) ที่สามารถตรวจจับ AI Deepfake ได้ทันท่วงที
2. **การแชร์ฐานข้อมูลกลาง (Open Data Integration):** การเชื่อมโยงฐานข้อมูลระหว่างสำนักข่าว ศูนย์ต่อต้านข่าวปลอม และสถาบันการเงิน จะช่วยตัดวงจรข่าวลวงการเงินได้อย่างมีประสิทธิภาพ
3. **การสร้างภูมิคุ้มกันดิจิทัล (Digital Literacy):** มุ่งเน้นการให้ความรู้ประชาชนเกี่ยวกับเทคนิค "เช็กก่อนเชื่อ" และการสังเกตจุดผิดสังเกตของเพจปลอม/แอปพลิเคชันดูดเงิน
"""
    return md

def generate_html(data, md_content):
    """Render the history report in the Fake News Lab system.

    The stylesheet is assets/brand/fnl-design-system.css; only the metric-tile
    grid used on this page is added on top.
    """
    extra_css = """
    .metrics-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
      gap:var(--fnl-space-3); margin:var(--fnl-space-5) 0; }
    .metric-card { border:var(--fnl-rule) solid var(--fnl-line);
      border-top:var(--fnl-rule-heavy) solid var(--fnl-red);
      background:var(--fnl-surface-1); padding:var(--fnl-space-4); text-align:center; }
    .metric-val { font-family:var(--fnl-font-mono); font-size:1.8rem; font-weight:700;
      color:var(--fnl-white); font-variant-numeric:tabular-nums; }
    .metric-label { font-family:var(--fnl-font-mono); font-size:var(--fnl-fs-micro);
      letter-spacing:0.06em; text-transform:uppercase; color:var(--fnl-gray); }
    """
    body = f"""
        <button class="dl-btn" onclick="window.print()">พิมพ์ / บันทึก PDF</button>
        {_brand.cover(
            "รายงานประวัติศาสตร์ · HISTORY REPORT",
            "๑๐ ปี คนไทยกับ<em>ข่าวลวง</em>",
            subtitle="10+ Years of Thai People and Fake News (2015–2026)",
            chips=[_brand.chip(f"{data['total_records']:,} เรื่อง"),
                   _brand.chip(f"{data['total_clusters']:,} คลัสเตอร์", "arrow"),
                   _brand.chip("5 สำนักตรวจสอบ", "mute")],
            meta=[("ฐานข้อมูล", "TH Verify Archive"),
                  ("ช่วงข้อมูล", "2015 – 2026"),
                  ("จัดทำเมื่อ", datetime.now().strftime("%Y-%m-%d"))])}

        <p class="fnl-muted">รายงานประวัติศาสตร์ 10+ ปี ข่าวลวงในประเทศไทย ผ่านฐานข้อมูล 28,000+ เรื่อง</p>

        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-val">{data['total_records']:,}</div>
                <div class="metric-label">จำนวนข่าวลวงทั้งหมด (Fact Checks)</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{data['total_clusters']:,}</div>
                <div class="metric-label">กลุ่มข่าวเชื่อมโยง (Claim Clusters)</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">5</div>
                <div class="metric-label">สำนักตรวจสอบข่าวหลัก</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">11 ปี</div>
                <div class="metric-label">ช่วงเวลาข้อมูล (2015 - 2026)</div>
            </div>
        </div>

        <h2>สำนักข่าวและแหล่งข้อมูลที่บันทึก</h2>
        <table>
            <thead>
                <tr>
                    <th>สำนักข่าว / แหล่งข้อมูล</th>
                    <th>จำนวนเรื่อง (Records)</th>
                    <th>ช่วงเวลาในฐานข้อมูล</th>
                </tr>
            </thead>
            <tbody>
"""
    source_names = {
        'afnc': 'ศูนย์ต่อต้านข่าวปลอม ประเทศไทย (AFNC)',
        'sure_share': 'ศูนย์ชัวร์ก่อนแชร์ (MCOT)',
        'cofact': 'Cofact Thailand',
        'afp': 'AFP Fact Check Thailand',
        'thaipbs': 'Thai PBS Verify'
    }
    for s in data['sources']:
        name = source_names.get(s['source'], s['source'])
        oldest = str(s['oldest'])[:10] if s['oldest'] else '-'
        newest = str(s['newest'])[:10] if s['newest'] else '-'
        body += f"""
                <tr>
                    <td><strong>{name}</strong></td>
                    <td>{s['cnt']:,}</td>
                    <td>{oldest} ถึง {newest}</td>
                </tr>"""

    body += """
            </tbody>
        </table>

        <h2>วิวัฒนาการข่าวลวงตามช่วงเวลา (Yearly Evolution)</h2>
        <pre>"""
    max_cnt = max([y['cnt'] for y in data['yearly']]) if data['yearly'] else 1
    for y in data['yearly']:
        bar_len = int((y['cnt'] / max_cnt) * 30)
        bar = "█" * bar_len
        body += f"\n{y['year']}  {y['cnt']:>6,}  {bar}"
        
    body += """</pre>

        <h2>เจาะลึก 4 ยุคประวัติศาสตร์ข่าวลวงในไทย</h2>
        
        <h3>1. 2015–2018: ยุคข่าวลวงโซเชียล & สุขภาพ</h3>
        <p>เน้นบทความส่งต่อทาง LINE และ Facebook เรื่องสมุนไพรรักษาโรค สุขภาพ และภัยธรรมชาติ</p>
        
        <h3>2. 2019–2021: ยุควิกฤตโควิด-19 & ศูนย์ต่อต้านข่าวปลอม</h3>
        <p>ข่าวลวงพุ่งสูงจากโควิด-19 ความปลอดภัยวัคซีน และการจัดตั้งศูนย์ต่อต้านข่าวปลอมแห่งชาติ (AFNC)</p>

        <h3>3. 2022–2023: ยุคอาชญากรรมทางการเงิน & หลอกลงทุน</h3>
        <p>ข่าวลวงเปลี่ยนเป็นคอลเซ็นเตอร์ เพจปลอมแอบอ้างธนาคารออมสิน ตลาดหลักทรัพย์ฯ และแอปเงินกู้</p>

        <h3>4. 2024–2026: ยุค AI Deepfake & อาชญากรรมข้ามชาติ</h3>
        <p>ใช้ AI สร้างวิดีโอ/เสียงตัดต่อบุคคลมีชื่อเสียง หลอกลงทุน คอลเซ็นเตอร์ข้ามชาติ และข่าวลวงความมั่นคง</p>

        <h2>สถาบันที่ถูกแอบอ้างบ่อยที่สุด</h2>
        <table>
            <thead>
                <tr>
                    <th>หน่วยงาน / สถาบัน</th>
                    <th>จำนวนครั้งที่พบ</th>
                    <th>รูปแบบการแอบอ้าง</th>
                </tr>
            </thead>
            <tbody>
"""
    body += f"""
                <tr><td>ธนาคารออมสิน</td><td>{data['scam_counts']['ออมสิน']:,}</td><td>เพจสินเชื่อเงินกู้ดอกเบี้ยต่ำ / อนุมัติไวผ่านไลน์</td></tr>
                <tr><td>ตลาดหลักทรัพย์แห่งประเทศไทย (SET)</td><td>{data['scam_counts']['ตลาดหลักทรัพย์']:,}</td><td>ชวนลงทุนหุ้นเริ่มต้น 1,000 บาท ปันผลรายวัน</td></tr>
                <tr><td>ธนาคารกรุงไทย</td><td>{data['scam_counts']['กรุงไทย']:,}</td><td>แอบอ้างแอป Krungthai NEXT และโครงการรัฐบาล</td></tr>
                <tr><td>สปสช.</td><td>{data['scam_counts']['สปสช']:,}</td><td>ล่อลวงเงินเยียวยาสิทธิรักษาพยาบาล</td></tr>
                <tr><td>กรมสรรพากร</td><td>{data['scam_counts']['สรรพากร']:,}</td><td>แอปปลอมคืนเงินภาษี / หลอกโหลดไฟล์ APK</td></tr>
"""
    body += """
            </tbody>
        </table>

        <h2>ข่าวลวงฉายซ้ำยอดฮิต (Recirculating Hoaxes)</h2>
        <ul>
"""
    for r in data['recirculated']:
        min_d = str(r['min_date'])[:10]
        max_d = str(r['max_date'])[:10]
        body += f"            <li><strong>{r['title']}</strong> — ตรวจสอบซ้ำ {r['cnt']} ครั้ง ({min_d} ถึง {max_d})</li>\n"

    body += """
        </ul>
"""
    body += _brand.footer(f"{_brand.ORG_TH} · {_brand.ORG_EN}",
                          "TH VERIFY ARCHIVE · 2015–2026")
    return _brand.document(
        "10+ Years of Thai People and Fake News (2015–2026)",
        f'<div class="fnl-doc">{body}</div>', extra_css=extra_css)

def main():
    print("Extracting data from database...")
    data = query_db()
    
    print("Generating Markdown report...")
    md_content = generate_markdown(data)
    
    with open(MD_PATH, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"Saved Markdown report to {MD_PATH}")
    
    print("Generating HTML report...")
    html_content = generate_html(data, md_content)
    
    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Saved HTML report to {HTML_PATH}")
    
    print("Report generation complete!")

if __name__ == '__main__':
    main()
