#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_article_datasets.py
Generates clean, transparent, reproducible raw datasets and data dictionaries
for Prachatai Grant Deliverables:
  - Article 1: 11-Year Fact-Check Archive (27,231 clean atomic claims)
  - Article 2: Migrant & Cross-Border Misinformation Deep-Dive (869 claims)
"""

import sys
import csv
import json
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from th_verify.normalized import get_normalized_records

DATASET_DIR = Path("data/reports/datasets")
DATASET_DIR.mkdir(parents=True, exist_ok=True)

def assign_era(year_str):
    try:
        y = int(year_str)
    except (ValueError, TypeError):
        return "Unknown"
    if y <= 2018:
        return "ยุคที่ 1: 2558–2561 (สุขภาพ & ไลน์ส่งต่อ)"
    elif 2019 <= y <= 2021:
        return "ยุคที่ 2: 2562–2564 (วิกฤตโรคระบาด & นโยบายรัฐ)"
    elif 2022 <= y <= 2023:
        return "ยุคที่ 3: 2565–2566 (การเงินภิวัตน์ & ล่าเหยื่อออนไลน์)"
    else:
        return "ยุคที่ 4: 2567–2569 (AI Deepfake & ชาตินิยม/ความมั่นคง)"

def categorize_migrant_narrative(text):
    t = text.lower()
    matched = []
    
    # 1. Sovereignty & Political
    sov_kw = ['สัญชาติ', 'เลือกตั้ง', 'บัตรประชาชน', 'อธิปไตย', 'เกาะกูด', 'mou', 'ยึดครอง', 'เสียดินแดน', 'สิทธิการเมือง']
    sov_hits = [k for k in sov_kw if k in t]
    
    # 2. Disease & Health
    dis_kw = ['โควิด', 'โรค', 'ระบาด', 'ติดเชื้อ', 'วัคซีน', 'ไข้ป่า', 'สาธารณสุข', 'โอไมครอน']
    dis_hits = [k for k in dis_kw if k in t]
    
    # 3. Economic & Nominee
    eco_kw = ['แย่งงาน', 'แย่งอาชีพ', 'ค้าขาย', 'ทำงาน', 'นอมินี', 'สิทธิรักษา', 'ประกันสังคม', 'สวัสดิการ']
    eco_hits = [k for k in eco_kw if k in t]
    
    # 4. Broker & Smuggling
    brk_kw = ['นายหน้า', 'หลอกลวง', 'ลักลอบ', 'ค้ามนุษย์', 'ข้ามแดน', 'ขนแรงงาน', 'หนีเข้าเมือง']
    brk_hits = [k for k in brk_kw if k in t]
    
    if sov_hits:
        return 'sovereignty', 'สัญชาติ อธิปไตย และสิทธิการเมือง', ", ".join(sov_hits)
    elif dis_hits:
        return 'disease', 'โรคระบาดและสุขอนามัยสาธารณะ', ", ".join(dis_hits)
    elif eco_hits:
        return 'economic', 'การแย่งอาชีพ เศรษฐกิจ และนอมินี', ", ".join(eco_hits)
    elif brk_hits:
        return 'broker', 'ขบวนการลักลอบและนายหน้าต้มตุ๋น', ", ".join(brk_hits)
    else:
        return 'other', 'ประเด็นความสัมพันธ์และอื่นๆ', "ต่างด้าว/ข้ามชาติทั่วไป"

def main():
    print("Loading normalized atomic records...")
    records = get_normalized_records("data/th_verify.db", filter_broadcasts=True)
    print(f"Loaded {len(records)} atomic records.")

    # 1. Prepare Article 1 Dataset (All 27,231 claims)
    art1_rows = []
    for r in records:
        era = assign_era(r.get("published_year"))
        art1_rows.append({
            "claim_id": r["id"],
            "source": r["source"],
            "published_date": r["published_date"],
            "published_year": r["published_year"],
            "era": era,
            "claim_text": r["claim_clean"],
            "raw_title": r["title_raw"],
            "verdict": r["verdict_normalized"],
            "raw_verdict": r["verdict_raw"],
            "verdict_origin": r["verdict_origin"],
            "topic_code": r["topic_id"],
            "topic_name": r["topic_name"],
            "source_url": r["url"]
        })

    # Write Article 1 CSV
    csv1_path = DATASET_DIR / "article1_11years_claims.csv"
    with open(csv1_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(art1_rows[0].keys()))
        writer.writeheader()
        writer.writerows(art1_rows)
    print(f"Article 1 CSV exported: {csv1_path} ({len(art1_rows)} rows)")

    # Write Article 1 JSONL
    jsonl1_path = DATASET_DIR / "article1_11years_claims.jsonl"
    with open(jsonl1_path, "w", encoding="utf-8") as f:
        for row in art1_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Article 1 JSONL exported: {jsonl1_path}")

    # 2. Prepare Article 2 Dataset (Migrant 869 claims)
    migrant_rx = re.compile(
        r'ต่างด้าว|แรงงานต่าง|พม่า|กัมพูชา|เขมร|ลาว|เวียดนาม|โรฮิงญา|สัญชาติ|เกาะกูด|mou\s*44|แย่งอาชีพ|แย่งงาน|ข้ามชาติ|ประชากรข้ามชาติ',
        re.IGNORECASE
    )
    art2_rows = []
    for r in records:
        if migrant_rx.search(r["claim_clean"]):
            era = assign_era(r.get("published_year"))
            frame_id, frame_th, matched_kws = categorize_migrant_narrative(r["claim_clean"])
            art2_rows.append({
                "claim_id": r["id"],
                "source": r["source"],
                "published_date": r["published_date"],
                "published_year": r["published_year"],
                "era": era,
                "narrative_frame_id": frame_id,
                "narrative_frame_th": frame_th,
                "matched_keywords": matched_kws,
                "claim_text": r["claim_clean"],
                "raw_title": r["title_raw"],
                "verdict": r["verdict_normalized"],
                "raw_verdict": r["verdict_raw"],
                "verdict_origin": r["verdict_origin"],
                "source_url": r["url"]
            })

    # Write Article 2 CSV
    csv2_path = DATASET_DIR / "article2_migrant_claims.csv"
    with open(csv2_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(art2_rows[0].keys()))
        writer.writeheader()
        writer.writerows(art2_rows)
    print(f"Article 2 CSV exported: {csv2_path} ({len(art2_rows)} rows)")

    # Write Article 2 JSONL
    jsonl2_path = DATASET_DIR / "article2_migrant_claims.jsonl"
    with open(jsonl2_path, "w", encoding="utf-8") as f:
        for row in art2_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Article 2 JSONL exported: {jsonl2_path}")

    # 3. Create DATA_DICTIONARY.md
    dict_md = """# 📚 Data Dictionary & Open Methodology: Prachatai Fact-Check Datasets

This data package accompanies the 2-part investigative journalism series produced by **TH Verify** in collaboration with **สำนักข่าวประชาไท (Prachatai)**:
1. **Article 1:** *11 Years of Misinformation in Thailand (2015–2026): Macro Topic Evolution & Turning Points*
2. **Article 2:** *Deep-Dive Investigation: 7 Years of Cross-Border & Migrant Disinformation Narratives (2020–2026)*

All datasets are exported in UTF-8 with BOM for immediate compatibility with Excel, Google Sheets, Python (pandas), and R.

---

## 📁 Package Contents

| Filename | Records | Description |
| :--- | ---: | :--- |
| `article1_11years_claims.csv` | 27,231 | Full longitudinal atomic claim dataset across 10 macro topics (2015–2026). |
| `article1_11years_claims.jsonl` | 27,231 | Same dataset formatted as newline-delimited JSON. |
| `article2_migrant_claims.csv` | 869 | Filtered and framing-annotated claims focusing on migrant and border issues. |
| `article2_migrant_claims.jsonl` | 869 | Same dataset formatted as newline-delimited JSON. |

---

## 🏷️ Schema: `article1_11years_claims.csv`

| Column | Data Type | Example | Description |
| :--- | :--- | :--- | :--- |
| `claim_id` | Integer | `16009` | Unique primary key in canonical database (`fact_checks.id`). |
| `source` | String | `sure_share` | Fact-checking publisher (`afnc`, `sure_share`, `cofact`, `afp`, `thaipbs`). |
| `published_date` | String | `2023-04-15` | Normalized ISO date of publication (YYYY-MM-DD). |
| `published_year` | String | `2023` | Year of publication. |
| `era` | String | `ยุคที่ 3: 2565–2566...` | Historical era classification (Eras 1 through 4). |
| `claim_text` | String | `สูตรยาสมุนไพร แก้โรคมะเร็ง...` | Clean claim text with verdict boilerplate & talk-show affixes removed. |
| `raw_title` | String | `ข่าวปลอม อย่าแชร์! สูตรยาสมุนไพร...` | Original verbatim headline scraped from the source. |
| `verdict` | String | `false` | Standardized 6-class verdict (`false`, `true`, `misleading`, `altered_media`, `scam_alert`, `satire`). |
| `raw_verdict` | String | `ข่าวปลอม` | Original verdict label from publisher or reviewer. |
| `verdict_origin` | String | `human` | Origin trust tier (`human`, `source`, `heuristic`, `llm`). |
| `topic_code` | String | `T01` | High-precision topic code (`T01` to `T10`, `T99_other`). |
| `topic_name` | String | `สุขภาพ อาหาร และยา` | Thai macro topic label. |
| `source_url` | String | `https://...` | Direct link to original fact-check publication. |

---

## 🏷️ Schema: `article2_migrant_claims.csv`

Includes all columns above plus specialized Layer B narrative framing fields:

| Column | Data Type | Example | Description |
| :--- | :--- | :--- | :--- |
| `narrative_frame_id` | String | `sovereignty` | Framing category: `sovereignty`, `disease`, `economic`, `broker`, `other`. |
| `narrative_frame_th` | String | `สัญชาติ อธิปไตย และสิทธิการเมือง` | Detailed Thai narrative frame description. |
| `matched_keywords` | String | `สัญชาติ, เลือกตั้ง` | Specific trigger terms detected in the claim. |

---

## 🔬 Methodology & Non-Destructive Ingestion Principles
1. **Non-Destructive Ingestion:** The canonical SQLite database is never altered. Normalization and cleaning occur via in-memory abstraction (`src/th_verify/normalized.py`).
2. **Talk-Show & Podcast Filtering:** Multi-topic broadcast roundups (`LIVE EP.`, `HIGHLIGHT`, `คุยข่าว`) are excluded to preserve atomic granularity.
3. **Compound NLP Matching:** High-precision Thai compound parsing prevents false positive keyword collisions (e.g. distinguishing `สภาวะดวงตา` [health] from `สภาผู้แทน` [politics]).

---
*Generated by TH Verify Open Data Pipeline for สำนักข่าวประชาไท (Prachatai) — September 3, 2026*
"""
    dict_path = DATASET_DIR / "DATA_DICTIONARY.md"
    with open(dict_path, "w", encoding="utf-8") as f:
        f.write(dict_md)
    print(f"Data Dictionary created: {dict_path}")

if __name__ == "__main__":
    main()
