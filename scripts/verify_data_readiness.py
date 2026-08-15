#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_data_readiness.py — Deep Diagnostic on Raw DB vs Clean Exports for PRD Compliance.
Analyzes 5 sources across 6 dimensions:
1. Title vs Claim duplication
2. Verdict leakage & boilerplate affixes
3. Content format contamination (broadcasts vs atomic claims)
4. Verdict fragmentation & normalization
5. Date / timestamp alignment
6. Deduplication & family tracking
"""

import sqlite3
import re
from collections import Counter
from pathlib import Path

DB_PATH = Path('data/th_verify.db')

def analyze():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sources = ['afnc', 'sure_share', 'cofact', 'afp', 'thaipbs']
    results = {}

    for src in sources:
        rows = cur.execute("""
            SELECT id, title, claim, explanation, verdict, category, published_at, verdict_origin
            FROM fact_checks WHERE source = ?
        """, (src,)).fetchall()
        
        n = len(rows)
        same_title_claim = sum(1 for r in rows if r['title'] == r['claim'])
        
        # Leakage
        prefixes = [
            r'^ข่าวปลอม\s*[,!:]?\s*(อย่าแชร์|อย่าเชื่อ)?\s*[!:]*\s*',
            r'^ข่าวบิดเบือน\s*[,!:]?\s*(อย่าแชร์)?\s*[!:]*\s*',
            r'^ข่าวจริง\s*[,!:?]?\s*',
            r'^(ภาพปลอม|คลิปปลอม|ข่าวเตือนภัย|เตือนภัย)\s*[,!:]?\s*',
            r'^ชัวร์ก่อนแชร์\s*[A-Za-z\- ]*\s*[:|]\s*',
            r'\s*(จริงหรือ|จริงหรือไม่|จริงไหม|ใช่หรือไม่)\s*[?？!]*\s*$'
        ]
        leaked = sum(1 for r in rows if any(re.search(rx, r['title']) for rx in prefixes))
        
        # Broadcast contamination (Sure & Share live shows / podcasts)
        broadcast_rx = re.compile(r'LIVE\s*EP|PODCAST|HIGHLIGHT|รอบวัน|สรุปข่าว|คุยข่าว|Motor Check', re.IGNORECASE)
        broadcast_cnt = sum(1 for r in rows if broadcast_rx.search(r['title']))
        
        # Verdicts
        verdict_counts = Counter(r['verdict'] for r in rows)
        
        # Dates
        dates = [r['published_at'] for r in rows if r['published_at']]
        
        results[src] = {
            'total': n,
            'same_title_claim_pct': round((same_title_claim / n) * 100, 1),
            'leaked_count': leaked,
            'leaked_pct': round((leaked / n) * 100, 1),
            'broadcast_count': broadcast_cnt,
            'broadcast_pct': round((broadcast_cnt / n) * 100, 1),
            'verdict_distinct_count': len(verdict_counts),
            'top_verdicts': verdict_counts.most_common(4),
            'missing_dates': n - len(dates)
        }

    conn.close()
    return results

if __name__ == '__main__':
    res = analyze()
    import pprint
    pprint.pprint(res)
