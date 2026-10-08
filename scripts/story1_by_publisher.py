#!/usr/bin/env python3
"""Story 1 tables on the publisher-by-publisher frame (all years, no blended trend line).

Reads the canonical run + the audit's near-duplicate groups; writes
runs/20261004_story1_by_publisher_v001/. Topic groupings below are an analyst
grouping of model topics, not model output.
"""
import collections, csv, hashlib, json, re, sqlite3, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'runs/20260908_bertopic_v001'
AUD = ROOT / 'runs/20261004_audit_v001'
OUT = ROOT / 'runs/20261004_story1_by_publisher_v001'
C = collections.Counter
csv.field_size_limit(10 ** 9)
GROUPS = {'health_food_T0': {0}, 'virus_T4_T7_T18': {4, 7, 18}, 'agency_impersonation_T1_T2_T11': {1, 2, 11},
          'cambodia_border_T6': {6}, 'unclustered': {-1}}
SRC = ['sure_share', 'afnc', 'afp', 'cofact', 'thaipbs']


def rd(p):
    with open(p, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def wr(name, rows):
    with open(OUT / name, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    A = rd(RUN / 'assignments.csv'); years = sorted({r['year'] for r in A})
    # 1. publisher x year x topic group
    rows = []
    for s in SRC + ['all']:
        for y in years:
            g = [r for r in A if r['year'] == y and (s == 'all' or r['source'] == s)]
            row = {'source': s, 'year': y, 'year_be': int(y) + 543, 'records': len(g), 'partial_year': y in ('2015', '2026')}
            for name, ts in GROUPS.items():
                n = sum(int(r['topic_id']) in ts for r in g)
                row[name] = n; row[name + '_pct'] = round(n / len(g) * 100, 2) if g else ''
            rows.append(row)
    wr('publisher_year_topic_groups.csv', rows)
    # 2. publisher summary + label source
    summ = []
    for s in SRC:
        g = [r for r in A if r['source'] == s]
        summ.append({'source': s, 'records': len(g), 'share_pct': round(len(g) / len(A) * 100, 1), 'first_date': min(r['date'] for r in g),
                     'last_date': max(r['date'] for r in g), 'verdict_from_publisher': sum(r['verdict_origin'] == 'source' for r in g),
                     'verdict_assigned_by_project_reviewers': sum(r['verdict_origin'] == 'human' for r in g)})
    wr('publisher_summary.csv', summ)
    # 3. topic rows for the three impersonation topics, raw vs near-duplicate-collapsed
    unique = list(dict.fromkeys(r['claim_text'] for r in A)); tix = {t: i for i, t in enumerate(unique)}
    g95 = np.load(AUD / 'near_dup_groups_cos095.npy')
    grec = [g95[tix[r['claim_text']]] for r in A]
    imp = []
    for t, nm in ((2, 'driving_licence'), (11, 'victim_refund'), (1, 'invest_dividend'), (6, 'cambodia_border'), (4, 'virus_cures'), (7, 'infection_reports'), (18, 'vaccine')):
        for y in years:
            sel = [(r, gi) for r, gi in zip(A, grec) if r['year'] == y and int(r['topic_id']) == t]
            den = sum(r['year'] == y for r in A)
            imp.append({'topic_id': t, 'label_draft': nm, 'year': y, 'year_be': int(y) + 543, 'records': len(sel), 'all_records_that_year': den,
                        'share_pct': round(len(sel) / den * 100, 2), 'afnc_records': sum(r['source'] == 'afnc' for r, _ in sel),
                        'distinct_near_duplicate_claims_cos095': len({gi for _, gi in sel})})
    wr('named_topics_by_year.csv', imp)
    # 4. Sure&Share shorts
    ss = [r for r in A if r['source'] == 'sure_share']
    is_short = lambda r: '#shorts' in (r['title'] or '').lower() or 'shorts' in (r['url'] or '')
    wr('sure_share_shorts_by_year.csv', [{'year': y, 'year_be': int(y) + 543, 'records': sum(r['year'] == y for r in ss),
        'shorts': sum(is_short(r) for r in ss if r['year'] == y),
        'shorts_pct': round(sum(is_short(r) for r in ss if r['year'] == y) / max(sum(r['year'] == y for r in ss), 1) * 100)} for y in years])
    # 5. blended vs within-publisher (the comparison the draft must not blend)
    f = lambda g, ts: round(sum(int(r['topic_id']) in ts for r in g) / len(g) * 100, 1)
    blend = {'health_food_all_2019': f([r for r in A if r['year'] == '2019'], {0}), 'health_food_all_2020': f([r for r in A if r['year'] == '2020'], {0}),
             'health_food_sure_share_2019': f([r for r in ss if r['year'] == '2019'], {0}), 'health_food_sure_share_2020': f([r for r in ss if r['year'] == '2020'], {0}),
             'afnc_share_2019': f([r for r in A if r['year'] == '2019'], set()) if False else round(sum(r['source'] == 'afnc' for r in A if r['year'] == '2019') / sum(r['year'] == '2019' for r in A) * 100, 1),
             'afnc_share_2020': round(sum(r['source'] == 'afnc' for r in A if r['year'] == '2020') / sum(r['year'] == '2020' for r in A) * 100, 1)}
    # 6. reading sample for the big Topic 0 (not covered by the 20261004 purity samples); refuses to overwrite a filled sheet
    import random
    sheet = OUT / 'topic0_samples.csv'
    if sheet.exists() and any((r.get('human_pure') or r.get('human_note')) for r in rd(sheet)):
        print('topic0_samples.csv already has human entries - not regenerated')
    else:
        random.seed(20261004); picked = []
        for s_, n in (('sure_share', 40), ('afnc', 30)):
            g = [r for r in A if r['source'] == s_ and r['topic_id'] == '0']
            picked += sorted(random.sample(g, n), key=lambda r: r['date'])
        wr('topic0_samples.csv', [{'topic_id': 0, 'topic_label_draft': 'สุขภาพ อาหาร และเรื่องใกล้ตัว (ยังไม่ผ่านการตรวจ)', 'id': r['id'], 'year': r['year'],
                                   'source': r['source'], 'title': r['title'], 'claim_text': r['claim_text'], 'url': r['url'], 'human_pure': '', 'human_note': ''} for r in picked])
    manifest = {'run': OUT.name, 'what': 'Story 1 tables per publisher; no blended trend line across the 2019/2020 publisher switch',
                'script': 'scripts/story1_by_publisher.py', 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'inputs_sha256': {'assignments.csv': hashlib.sha256((RUN / 'assignments.csv').read_bytes()).hexdigest(),
                                  'near_dup_groups_cos095.npy': hashlib.sha256((AUD / 'near_dup_groups_cos095.npy').read_bytes()).hexdigest()},
                'topic_groups': {k: sorted(v) for k, v in GROUPS.items()}, 'topic_groups_are': 'analyst grouping of model topics, not model output',
                'blended_vs_within_publisher': blend, 'status': 'derived from the canonical run; topic names not human-validated'}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(blend, indent=1))


if __name__ == '__main__':
    main()
