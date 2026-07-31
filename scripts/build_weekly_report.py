#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_weekly_report.py — Generates the Weekly Fact-Check & System Report for TH Verify.
Queries data/th_verify.db and produces Markdown and HTML outputs.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent))
from _freshness import assert_fresh  # noqa: E402

DB_PATH = Path('data/th_verify.db')
OUTPUT_DIR = Path('data/reports')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

WEEKLY_MD_PATH = OUTPUT_DIR / 'weekly_report_2026_w31.md'
WEEKLY_HTML_PATH = OUTPUT_DIR / 'weekly_report_2026_w31.html'

def generate_report():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    assert_fresh(conn)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Total statistics
    total_records = cur.execute("SELECT COUNT(*) FROM fact_checks").fetchone()[0]
    total_clusters = cur.execute("SELECT COUNT(*) FROM claim_clusters").fetchone()[0]
    total_cluster_members = cur.execute("SELECT COUNT(*) FROM claim_cluster_members").fetchone()[0]

    # 2. Source statistics
    sources = cur.execute("""
        SELECT source, COUNT(*) as count, MIN(published_at) as oldest, MAX(published_at) as newest, MAX(last_seen_at) as last_seen
        FROM fact_checks
        GROUP BY source
        ORDER BY count DESC
    """).fetchall()
    sources = [dict(s) for s in sources]

    # 3. Label Provenance Tiers
    origins = cur.execute("""
        SELECT 
            CASE 
                WHEN verdict_origin = 'source' THEN 'Source (Native Gold)'
                WHEN verdict_origin = 'human' THEN 'Human Verified (Gold Standard)'
                WHEN verdict_origin = 'heuristic' THEN 'Heuristic Guesses (Low Trust)'
                WHEN verdict_origin = 'llm' THEN 'LLM Extracted (Medium Trust)'
                ELSE 'Unlabeled / Pending Queue'
            END as origin_label,
            verdict_origin,
            COUNT(*) as count
        FROM fact_checks
        GROUP BY verdict_origin
        ORDER BY count DESC
    """).fetchall()
    origins = [dict(o) for o in origins]

    # 4. Top Verdicts
    verdicts = cur.execute("""
        SELECT verdict, COUNT(*) as count
        FROM fact_checks
        GROUP BY verdict
        ORDER BY count DESC
        LIMIT 10
    """).fetchall()
    verdicts = [dict(v) for v in verdicts]

    # 5. Top Categories
    categories = cur.execute("""
        SELECT category, COUNT(*) as count
        FROM fact_checks
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY count DESC
        LIMIT 10
    """).fetchall()
    categories = [dict(c) for c in categories]

    # 6. Recent fact-checks in dataset
    recent_checks = cur.execute("""
        SELECT id, source, title, verdict, published_at, source_url
        FROM fact_checks
        ORDER BY published_at DESC
        LIMIT 15
    """).fetchall()
    recent_checks = [dict(r) for r in recent_checks]

    # 7. Sure & Share Human Labeling Progress
    sure_share_stats = cur.execute("""
        SELECT verdict_origin, COUNT(*) as count
        FROM fact_checks
        WHERE source = 'sure_share'
        GROUP BY verdict_origin
        ORDER BY count DESC
    """).fetchall()
    sure_share_stats = [dict(s) for s in sure_share_stats]

    # 8. Sync Runs Audit
    sync_runs = cur.execute("""
        SELECT source, mode, status, COUNT(*) as count, MAX(started_at) as last_started
        FROM sync_runs
        GROUP BY source, mode, status
        ORDER BY source, mode
    """).fetchall()
    sync_runs = [dict(sr) for sr in sync_runs]

    # Derived summary figures. These were previously hardcoded in the template,
    # so the executive summary drifted out of step with the tables underneath it --
    # the 2026-07-31 edition claimed 80 human-labelled episodes directly above a
    # table reading 164. Anything asserted in prose is computed here.
    by_origin = {o["verdict_origin"]: o["count"] for o in origins}
    human_n = by_origin.get("human", 0)
    skipped_n = by_origin.get("human_skipped", 0)
    gold_n = by_origin.get("source", 0) + human_n
    gold_pct = gold_n / total_records * 100 if total_records else 0
    pending_n = by_origin.get("", 0)
    coverage = ", ".join(
        f'**{s["source"].upper()}** ({s["count"] / total_records * 100:.1f}%)'
        for s in sources)
    sync_run_total = sum(sr["count"] for sr in sync_runs) if sync_runs else 0
    db_mb = DB_PATH.stat().st_size / 1_048_576
    report_dt = datetime.now()
    period = f"Week {report_dt.isocalendar().week} (generated {report_dt:%Y-%m-%d})"
    freshest = max((s["last_seen"] or "") for s in sources) if sources else "unknown"

    conn.close()

    # Build Markdown Content
    md = f"""# 📊 TH Verify Weekly Status & Intelligence Report

**Report Period:** {period}  
**Database Snapshot:** `data/th_verify.db` ({db_mb:,.1f} MB WAL SQLite)  
**Data Current To:** {freshest}  
**Total Claims Archived:** **{total_records:,}**  
**Semantic Claim Clusters:** **{total_clusters:,}** (mapping **{total_cluster_members:,}** records)  

---

## 1. Executive Summary & Weekly Highlights

This weekly report summarizes database status, publisher archiving coverage, label provenance, recent claim trends, and technical infrastructure readiness across the **TH Verify** ecosystem.

### Key Weekly Metrics:
- **Canonical Fact-Check Records:** **{total_records:,}** claims indexed across 5 major Thai fact-checking institutions.
- **Publisher Coverage:** Active deltas across {coverage}.
- **Gold Label Proportion:** **{gold_pct:.1f}%** of records ({gold_n:,}) hold verified native source or human-reviewed gold verdicts.
- **Human Labeling Queue:** {human_n:,} episodes verified in `/review` room ({skipped_n:,} skipped as unjudgeable); {pending_n:,} records awaiting labelling.

---

## 2. Fact-Check Archiving by Publisher

| Publisher / Source | Code | Total Records | Share (%) | Oldest Record | Newest Record | Last System Sync |
| :--- | :--- | ---: | ---: | :--- | :--- | :--- |
"""
    source_map = {
        'afnc': 'ศูนย์ต่อต้านข่าวปลอม ประเทศไทย',
        'sure_share': 'ชัวร์ก่อนแชร์ (MCOT)',
        'cofact': 'Cofact Thailand',
        'afp': 'AFP Fact Check Thailand',
        'thaipbs': 'Thai PBS Verify'
    }
    for s in sources:
        src = s['source']
        name = source_map.get(src, src)
        cnt = s['count']
        pct = (cnt / total_records) * 100
        oldest = str(s['oldest'])[:10] if s['oldest'] else '-'
        newest = str(s['newest'])[:10] if s['newest'] else '-'
        last_s = str(s['last_seen'])[:16].replace('T', ' ') if s['last_seen'] else '-'
        md += f"| **{name}** | `{src}` | {cnt:,} | {pct:.1f}% | {oldest} | {newest} | {last_s} |\n"

    md += f"""
---

## 3. Label Provenance & Data Trust Tiers

The repository enforces strict trust tiers (`verdict_origin`) to maintain model training purity and prevent unverified heuristic noise:

| Trust Tier | Provenance Code | Record Count | Share (%) | Quality Description |
| :--- | :--- | ---: | ---: | :--- |
"""
    for o in origins:
        lbl = o['origin_label']
        code = o['verdict_origin'] or "''"
        cnt = o['count']
        pct = (cnt / total_records) * 100
        desc = ""
        if code == 'source':
            desc = "Publisher native label (Gold Standard)"
        elif code == 'human':
            desc = "Reviewed in `/review` room by analyst (Gold Standard)"
        elif code == 'llm':
            desc = "Extracted via Ollama `qwen2.5:14b` with verbatim quote guard"
        elif code == 'heuristic':
            desc = "Keyword/Gemini guess (Excluded from briefs by policy)"
        else:
            desc = "Unlabeled / Pending human video evaluation"
        md += f"| **{lbl}** | `{code}` | {cnt:,} | {pct:.1f}% | {desc} |\n"

    md += f"""
---

## 4. Top Verdict Categories & Topic Trends

### Breakdown by Verdict Outcome:
"""
    for v in verdicts:
        v_name = v['verdict']
        v_cnt = v['count']
        v_pct = (v_cnt / total_records) * 100
        md += f"- **{v_name}:** {v_cnt:,} records ({v_pct:.1f}%)\n"

    md += """
### Top Domain Categories:
"""
    for c in categories:
        c_name = c['category']
        c_cnt = c['count']
        md += f"- **{c_name}:** {c_cnt:,} articles\n"

    md += f"""
---

## 5. Recent Fact-Checks Spotlight

Below is a curated sample of recent claims indexed in the archive:

| Source | Date | Verdict | Title / Headline |
| :--- | :--- | :--- | :--- |
"""
    for r in recent_checks[:10]:
        src = r['source'].upper()
        pub = str(r['published_at'])[:10] if r['published_at'] else '-'
        verd = r['verdict']
        title = r['title'][:80] + ("..." if len(r['title']) > 80 else "")
        md += f"| `{src}` | {pub} | **{verd}** | {title} |\n"

    md += f"""
---

## 6. Technical Infrastructure & Operations Status

- **Database Engine:** SQLite 3 in WAL Journal Mode (`data/th_verify.db`, {db_mb:,.1f} MB).
- **Public Service API:** FastAPI read-only server (`TH_VERIFY_READONLY=1`) configured on `127.0.0.1:8943` behind Cloudflare tunnel for `check-before.org`.
- **Search Index:** Embeddings snapshot (`embeddings.npy` + `meta.jsonl`) supporting semantic retrieval with `intfloat/multilingual-e5-small`.
- **Crawler Health:** {sync_run_total:,} backfill and delta sync runs logged in `sync_runs`.

---

## 7. Strategic Recommendations for Next Week

1. **Human Review Acceleration:** Continue labeling Sure & Share YouTube episodes at `/review` to expand gold labels beyond the current {human_n:,} verified episodes.
2. **Search Index Refresh:** Run `th-verify index` following the latest delta syncs to ensure newly ingested claims are searchable on the public check service.
3. **Monthly Brief Preparation:** Prepare for the upcoming August 1st `build_brief.py` cron execution to generate `brief_2026-08.md`.
"""

    return md

def main():
    md_content = generate_report()
    
    with open(WEEKLY_MD_PATH, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"Weekly report generated at: {WEEKLY_MD_PATH}")

if __name__ == '__main__':
    main()
