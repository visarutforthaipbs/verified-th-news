"""Local data/provenance QA, not certification of every publisher verdict."""
import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/reports/journalist_handoff_2026-09-08'


def rows(name):
    with (OUT/name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


@pytest.fixture(scope='module')
def bundle():
    if not (OUT/'manifest.json').exists():
        pytest.skip('Requires the journalist handoff snapshot')
    return (json.loads((OUT/'manifest.json').read_text()),
            rows('01_checked_records.csv'), rows('02_false_misleading_altered_records.csv'))


def test_partition_and_verdict_provenance(bundle):
    m, accepted, main = bundle
    excluded = rows('03_exclusions.csv')
    assert len(accepted) == m['accepted_comparison_records'] == 19326
    assert len(main) == m['main_records'] == 14429
    assert len(accepted)+len(excluded) == m['raw_records'] == 29001
    a_ids, e_ids = ({r['id'] for r in group} for group in (accepted,excluded))
    assert len(a_ids) == len(accepted) and len(e_ids) == len(excluded)
    assert not a_ids & e_ids
    assert {r['id'] for r in main} == {r['id'] for r in accepted if r['verdict']!='true'}
    assert Counter(r['verdict'] for r in main) == m['main_verdicts']
    assert {r['verdict_origin'] for r in main} <= {'human','source'}
    assert Counter(r['source'] for r in main) == m['main_sources']


def test_source_rows_and_curated_text_preserved(bundle):
    _,accepted,_ = bundle
    with sqlite3.connect(f'file:{ROOT / "data/th_verify.db"}?mode=ro',uri=True) as db:
        db.row_factory = sqlite3.Row
        original = {str(r['id']):dict(r) for r in db.execute('SELECT * FROM fact_checks')}
    for r in accepted:
        source = original[r['id']]
        assert r['url'] == source['source_url']
        assert r['title'] == source['title']
        assert r['verdict_origin'] == source['verdict_origin']
        if r['claim_text_basis'] != 'cleaned_title':
            assert r['claim_text'] == source['claim'].strip()


def test_annual_and_keyword_aggregates(bundle):
    m,accepted,main = bundle
    for r in rows('04_year_counts.csv'):
        group = [x for x in accepted if x['year']==r['year']]
        assert len(group)==int(r['checked_records'])
        assert sum(x['verdict']!='true' for x in group)==int(r['main_records'])
    compiled = {key:re.compile(pattern,re.I) for key,pattern in m['topic_rules'].items()}
    for r in main:
        expected = {key for key,rx in compiled.items() if rx.search(r['claim_text'])} or {'other'}
        assert set(r['topic_flags'].split(';'))==expected
    for r in rows('06_topic_year_by_publisher.csv'):
        group = [x for x in main if x['year']==r['year'] and (r['source']=='all' or x['source']==r['source'])]
        count = sum(r['topic'] in x['topic_flags'].split(';') for x in group)
        assert (int(r['matches']),int(r['denominator'])) == (count,len(group))
        assert r['share_pct'] == (str(round(count/len(group)*100,3)) if group else '')


def test_sensitivity_denominators(bundle):
    _,_,main = bundle
    for r in rows('11_period_sensitivity.csv'):
        first,last = map(int,r['period'].split('-'))
        group = [x for x in main if first<=int(x['year'])<=last and (r['source']=='all' or x['source']==r['source'])]
        if r['method']=='same_source_year_text_dedup':
            group = list({(x['source'],x['year'],x['text_family']):x for x in group}.values())
        elif r['method']=='false_only':
            group = [x for x in group if x['verdict']=='false']
        count = sum(r['topic'] in x['topic_flags'].split(';') for x in group)
        assert (int(r['matches']),int(r['denominator'])) == (count,len(group))
        assert r['share_pct'] == (str(round(count/len(group)*100,3)) if group else '')


def test_migrant_queues_are_provisional_and_nested(bundle):
    m,_,main = bundle
    narrow = rows('07_migrant_candidates_review.csv')
    expanded = rows('10_expanded_migrant_review.csv')
    assert len(narrow)==m['migrant_candidates']==81
    assert len(expanded)==m['expanded_migrant_candidates']==128
    assert {r['id'] for r in narrow} < {r['id'] for r in expanded} <= {r['id'] for r in main}
    assert {'15731','15735'} <= {r['id'] for r in expanded}
    for r in narrow+expanded:
        assert r['review_status']=='pending_editorial_review'
        assert not r['reviewed_scope'] and not r['reviewed_frames']
    border = rows('08_border_only_excluded_from_migrant.csv')
    assert len(border)==153
    assert all(r['border_match']=='True' and r['migrant_match']=='False' for r in border)


def test_selected_cases_and_local_document_links(bundle):
    _,_,main = bundle
    lookup = {r['id']:r for r in main}
    cases = rows('12_selected_cases.csv')
    assert len(cases)==17
    for r in cases:
        assert r['url']==lookup[r['id']]['url']
        assert r['final_editorial_verification']=='pending'
    for filename in ('README.md','story_1_outline_th.md','story_2_outline_th.md','methodology_and_review_th.md'):
        text = (OUT/filename).read_text()
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if not target.startswith(('https://','http://','#')):
                assert (OUT/target.split('#')[0]).exists(), (filename,target)
    story1 = (OUT/'story_1_outline_th.md').read_text()
    for r in rows('04_year_counts.csv'):
        assert f"| {r['year_be']}{'*' if r['partial_year']=='True' else ''} | {int(r['main_records']):,} |" in story1


def test_manifest_hashes(bundle):
    m,_,_ = bundle
    for name,expected in m['csv_sha256'].items():
        assert hashlib.sha256((OUT/name).read_bytes()).hexdigest()==expected
    assert hashlib.sha256((ROOT/'scripts/build_journalist_handoff.py').read_bytes()).hexdigest()==m['script_sha256']
