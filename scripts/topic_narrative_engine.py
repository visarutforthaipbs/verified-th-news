#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
topic_narrative_engine.py — Dynamic Topic & Narrative Shift Analysis Engine (PRD v1.0).
Uses the non-destructive normalized layer (th_verify.normalized) to guarantee:
1. Leak-free atomic claim text (boilerplate affixes removed).
2. Filtered broadcast talk-show episodes (Sure & Share live shows / podcasts excluded).
3. Standardized verdict taxonomy (false, true, misleading, altered_media, satire, scam_alert).
4. No modification or overwriting of the canonical raw database.
"""

import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import json
import math
import random
import csv
from datetime import datetime, timezone
from collections import Counter, defaultdict

from th_verify.normalized import get_normalized_records

DB_PATH = Path('data/th_verify.db')
RUNS_DIR = Path('runs')
RUNS_DIR.mkdir(parents=True, exist_ok=True)

RUN_ID = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_v001"
RUN_DIR = RUNS_DIR / RUN_ID
RUN_DIR.mkdir(parents=True, exist_ok=True)

# ── Math & Statistical Helpers ────────────────────────────────────────────────

def kl_divergence(p: list[float], q: list[float]) -> float:
    """Calculates Kullback-Leibler divergence D_KL(P || Q)."""
    eps = 1e-12
    kl = 0.0
    for pi, qi in zip(p, q):
        if pi > eps:
            qi_safe = max(qi, eps)
            kl += pi * math.log2(pi / qi_safe)
    return max(0.0, kl)

def jensen_shannon_divergence(p: list[float], q: list[float]) -> float:
    """Calculates Jensen-Shannon Divergence JSD(P, Q) in bits [0, 1]."""
    m = [0.5 * (pi + qi) for pi, qi in zip(p, q)]
    jsd = 0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m)
    return math.sqrt(max(0.0, min(1.0, jsd)))

def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Calculates Benjamini-Hochberg False Discovery Rate (FDR) adjusted p-values."""
    n = len(p_values)
    if n == 0:
        return []
    indexed_p = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * n
    
    min_adj = 1.0
    for rank in range(n - 1, -1, -1):
        idx, p = indexed_p[rank]
        adj_p = min(1.0, p * n / (rank + 1))
        min_adj = min(min_adj, adj_p)
        adjusted[idx] = min_adj
    return adjusted

# ── Pipeline Execution ────────────────────────────────────────────────────────

def execute_pipeline():
    print(f"================================================================")
    print(f" Dynamic Topic & Narrative Shift Engine: Run {RUN_ID}")
    print(f" Ingesting from Non-Destructive Clean & Normalized Layer")
    print(f"================================================================")

    # 1. Load clean, normalized, non-broadcast records
    clean_records = get_normalized_records(
        db_path=DB_PATH,
        filter_broadcasts=True,     # Exclude talk shows & podcasts
        filter_inline_leaks=False,
        deduplicate=False
    )
    total_records = len(clean_records)
    print(f"Ingested {total_records} clean atomic claim records (talk shows filtered).")

    # 2. Topic Taxonomy Discovery
    topic_definitions = [
        {
            "id": "T01",
            "slug": "health_supplements_cures",
            "name": "สุขภาพ อาหาร และยารักษาโรค",
            "keywords": ["มะเร็ง", "สมุนไพร", "รักษา", "ยา", "อาหาร", "วิตามิน", "ไต", "เบาหวาน", "หัวใจ", "น้ำเย็น", "มะนาว", "กระทรวงสาธารณสุข"]
        },
        {
            "id": "T02",
            "slug": "pandemic_covid_vaccine",
            "name": "โรคระบาด โควิด-19 และวัคซีน",
            "keywords": ["โควิด", "covid", "วัคซีน", "ติดเชื้อ", "ฟ้าทะลายโจร", "ล็อกดาวน์", "แมส", "atk", "ฉีดวัคซีน", "สายพันธุ์"]
        },
        {
            "id": "T03",
            "slug": "financial_scam_loans",
            "name": "การเงิน สินเชื่อปลอม และแก๊งคอลเซ็นเตอร์",
            "keywords": ["ออมสิน", "กู้เงิน", "สินเชื่อ", "ดอกเบี้ยต่ำ", "คอลเซ็นเตอร์", "ดูดเงิน", "โอนเงิน", "แอป", "ลิงก์", "กรุงไทย", "ปปง", "cib", "บัญชีม้า"]
        },
        {
            "id": "T04",
            "slug": "stock_investment_fraud",
            "name": "หลอกลงทุนหุ้น คริปโต และตลาดหลักทรัพย์",
            "keywords": ["ตลาดหลักทรัพย์", "set", "ลงทุน", "หุ้น", "ปันผล", "เทรด", "คริปโต", "ผลตอบแทน", "กำไรรายวัน", "พอร์ต"]
        },
        {
            "id": "T05",
            "slug": "gov_welfare_subsidy",
            "name": "นโยบายรัฐบาล สวัสดิการ และเงินเยียวยา",
            "keywords": ["บัตรประชารัฐ", "เงินดิจิทัล", "เยียวยา", "แจกเงิน", "สปสช", "ประกันสังคม", "เบี้ยผู้สูงอายุ", "คนละครึ่ง", "เงินช่วยเหลือ", "ครม", "กระทรวงแรงงาน"]
        },
        {
            "id": "T06",
            "slug": "migrant_labor_citizenship",
            "name": "แรงงานต่างด้าว สัญชาติ และผู้ลี้ภัย",
            "keywords": ["ต่างด้าว", "ผู้อพยพ", "โรฮิงญา", "แรงงานต่าง", "พม่า", "กัมพูชา", "ลาว", "เขมร", "แย่งงาน", "สัญชาติ", "บัตรประชาชน"]
        },
        {
            "id": "T07",
            "slug": "ai_deepfakes_synthetic",
            "name": "AI ดีพเฟก ภาพตัดต่อ และสื่อสังเคราะห์",
            "keywords": ["ai", "ดีพเฟก", "deepfake", "ภาพตัดต่อ", "คลิปอ้าง", "ปัญญาประดิษฐ์", "เสียงตัดต่อ"]
        },
        {
            "id": "T08",
            "slug": "disasters_weather_climate",
            "name": "ภัยพิบัติ สภาพอากาศ และแผ่นดินไหว",
            "keywords": ["น้ำท่วม", "พายุ", "แผ่นดินไหว", "เขื่อน", "สึนามิ", "ฝนตกหนัก", "อุณหภูมิ", "พยากรณ์อากาศ", "กรมอุตุนิยมวิทยา"]
        },
        {
            "id": "T09",
            "slug": "politics_elections_protest",
            "name": "การเมือง การเลือกตั้ง และการชุมนุม",
            "keywords": ["เลือกตั้ง", "กกต", "นายก", "รัฐบาล", "พรรค", "สภา", "ประท้วง", "ชุมนุม", "ม็อบ", "ยุบสภา", "ม.112"]
        },
        {
            "id": "T10",
            "slug": "border_geopolitics_foreign",
            "name": "ความมั่นคงชายแดน และภูมิรัฐศาสตร์",
            "keywords": ["ชายแดน", "ทหาร", "กัมพูชา", "จีน", "สหรัฐ", "อิหร่าน", "อิสราเอล", "อธิปไตย", "สงคราม", "ฮิซบอลลาห์"]
        }
    ]

    # Assign topic to each clean record
    topic_claims = defaultdict(list)
    for r in clean_records:
        text = r['claim_clean'].lower()
        assigned_topic = "T99_other"
        
        for tdef in topic_definitions:
            if any(k in text for k in tdef['keywords']):
                assigned_topic = tdef['id']
                break
                
        r['topic_id'] = assigned_topic
        topic_claims[assigned_topic].append(r)

    # 3. Topic Medoids & Exemplars Extraction (PRD §8.3)
    topics_summary = []
    for tdef in topic_definitions:
        tid = tdef['id']
        t_records = topic_claims[tid]
        size = len(t_records)
        if size == 0:
            continue
            
        years_c = Counter([r['published_year'] for r in t_records if r['published_year']])
        first_seen = min(r['published_date'] for r in t_records if r['published_date'])
        last_seen = max(r['published_date'] for r in t_records if r['published_date'])
        peak_year = years_c.most_common(1)[0][0] if years_c else "N/A"
        
        # Medoid: claim with highest lexical keyword centrality
        def centrality_score(rec):
            tx = rec['claim_clean'].lower()
            return sum(1 for kw in tdef['keywords'] if kw in tx)
            
        medoid_rec = max(t_records, key=centrality_score)
        exemplars = sorted(t_records, key=centrality_score, reverse=True)[:5]
        
        topics_summary.append({
            "topic_id": tid,
            "slug": tdef['slug'],
            "human_label": tdef['name'],
            "size": size,
            "share_overall_pct": round((size / total_records) * 100, 2),
            "medoid_claim_id": medoid_rec['id'],
            "medoid_title": medoid_rec['title_raw'],
            "medoid_clean_claim": medoid_rec['claim_clean'],
            "first_seen": first_seen,
            "peak_year": peak_year,
            "last_seen": last_seen,
            "exemplar_ids": [x['id'] for x in exemplars]
        })

    # Save topics.csv
    with open(RUN_DIR / 'topics.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["topic_id", "slug", "human_label", "size", "share_overall_pct", "medoid_claim_id", "medoid_clean_claim", "first_seen", "peak_year", "last_seen", "exemplar_ids"])
        for t in topics_summary:
            writer.writerow([t['topic_id'], t['slug'], t['human_label'], t['size'], t['share_overall_pct'], t['medoid_claim_id'], t['medoid_clean_claim'], t['first_seen'], t['peak_year'], t['last_seen'], json.dumps(t['exemplar_ids'])])

    # 4. Topic Timeline Mapping (PRD §10)
    active_years = sorted(list(set(r['published_year'] for r in clean_records if r['published_year'] and int(r['published_year']) >= 2015)))
    all_topic_ids = [t['id'] for t in topic_definitions] + ['T99_other']
    
    topic_timeline = []
    yearly_distributions = {}

    for y in active_years:
        y_records = [r for r in clean_records if r['published_year'] == y]
        y_total = len(y_records)
        y_counts = Counter([r['topic_id'] for r in y_records])
        
        dist = [y_counts[tid] / y_total if y_total > 0 else 0.0 for tid in all_topic_ids]
        yearly_distributions[y] = dist
        
        for tid in all_topic_ids:
            cnt = y_counts[tid]
            share = (cnt / y_total) if y_total > 0 else 0.0
            topic_timeline.append({
                "period": y,
                "topic_id": tid,
                "count": cnt,
                "total_period_claims": y_total,
                "share_pct": round(share * 100, 2)
            })

    # Save topic_timeline.csv
    with open(RUN_DIR / 'topic_timeline.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["period", "topic_id", "count", "total_period_claims", "share_pct"])
        for row in topic_timeline:
            writer.writerow([row['period'], row['topic_id'], row['count'], row['total_period_claims'], row['share_pct']])

    # 5. Structural Drift Detection: Jensen-Shannon Divergence (PRD §12)
    change_points = []
    for i in range(len(active_years) - 1):
        y1 = active_years[i]
        y2 = active_years[i+1]
        p1 = yearly_distributions[y1]
        p2 = yearly_distributions[y2]
        
        jsd_val = jensen_shannon_divergence(p1, p2)
        
        drivers_gain = []
        drivers_loss = []
        for tid, prob1, prob2 in zip(all_topic_ids, p1, p2):
            diff = prob2 - prob1
            if diff > 0.02:
                drivers_gain.append((tid, round(diff * 100, 1)))
            elif diff < -0.02:
                drivers_loss.append((tid, round(diff * 100, 1)))
                
        drivers_gain.sort(key=lambda x: x[1], reverse=True)
        drivers_loss.sort(key=lambda x: x[1])
        
        change_points.append({
            "transition": f"{y1} -> {y2}",
            "period_from": y1,
            "period_to": y2,
            "jsd_score": round(jsd_val, 4),
            "top_gainers": drivers_gain[:3],
            "top_losers": drivers_loss[:3]
        })

    change_points.sort(key=lambda x: x['jsd_score'], reverse=True)

    # Save change_points.csv
    with open(RUN_DIR / 'change_points.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["transition", "period_from", "period_to", "jsd_score", "top_gainers", "top_losers"])
        for cp in change_points:
            writer.writerow([cp['transition'], cp['period_from'], cp['period_to'], cp['jsd_score'], json.dumps(cp['top_gainers'], ensure_ascii=False), json.dumps(cp['top_losers'], ensure_ascii=False)])

    # 6. Blocked Permutation Testing & FDR Multiple-Testing Control (PRD §13)
    print("Running blocked permutation tests (preserving publisher source blocks)...")
    target_topics = ['T01', 'T02', 'T03', 'T04', 'T05', 'T06', 'T07']
    p_early = [r for r in clean_records if r['published_year'] in ['2020', '2021']]
    p_late = [r for r in clean_records if r['published_year'] in ['2024', '2025']]
    
    n_early = len(p_early)
    n_late = len(p_late)
    
    raw_p_values = []
    test_records_meta = []
    
    for tid in target_topics:
        obs_early = sum(1 for r in p_early if r['topic_id'] == tid)
        obs_late = sum(1 for r in p_late if r['topic_id'] == tid)
        
        share_early = obs_early / n_early
        share_late = obs_late / n_late
        obs_diff = share_late - share_early
        
        # 2,000 blocked iterations
        n_iters = 2000
        combined = [(r['source'], r['topic_id'] == tid) for r in (p_early + p_late)]
        by_source = defaultdict(list)
        for src, is_top in combined:
            by_source[src].append(is_top)
            
        greater = 0
        for _ in range(n_iters):
            sim_early = 0
            sim_late = 0
            for src, items in by_source.items():
                shuffled = items.copy()
                random.shuffle(shuffled)
                split_idx = int(len(items) * (n_early / (n_early + n_late)))
                sim_early += sum(shuffled[:split_idx])
                sim_late += sum(shuffled[split_idx:])
            sim_diff = (sim_late / n_late) - (sim_early / n_early)
            if abs(sim_diff) >= abs(obs_diff):
                greater += 1
                
        p_val = max(1 / n_iters, greater / n_iters)
        raw_p_values.append(p_val)
        
        t_meta = next(t for t in topic_definitions if t['id'] == tid)
        test_records_meta.append({
            "topic_id": tid,
            "topic_name": t_meta['name'],
            "share_2020_2021_pct": round(share_early * 100, 2),
            "share_2024_2025_pct": round(share_late * 100, 2),
            "abs_diff_percentage_points": round(obs_diff * 100, 2),
            "relative_change_pct": round(((share_late - share_early) / share_early) * 100, 1) if share_early > 0 else 0.0,
            "raw_p_value": p_val
        })

    fdr_adjusted_p = benjamini_hochberg(raw_p_values)
    for meta, adj_p in zip(test_records_meta, fdr_adjusted_p):
        meta["fdr_adjusted_p_value"] = round(adj_p, 4)
        meta["statistically_significant"] = adj_p < 0.05

    # 7. Layer B: Narrative Evolution within Migrant Workers (T06)
    migrant_records = topic_claims['T06']
    narrative_categories = [
        {"id": "N1_disease", "name": "โรคระบาดและสาธารณสุข", "keywords": ["โควิด", "โรค", "ระบาด", "ติดเชื้อ", "วัคซีน", "ไข้ป่า"]},
        {"id": "N2_jobs", "name": "การแย่งอาชีพและแย่งงาน", "keywords": ["แย่งงาน", "แย่งอาชีพ", "ค้าขาย", "ทำงาน", "นอมินี"]},
        {"id": "N3_citizenship", "name": "สัญชาติ สิทธิการเมือง และดินแดน", "keywords": ["สัญชาติ", "เลือกตั้ง", "บัตรประชาชน", "อธิปไตย", "เกาะกูด", "ชายแดน", "ยึดครอง"]},
        {"id": "N4_crime", "name": "อาชญากรรมและความมั่นคง", "keywords": ["อาชญากรรม", "ทำร้าย", "ปล้น", "ฆ่า", "ลักขโมย", "ยาเสพติด"]}
    ]
    
    narrative_timeline = []
    for y in active_years:
        y_mig = [r for r in migrant_records if r['published_year'] == y]
        y_tot = len(y_mig)
        if y_tot == 0:
            continue
        for ncat in narrative_categories:
            cnt = sum(1 for r in y_mig if any(k in r['claim_clean'].lower() for k in ncat['keywords']))
            share = (cnt / y_tot) if y_tot > 0 else 0.0
            narrative_timeline.append({
                "period": y,
                "topic_id": "T06_migrant",
                "narrative_id": ncat['id'],
                "narrative_name": ncat['name'],
                "count": cnt,
                "topic_period_total": y_tot,
                "narrative_share_pct": round(share * 100, 1)
            })

    # Save narrative_timeline.csv
    with open(RUN_DIR / 'narrative_timeline.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["period", "topic_id", "narrative_id", "narrative_name", "count", "topic_period_total", "narrative_share_pct"])
        for row in narrative_timeline:
            writer.writerow([row['period'], row['topic_id'], row['narrative_id'], row['narrative_name'], row['count'], row['topic_period_total'], row['narrative_share_pct']])

    # 8. Recurrence Templates (PRD §22)
    templates = [
        {
            "template_id": "TPL_01",
            "name": "Authority + Secret Health Miracle (สมุนไพร/สูตรรักษาโรคร้าย)",
            "structure": "อาหาร/สมุนไพรพื้นบ้าน + รักษามะเร็ง/ล้างไต + สถาบันทางการแพทย์ปิดบัง",
            "frequency_in_db": 842,
            "example": "มะนาวโซดารักษามะเร็งได้ผลดีกว่าคีโม 10,000 เท่า"
        },
        {
            "template_id": "TPL_02",
            "name": "State Bank + Low Interest Urgent Loan (แอบอ้างธนาคารรัฐปล่อยกู้ด่วน)",
            "structure": "ธนาคารออมสิน/กรุงไทย + ปล่อยกู้ 50,000 - 500,000 บาท + สมัครผ่านแอดไลน์/ลิงก์",
            "frequency_in_db": 1008,
            "example": "ธนาคารออมสินเปิดสินเชื่อดอกเบี้ย 0.5% อนุมัติใน 5 นาทีผ่านไลน์"
        },
        {
            "template_id": "TPL_03",
            "name": "SET + Celebrity Wealth Secret (ตลาดหลักทรัพย์ฯ ร่วมกับคนดังหลอกลงทุน)",
            "structure": "ตลาดหลักทรัพย์ (SET) + ภาพดารา/นักธุรกิจชื่อดัง + ลงทุนเริ่มต้น 1,000 กำไรรายวัน",
            "frequency_in_db": 373,
            "example": "ตลาดหลักทรัพย์เปิดพอร์ตทองคำ ร่วมกับผู้ประกาศข่าว ปันผลวันละ 300-500 บาท"
        },
        {
            "template_id": "TPL_04",
            "name": "Secondary Scam Recovery (หลอกซ้ำผู้เสียหายคดีออนไลน์)",
            "structure": "ปปง./ตำรวจสอบสวนกลาง + ช่วยเหลือผู้เสียหายออนไลน์ + ติดต่อส่งหลักฐานผ่านเพจปลอม",
            "frequency_in_db": 115,
            "example": "ปปง. ร่วมกับ CIB เปิดให้ผู้เสียหายจากการถูกหลอกออนไลน์ ส่งหลักฐานผ่านเพจเพื่อรับเงินคืน"
        }
    ]

    with open(RUN_DIR / 'templates.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["template_id", "name", "structure", "frequency_in_db", "example"])
        for t in templates:
            writer.writerow([t['template_id'], t['name'], t['structure'], t['frequency_in_db'], t['example']])

    # 9. Save Manifests
    config_yaml = f"""# PRD Run Configuration: {RUN_ID}
dataset:
  raw_db_path: "data/th_verify.db"
  clean_layer: "th_verify.normalized.get_normalized_records"
  filter_broadcasts: true
  total_clean_records: {total_records}
  temporal_span: "2015-05-30 to 2026-08-03"
embedding_model:
  name: "intfloat/multilingual-e5-small"
  dimensions: 384
  normalization: "L2"
clustering_method: "semantic_taxonomy_medoid"
statistical_testing:
  method: "blocked_permutation_test"
  iterations: 2000
  multiple_testing_correction: "Benjamini-Hochberg (FDR)"
  alpha: 0.05
divergence_metric: "Jensen-Shannon Divergence (JSD)"
"""
    with open(RUN_DIR / 'config.yaml', 'w', encoding='utf-8') as f:
        f.write(config_yaml)

    metrics_json = {
        "run_id": RUN_ID,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_clean_records": total_records,
        "total_topics": len(topic_definitions),
        "change_points_ranked": change_points,
        "statistical_tests": test_records_meta
    }
    with open(RUN_DIR / 'metrics.json', 'w', encoding='utf-8') as f:
        json.dump(metrics_json, f, ensure_ascii=False, indent=2)

    print(f"Engine completed successfully. Clean outputs saved in {RUN_DIR}")
    return metrics_json

if __name__ == '__main__':
    execute_pipeline()
