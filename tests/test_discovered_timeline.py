"""Independent artifact checks; no claim of human narrative validation."""
import csv,json,hashlib,re
from pathlib import Path
from collections import Counter
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runs/20260908_bertopic_v001'
def read(name):
    with (OUT/name).open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
@pytest.fixture(scope='module')
def data():
    if not (OUT/'metrics.json').exists(): pytest.skip('Requires fitted snapshot')
    return read('assignments.csv')

def test_coverage_and_real_topic_discovery(data):
    assert len(data)==14429 and len({r['id'] for r in data})==14429
    counts=Counter(int(r['topic_id']) for r in data)
    assert len(counts)-1==64 and counts[-1]==2324
    assert {r['verdict_origin'] for r in data}<={'human','source'}
    assert len({r['claim_text'] for r in data})==13377
    assert np.load(OUT/'unique_embeddings.npy').shape==(13377,384)
    assert np.load(OUT/'umap10.npy').shape==(13377,10)

def test_timeline_denominators_include_noise(data):
    counts=Counter((r['source'],r['year'],r['topic_id']) for r in data)
    den=Counter((r['source'],r['year']) for r in data)
    for r in data:
        counts['all',r['year'],r['topic_id']]+=1; den['all',r['year']]+=1
    for r in read('topic_timeline.csv'):
        n=den[r['source'],r['year']]; c=counts[r['source'],r['year'],r['topic_id']]
        assert (int(r['count']),int(r['denominator']))==(c,n)
        if n: assert float(r['share_pct'])==pytest.approx(100*c/n)
        else: assert r['share_pct']==''

def test_thai_keywords_and_temporal_frequencies(data):
    for r in read('topics.csv'):
        assert re.search('[ก-๙]',r['machine_keywords'])
        assert r['human_label']==''
        assert r['representative_id'] in {x['id'] for x in data if x['topic_id']==r['topic_id']}
    counts=Counter((r['topic_id'],r['year']) for r in data)
    for r in read('topic_words_over_time.csv'):
        assert int(r['Frequency'])==counts[r['Topic'],r['Timestamp']]

def test_balanced_effect_uses_real_source_sizes(data):
    m=json.loads((OUT/'metrics.json').read_text())
    for row in read('source_balanced_tests.csv'):
        effects=[]
        for block in m['source_test_blocks']:
            source=block['source']
            early=[r for r in data if r['source']==source and r['year'] in ['2020','2021']]
            late=[r for r in data if r['source']==source and r['year'] in ['2024','2025']]
            assert (len(early),len(late))==(block['early_n'],block['late_n'])
            effects.append(sum(r['topic_id']==row['topic_id'] for r in late)/len(late)-sum(r['topic_id']==row['topic_id'] for r in early)/len(early))
        assert float(row['late_minus_early_pp'])==pytest.approx(np.mean(effects)*100)
        assert 1/2001 <= float(row['p_exploratory']) <= float(row['q_bh']) <= 1

def test_screened_subtopic_coverage_and_timeline(data):
    decisions=read('migrant_scope_decisions.csv'); selected=read('migrant_screened_assignments.csv')
    assert len(decisions)==332 and len(selected)==118
    assert len({r['id'] for r in selected})==118
    assert all(r['human_review_status']=='pending' and not r['human_frame'] for r in decisions)
    assert len({r['screened_subtopic'] for r in selected}-{'-1'})==6
    for r in read('migrant_screened_timeline.csv'):
        group=[x for x in selected if x['year']==r['year'] and (r['scope']=='all_screened' or x['assistant_scope']==r['scope'])]
        assert int(r['denominator'])==len(group)
        assert int(r['count'])==sum(x['screened_subtopic']==r['subtopic_id'] for x in group)
        if not group: assert r['share_pct']==''

def test_js_distance_and_hashes(data):
    from scipy.spatial.distance import jensenshannon
    topics=sorted({r['topic_id'] for r in data}); counts=Counter((r['year'],r['topic_id']) for r in data)
    for r in read('adjacent_year_shifts.csv'):
        p=[counts[r['from_year'],t] for t in topics]; q=[counts[r['to_year'],t] for t in topics]
        assert float(r['js_distance'])==pytest.approx(jensenshannon(p,q,base=2))
    m=json.loads((OUT/'metrics.json').read_text())
    for name,expected in m['files_sha256'].items(): assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==expected

def test_report_links_and_exported_figures(data):
    for name in ['README_TH.md','story_1_model_outline_th.md','story_2_model_outline_th.md']:
        for target in re.findall(r'\]\(([^)]+)\)',(OUT/name).read_text()):
            if not target.startswith(('https://','http://','#')): assert (OUT/target).exists(),target
    for name in ['overview_timelines.png','migrant_subtopic_timeline.png']:
        assert (OUT/name).read_bytes().startswith(b'\x89PNG')

def test_leakage_exclusion_is_reported_not_hidden(data):
    diagnostic=read('residual_editorial_review.csv')
    assert len(diagnostic)==82
    m=json.loads((OUT/'leakage_sensitivity_metrics.json').read_text())
    assert m['remaining_records']+m['excluded_records']==len(data)
    assert m['refit_clusters']==56
    assert 0<=m['adjusted_rand_index_including_noise']<=1
    signals={int(r['original_topic']):r for r in read('leakage_exclusion_sensitivity.csv')}
    for t in [1,2,6,11]: assert float(signals[t]['late_minus_early_pp'])>0
    for t in [4,7]: assert float(signals[t]['late_minus_early_pp'])<0
