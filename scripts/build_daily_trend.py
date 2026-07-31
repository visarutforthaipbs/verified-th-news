#!/usr/bin/env python3
"""
Daily Misinformation Trend Generator (Daily Trend SKU).

Analyzes recent fact-checked articles from the database (default: last 24h),
clusters them into key thematic trends (Foreign Conflict, Online Scams, Health Myths, Security/Policy),
and outputs a formatted Markdown/HTML report.

Usage:
    python scripts/build_daily_trend.py [--hours 24] [--output-dir data/reports]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
from _freshness import assert_fresh  # noqa: E402

SOURCE_NAMES = {
    "afnc": "ศูนย์ต่อต้านข่าวปลอม (AFNC)",
    "sure_share": "ชัวร์ก่อนแชร์ (Sure & Share)",
    "cofact": "Cofact Thailand",
    "afp": "AFP Fact Check",
    "thaipbs": "Thai PBS Verify",
}

LABEL_TH = {
    "false": "ข่าวปลอม",
    "true": "ข่าวจริง",
    "misleading": "ข่าวบิดเบือน",
    "altered_media": "สื่อดัดแปลง/AI",
    "scam_alert": "เตือนภัยมิจฉาชีพ",
    "satire": "เสียดสี",
    "unknown": "รอตรวจสอบ/ไม่ระบุ",
    "ปลอม": "ข่าวปลอม",
    "บิดเบือน": "ข่าวบิดเบือน",
    "คลังความรู้": "คลังความรู้/ข้อเท็จจริง",
    "อาชญากรรมออนไลน์": "เตือนภัยมิจฉาชีพ",
    "ผลิตภัณฑ์สุขภาพ": "เตือนภัยสุขภาพ",
    "ความสงบและความมั่นคง": "ข่าวลือความมั่นคง",
}

THEMES = [
    {
        "id": "foreign_conflict",
        "title": "🌐 1. ภาพบริบทผิด & ข่าวบิดเบือนสถานการณ์ต่างประเทศ (Foreign Conflict & Misattributed Media)",
        "keywords": re.compile(r"อิหร่าน|อิสราเอล|สหรัฐ|ไฟไหม้|ขีปนาวุธ|คลังกระสุน|ฮูตี|ซาอุ|สเปน|ไครเมีย|ยูเครน|ตึกไฟไหม้|ถล่มโรงไฟฟ้า", re.IGNORECASE),
        "desc": "ตรวจพบสื่อโซเชียลนำคลิปไฟไหม้หรือระเบิดเก่าในต่างประเทศ (สเปน, ซาอุฯ, จีน) มาตัดต่ออ้างว่าเป็นเหตุการณ์โจมตีล่าสุดระหว่างสหรัฐฯ-อิหร่าน-อิสราเอล",
    },
    {
        "id": "health_and_wellness",
        "title": "🏥 2. เตือนภัยสุขภาพ & ความเชื่อทางการแพทย์ (Health Myths & Product Warnings)",
        "keywords": re.compile(r"ปากกาลดน้ำหนัก|หนอนกินฟัน|ฟันผุ|สมองเน่า|Brain Rot|กระพุ้งแก้ม|ยาควบคุมพิเศษ", re.IGNORECASE),
        "desc": "คำเตือนอันตรายจาก 'ปากกาลดน้ำหนัก' (ยาควบคุมพิเศษ) และการแก้ไขความเชื่อผิดๆ เรื่อง 'หนอนกินฟัน' ซึ่งแท้จริงเกิดจากแบคทีเรียย่อยสลายแป้ง/น้ำตาล",
    },
    {
        "id": "online_scams",
        "title": "🚨 3. อาชญากรรมออนไลน์ & เพจปลอมแอบอ้าง (Online Scams & Impersonation)",
        "keywords": re.compile(r"มิจ|เพจปลอม|แลกเงิน|บำนาญ|กรมบัญชีกลาง|LINE|แอบอ้าง|โกง|อิโมจิ|CIBbot|EV มือสอง", re.IGNORECASE),
        "desc": "มิจฉาชีพสร้างเพจปลอมแลกเงินต่างประเทศช่วงเทศกาลท่องเที่ยว และแอบอ้างชื่อเจ้าหน้าที่กรมบัญชีกลางสร้าง LINE ปลอมเพื่อหลอกรับเอกสารบำนาญ",
    },
    {
        "id": "state_policy_security",
        "title": "📌 4. ข่าวลือความมั่นคง & นโยบายรัฐบาล (Security Rumors & State Policy)",
        "keywords": re.compile(r"บัตรสวัสดิการ|ค่าน้ำประปา|กัมพูชา|PHL03|จรวด|ไฟไหม้โรงเบียร์|รถไฟฟ้า|กทม|คมนาคม|ทหาร|ไทยมีงานทำ|ว่างงาน", re.IGNORECASE),
        "desc": "ข่าวลือการเฝ้าระวังชายแดนกัมพูชา และการชี้แจงสิทธิประโยชน์จริงเรื่องค่าน้ำประปาผู้ถือบัตรสวัสดิการแห่งรัฐ",
    },
]


def fetch_recent_articles(db_path: str, hours: int = 24) -> list[dict]:
    con = sqlite3.connect(db_path)
    assert_fresh(con)
    con.row_factory = sqlite3.Row
    sql = """
    SELECT id, source, source_url, title, claim, explanation, verdict, category,
           published_at, first_seen_at
    FROM fact_checks
    WHERE first_seen_at >= datetime('now', '-' || ? || ' hours')
    ORDER BY first_seen_at DESC
    """
    rows = con.execute(sql, (hours,)).fetchall()
    return [dict(r) for r in rows]


def categorize_articles(articles: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    categorized = defaultdict(list)
    uncategorized = []

    for art in articles:
        text = f"{art['title']} {art['claim']} {art['explanation']} {art['category']}"
        matched = False
        for theme in THEMES:
            if theme["keywords"].search(text):
                categorized[theme["id"]].append(art)
                matched = True
                break
        if not matched:
            uncategorized.append(art)

    return categorized, uncategorized


def render_report(articles: list[dict], categorized: dict[str, list[dict]], uncategorized: list[dict], hours: int) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_count = len(articles)

    # Source breakdown
    source_counts = defaultdict(int)
    for a in articles:
        source_counts[a["source"]] += 1

    source_table = "".join(
        f"| {SOURCE_NAMES.get(src, src)} | {cnt} |\n"
        for src, cnt in sorted(source_counts.items(), key=lambda x: x[1], reverse=True)
    )

    # Trend sections
    trend_blocks = []
    for theme in THEMES:
        tid = theme["id"]
        items = categorized.get(tid, [])
        if not items:
            continue

        item_list = []
        for item in items:
            raw_v = item.get('verdict') or 'unknown'
            verdict_text = LABEL_TH.get(raw_v, raw_v)
            verdict_badge = f"`{verdict_text}`"
            src_name = SOURCE_NAMES.get(item['source'], item['source'])
            url_str = f" 🔗 [อ่านต้นฉบับ]({item['source_url']})" if item.get('source_url') else ""

            claim_text = item['claim'] if item['claim'] else item['title']
            if len(claim_text) > 140:
                claim_text = claim_text[:140] + "…"

            item_list.append(
                f"- **{item['title']}** {verdict_badge} — _{src_name}_{url_str}\n"
                f"  > 💬 **ข้อความที่แพร่กระจาย:** {claim_text}\n"
            )

        items_str = "\n".join(item_list)
        trend_blocks.append(f"""### {theme['title']}

> 💡 **สรุปบทวิเคราะห์:** {theme['desc']}

**รายการตรวจสอบที่เกี่ยวข้อง ({len(items)} รายการ):**
{items_str}
""")

    if uncategorized:
        other_items = []
        for item in uncategorized:
            raw_v = item.get('verdict') or 'unknown'
            verdict_text = LABEL_TH.get(raw_v, raw_v)
            verdict_badge = f"`{verdict_text}`"
            src_name = SOURCE_NAMES.get(item['source'], item['source'])
            other_items.append(f"- **{item['title']}** {verdict_badge} — _{src_name}_")
        others_str = "\n".join(other_items)
        trend_blocks.append(f"""### 📌 ประเด็นอื่นๆ (Other Topics)
{others_str}
""")

    body_trends = "\n---\n\n".join(trend_blocks) if trend_blocks else "_ไม่พบข่าวสารใหม่ในรอบเวลาที่กำหนด_"

    return f"""# 📊 รายงานแนวโน้มข่าวปลอมและข่าวสารประจำวัน (Daily Misinformation Trend Report)

> 🗓️ **วันที่:** {today_str}  
> 🕒 **เวลาประมวลผล:** {now_str}  
> ⏱️ **ช่วงเวลาข้อมูล:** ย้อนหลัง {hours} ชั่วโมง  
> 📥 **จำนวนข่าวสารใหม่ทั้งหมด:** **{total_count}** รายการ  

---

## 📈 สรุปภาพรวมรายแหล่งข้อมูล (Source Breakdown)

| แหล่งข้อมูล (Source) | จำนวนข่าวใหม่ |
|----------------------|---------------|
{source_table}

---

## 🎯 แนวโน้มและรูปแบบข่าวปลอมสำคัญประจำวัน (Key Daily Trends)

{body_trends}

---
*รายงานแนวโน้มประจำวันสร้างขึ้นโดยอัตโนมัติจากคลังข้อมูล th-verify database*
"""


def main():
    ap = argparse.ArgumentParser(description="Generate Daily Misinformation Trend report.")
    ap.add_argument("--hours", type=int, default=24, help="Time window in hours (default: 24)")
    ap.add_argument("--db", default="data/th_verify.db", help="Path to th_verify.db")
    ap.add_argument("--output-dir", default="data/reports", help="Output directory for reports")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        db_path = Path.home() / "th-verify" / "data" / "th_verify.db"

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    report_file = output_dir / f"daily_trend_{today_str}.md"

    articles = fetch_recent_articles(str(db_path), hours=args.hours)
    categorized, uncategorized = categorize_articles(articles)

    report_md = render_report(articles, categorized, uncategorized, args.hours)
    report_file.write_text(report_md, encoding="utf-8")

    print(f"✅ Daily trend report generated → {report_file}")
    print("\n" + "="*60 + "\n")
    print(report_md)


if __name__ == "__main__":
    main()
