#!/usr/bin/env python3
"""Story 2 interim tables on the v2 queue, after the owner's scope decisions of 2026-10-04.

Decisions applied: (1) foreign residents of any origin are in scope; (2) tourists and
short-term visitors in Thailand are out of scope. Everything here still rests on the
assistant's reading of title + claim; it is replaced once two human coders finish.

Reads runs/20261004_story2_queue_v002 and the canonical run (read-only).
Writes runs/20261004_story2_interim_v002/.
"""
import collections, csv, hashlib, json, re, sys, warnings
from pathlib import Path
import numpy as np

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
RUN = ROOT / 'runs/20260908_bertopic_v001'
QUE = ROOT / 'runs/20261004_story2_queue_v002'
OUT = ROOT / 'runs/20261004_story2_interim_v002'
C = collections.Counter
csv.field_size_limit(10 ** 9)
IN = ('resident_refugee_status', 'crossborder_people_services')
# Decision 2: these rows were "unclear" only because the subject is a tourist / short-term visitor -> out of scope.
VISITOR_OUT = set('16541 16531 16517 16444 16351 14485 13656 27475 1595 1126 27414'.split())
NOT_LAO = 'ผักชีลาว|ศิลาว|เวลาว'
GROUPS = (('israel_jewish', 'อิสราเอล|ยิว'), ('china', 'จีน'), ('myanmar', 'พม่า|เมียนมา|โรฮิง|โรฮีน'), ('cambodia', 'กัมพูชา|เขมร'), ('laos_vietnam', 'ลาว|เวียดนาม'))


def rd(p):
    with open(p, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def wr(name, rows, cols=None):
    cols = cols or list(rows[0])
    with open(OUT / name, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, restval=0, extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def group_of(r):
    t = re.sub(NOT_LAO, '', (r['title'] or '') + ' ' + (r['claim_text'] or ''))
    for name, pat in GROUPS:
        if re.search(pat, t):
            return name
    return 'generic_or_other'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    A = rd(RUN / 'assignments.csv'); den = C(r['year'] for r in A)
    Q = rd(QUE / 'review_queue_v2.csv')
    for r in Q:
        r['scope_interim'] = 'out_of_scope' if r['id'] in VISITOR_OUT else r['assistant_scope']
        r['group_marker'] = group_of(r)
    ins = [r for r in Q if r['scope_interim'] in IN]
    years = [y for y in sorted(den) if y >= '2020']
    # --- subtopics: same recipe as round 1 (UMAP 5d, HDBSCAN leaf 8/3)
    unique = list(dict.fromkeys(r['claim_text'] for r in A)); ix = {t: i for i, t in enumerate(unique)}
    texts = list(dict.fromkeys(r['claim_text'] for r in ins)); X = np.load(RUN / 'unique_embeddings.npy')[[ix[t] for t in texts]]
    from umap import UMAP
    from hdbscan import HDBSCAN
    from bertopic import BERTopic
    from bertopic.dimensionality import BaseDimensionalityReduction
    from sklearn.feature_extraction.text import CountVectorizer
    from discovered_timeline import tokens
    Z = UMAP(n_neighbors=10, n_components=5, min_dist=0., metric='cosine', random_state=42).fit_transform(X)
    sweep = []
    for method in ('eom', 'leaf'):
        for size in (5, 8, 12, 20):
            lab = HDBSCAN(min_cluster_size=size, min_samples=3, cluster_selection_method=method).fit_predict(Z)
            sweep.append({'method': method, 'min_cluster_size': size, 'topics': len(set(lab) - {-1}), 'noise_pct': round(float(np.mean(lab == -1) * 100), 1)})
    wr('subtopic_sensitivity.csv', sweep)
    model = BERTopic(language='multilingual', embedding_model=None, umap_model=BaseDimensionalityReduction(),
                     hdbscan_model=HDBSCAN(min_cluster_size=8, min_samples=3, cluster_selection_method='leaf'),
                     vectorizer_model=CountVectorizer(tokenizer=tokens, token_pattern=None, lowercase=False, min_df=1), verbose=False)
    labels, _ = model.fit_transform(texts, embeddings=Z); look = dict(zip(texts, map(int, labels)))
    for r in ins:
        r['subtopic_v2'] = look[r['claim_text']]
    labels = np.array(labels); subs = []; ex = []
    for t in sorted(set(labels)):
        g = [r for r in ins if r['subtopic_v2'] == t]
        idx = np.flatnonzero(labels == t); c = X[idx].mean(0); c /= np.linalg.norm(c)
        reps = idx[np.argsort(-(X[idx] @ c))[:6]]
        er = [next(r for r in g if r['claim_text'] == texts[i]) for i in reps]
        row = {'subtopic_id': int(t), 'machine_keywords': ' | '.join(w for w, v in (model.get_topic(int(t)) or [])[:8]), 'records': len(g),
               'groups': '; '.join(f'{k} {v}' for k, v in C(r['group_marker'] for r in g).most_common()),
               'sources': '; '.join(f'{k} {v}' for k, v in C(r['source'] for r in g).most_common()),
               'status': 'assistant-screened scope; machine keywords; not a human-validated frame'}
        row.update({f'y{y}': sum(r['year'] == y for r in g) for y in years})
        subs.append(row)
        for rank, r in enumerate(er, 1):
            ex.append({'subtopic_id': int(t), 'rank': rank, 'id': r['id'], 'source': r['source'], 'date': r['date'], 'verdict': r['verdict'],
                       'claim_text': r['claim_text'], 'claim_text_basis': r['claim_text_basis'], 'url': r['url'], 'queue_round': r['queue_round']})
    wr('subtopics_v2.csv', subs); wr('subtopic_exemplars_v2.csv', ex)
    # --- record-level file
    keep = ['id', 'source', 'date', 'year', 'verdict', 'verdict_origin', 'claim_text', 'claim_text_basis', 'title', 'url', 'queue_round', 'retrieval_route',
            'assistant_scope', 'scope_interim', 'group_marker', 'subtopic_v2']
    wr('in_scope_records_interim.csv', sorted(ins, key=lambda r: r['date']), keep)
    wr('scope_interim_all_rows.csv', Q, ['id', 'source', 'date', 'year', 'claim_text', 'queue_round', 'assistant_scope', 'scope_interim', 'group_marker'])
    # --- year tables
    kh = lambda r: r['group_marker'] == 'cambodia'
    yr = []
    for y in years:
        g = [r for r in ins if r['year'] == y]
        row = {'year': y, 'year_be': int(y) + 543, 'partial_year': y == '2026', 'all_records': den[y], 'in_scope': len(g), 'share_pct': round(len(g) / den[y] * 100, 2),
               'in_scope_excl_cambodia': sum(not kh(r) for r in g), 'share_excl_cambodia_pct': round(sum(not kh(r) for r in g) / den[y] * 100, 2),
               'resident': sum(r['scope_interim'] == IN[0] for r in g), 'crossborder': sum(r['scope_interim'] == IN[1] for r in g)}
        row.update({f'group_{k}': v for k, v in C(r['group_marker'] for r in g).items()})
        row.update({f'src_{k}': v for k, v in C(r['source'] for r in g).items()})
        yr.append(row)
    cols = ['year', 'year_be', 'partial_year', 'all_records', 'in_scope', 'share_pct', 'in_scope_excl_cambodia', 'share_excl_cambodia_pct', 'resident', 'crossborder'] + \
           [f'group_{k}' for k in ('myanmar', 'cambodia', 'laos_vietnam', 'china', 'israel_jewish', 'generic_or_other')] + [f'src_{k}' for k in ('afnc', 'cofact', 'thaipbs', 'afp')]
    wr('in_scope_by_year.csv', yr, cols)
    late = [r for r in ins if r['year'] in ('2025', '2026')]
    metrics = {'queue_rows': len(Q), 'scope_interim': dict(C(r['scope_interim'] for r in Q)), 'in_scope': len(ins),
               'in_scope_resident': sum(r['scope_interim'] == IN[0] for r in ins), 'in_scope_crossborder': sum(r['scope_interim'] == IN[1] for r in ins),
               'in_scope_from_round2': sum(r['queue_round'] == '2' for r in ins), 'in_scope_unique_texts': len(texts),
               'by_source': dict(C(r['source'] for r in ins)), 'by_group_marker': dict(C(r['group_marker'] for r in ins)),
               'by_verdict': dict(C(r['verdict'] for r in ins)), 'claim_text_basis_llm': sum(r['claim_text_basis'] == 'llm' for r in ins),
               'late_2025_2026': len(late), 'late_by_group': dict(C(r['group_marker'] for r in late)),
               'subtopics': len(set(labels) - {-1}), 'subtopic_noise_records': sum(r['subtopic_v2'] == -1 for r in ins),
               'human_coded_rows': 0, 'decisions': {'foreign_residents_any_origin': 'in scope', 'tourists_short_term_visitors': 'out of scope', 'decided_by': 'owner', 'date': '2026-10-04'},
               'status': 'assistant-screened; replaced after human coding'}
    manifest = {'run': OUT.name, 'script': 'scripts/story2_interim_analysis.py', 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'inputs_sha256': {'review_queue_v2.csv': hashlib.sha256((QUE / 'review_queue_v2.csv').read_bytes()).hexdigest(),
                                  'assignments.csv': hashlib.sha256((RUN / 'assignments.csv').read_bytes()).hexdigest()},
                'subtopic_params': {'umap': {'n_neighbors': 10, 'n_components': 5, 'min_dist': 0, 'metric': 'cosine', 'random_state': 42},
                                    'hdbscan': {'min_cluster_size': 8, 'min_samples': 3, 'cluster_selection_method': 'leaf'}},
                'visitor_rows_moved_out': sorted(VISITOR_OUT), 'group_marker': 'string matching on title+claim; not coding', 'metrics': metrics}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(metrics, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
