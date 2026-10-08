#!/usr/bin/env python3
"""End-to-end audit of the two-article analysis (data -> method -> drafts).

Reads the canonical run, the frozen corpus and the dev DB (read-only, immutable);
writes runs/20261004_audit_v001/audit_metrics.json. Changes nothing else.
Narrative findings are in runs/20261004_audit_v001/AUDIT.md.
"""
import collections, csv, hashlib, json, math, re, sqlite3, statistics, sys, warnings
from datetime import datetime
from pathlib import Path
import numpy as np

warnings.filterwarnings('ignore')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from th_verify.normalized import is_factcheck, normalize_verdict  # noqa: E402

RUN = ROOT / 'runs/20260908_bertopic_v001'
OUT = ROOT / 'runs/20261004_audit_v001'
DB = ROOT / 'data/th_verify.db'
C = collections.Counter
csv.field_size_limit(10 ** 9)
E, L = ('2020', '2021'), ('2024', '2025')
HEAD = {4: 'virus cures', 7: 'infection reports', 1: 'invest-dividend',
        2: 'driving licence', 11: 'victim refund', 6: 'Cambodia border'}


def rd(p):
    with open(p, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def jsd(p, q):
    m = (p + q) / 2
    kl = lambda a, b: float(np.sum(np.where(a > 0, a * np.log2(a / b), 0)))
    return math.sqrt(0.5 * kl(p, m) + 0.5 * kl(q, m))


def near_dup_groups(X, th):
    n = len(X); parent = np.arange(n)
    def f(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for s in range(0, n, 1500):
        ii, jj = np.nonzero(X[s:s + 1500] @ X.T >= th)
        for i, j in zip(ii + s, jj):
            if j > i:
                a, b = f(i), f(j)
                if a != b:
                    parent[b] = a
    return np.array([f(i) for i in range(n)])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    M = {}
    A = rd(RUN / 'assignments.csv'); ids = {r['id'] for r in A}
    con = sqlite3.connect(f'file:{DB}?immutable=1', uri=True); con.row_factory = sqlite3.Row
    db = {str(r['id']): r for r in con.execute('SELECT * FROM fact_checks')}
    asr = {str(x[0]): (x[1], x[2]) for x in con.execute(
        "SELECT fact_check_id, length(coalesce(transcript,'')), length(coalesce(quote,'')) FROM asr_evidence")}

    # 1 data layer ---------------------------------------------------------
    mine = {i for i, r in db.items()
            if is_factcheck(r['source'], r['title'], r['verdict'], r['explanation'] or '', r['verdict_origin'] or '')
            and (r['verdict_origin'] or '') in ('source', 'human')
            and normalize_verdict(r['source'], r['verdict']) in ('false', 'misleading', 'altered_media')}
    def basis(i):
        d = db[i]
        if len((d['explanation'] or '').strip()) > 40: return 'evidence'
        if i in asr and (asr[i][1] > 0 or asr[i][0] > 120): return 'evidence'
        return 'title_only'
    hum = [r for r in A if r['verdict_origin'] == 'human']
    to = [r for r in hum if basis(r['id']) == 'title_only']
    gaps = {}
    for who in ('best', 'visarut'):
        rows = sorted([d for d in db.values() if d['labeled_by'] == who and d['labeled_at']], key=lambda d: d['labeled_at'])
        for a, b in zip(rows, rows[1:]):
            g = (datetime.fromisoformat(b['labeled_at']) - datetime.fromisoformat(a['labeled_at'])).total_seconds()
            if g < 600: gaps[str(b['id'])] = g
    tg = [gaps[r['id']] for r in to if r['id'] in gaps]
    ss = [r for r in A if r['source'] == 'sure_share']
    M['data'] = {
        'corpus': len(A), 'rebuild_extra_only_short_text': len(mine - ids), 'corpus_not_in_rebuild': len(ids - mine),
        'human_labelled': len(hum), 'human_by_source': dict(C(r['source'] for r in hum)),
        'human_via_asr_quote_path': sum(1 for r in hum if r['id'] in asr and asr[r['id']][1] > 0),
        'title_only_human': len(to), 'title_only_question_form': sum(1 for r in to if 'จริงหรือ' in (r['title'] or '')),
        'title_only_median_seconds': statistics.median(tg), 'title_only_under_20s_pct': round(sum(x < 20 for x in tg) / len(tg) * 100, 1),
        'records_2015_2019': sum(r['year'] < '2020' for r in A),
        'sure_share_share_2015_2019_pct': round(sum(r['source'] == 'sure_share' for r in A if r['year'] < '2020') / sum(r['year'] < '2020' for r in A) * 100, 1),
        'afnc_share_by_year_pct': {y: round(sum(r['source'] == 'afnc' for r in A if r['year'] == y) / sum(r['year'] == y for r in A) * 100, 1) for y in sorted({r['year'] for r in A})},
        'sure_share_shorts_pct': {y: round(sum('#shorts' in (r['title'] or '').lower() or 'shorts' in (r['url'] or '') for r in ss if r['year'] == y) / max(sum(r['year'] == y for r in ss), 1) * 100) for y in ('2022', '2023', '2024', '2025')},
        'afnc_dated_before_opening': sum(1 for r in A if r['source'] == 'afnc' and r['date'] < '2019-11-01'),
        'claim_text_basis': dict(C(r['claim_text_basis'] for r in A)),
    }
    # same claim labelled with and without evidence (Sure&Share, whole DB)
    fam = lambda t: re.sub(r'ชัวร์ก่อนแชร์|shorts|:|\|', '', re.sub(r'จริงหรือ\s*\??|[?？!\s"“”\']', '', re.sub(r'#\S+', '', t or '')), flags=re.I).strip()
    groups = collections.defaultdict(list)
    for i, d in db.items():
        if d['source'] == 'sure_share' and d['verdict_origin'] == 'human':
            v = normalize_verdict('sure_share', d['verdict'])
            if v in ('false', 'true', 'misleading'): groups[fam(d['title'])].append((v, basis(i)))
    pairs = [(a[0], b[0]) for k, g in groups.items() if len(k) >= 8 for a in g if a[1] == 'title_only' for b in g if b[1] == 'evidence']
    nt = [(a, b) for a, b in pairs if a != 'true']; tt = [(a, b) for a, b in pairs if a == 'true']
    M['label_pairs'] = {'pairs': len(pairs), 'exact_agree': sum(a == b for a, b in pairs),
                        'title_only_not_true': len(nt), 'of_which_evidence_says_true': sum(b == 'true' for a, b in nt),
                        'title_only_true': len(tt), 'of_which_evidence_says_not_true': sum(b != 'true' for a, b in tt)}

    # 2 method layer -------------------------------------------------------
    unique = list(dict.fromkeys(r['claim_text'] for r in A)); tix = {t: i for i, t in enumerate(unique)}
    rec_ix = np.array([tix[r['claim_text']] for r in A]); topic = np.array([int(r['topic_id']) for r in A])
    ul = np.full(len(unique), -99); ul[rec_ix] = topic
    X = np.load(RUN / 'unique_embeddings.npy').astype(np.float32)
    from hdbscan import HDBSCAN
    from sklearn.metrics import adjusted_rand_score as ari
    from umap import UMAP
    Z2 = UMAP(n_neighbors=15, n_components=10, min_dist=0., metric='cosine', random_state=42).fit_transform(X)
    h2 = HDBSCAN(min_cluster_size=30, min_samples=5, metric='euclidean', cluster_selection_method='eom').fit_predict(Z2)
    topics = sorted(set(topic))
    dist = lambda rows: np.array([C(int(r['topic_id']) for r in rows)[t] / len(rows) for t in topics])
    yr = lambda y, s=None: [r for r in A if r['year'] == y and (s is None or r['source'] == s)]
    per_source = {}
    for t, nm in {**HEAD, 18: 'vaccine'}.items():
        per_source[nm] = {}
        for s in ('all', 'afnc', 'sure_share', 'afp'):
            e = [r for r in A if r['year'] in E and (s == 'all' or r['source'] == s)]
            l = [r for r in A if r['year'] in L and (s == 'all' or r['source'] == s)]
            per_source[nm][s] = [sum(int(r['topic_id']) == t for r in e), len(e), sum(int(r['topic_id']) == t for r in l), len(l)]
    seeds = {}
    for seed in (7, 21):
        lab = np.load(ROOT / f'runs/20260914_embedding_ab_v001/e5_passage_seed{seed}_labels.npy'); rl = lab[rec_ix]
        seeds[seed] = {'ari': round(float(ari(ul, lab)), 3)}
        for t, nm in HEAD.items():
            mine_t = set(np.flatnonzero(ul == t))
            best = max(set(lab) - {-1}, key=lambda c: len(mine_t & set(np.flatnonzero(lab == c))) / len(mine_t | set(np.flatnonzero(lab == c))))
            other = set(np.flatnonzero(lab == best))
            seeds[seed][nm] = {'jaccard': round(len(mine_t & other) / len(mine_t | other), 2),
                               'late_share_pct': round(sum(1 for r, x in zip(A, rl) if r['year'] in L and x == best) / 4836 * 100, 2)}
    dedup = {}
    for th in (0.95, 0.97):
        g = near_dup_groups(X, th); grec = g[rec_ix]; seen = set(); keep = []
        for r, gi in zip(A, grec):
            k = (r['source'], r['year'], gi)
            if k not in seen: seen.add(k); keep.append(r)
        dE = sum(r['year'] in E for r in keep); dL = sum(r['year'] in L for r in keep)
        dedup[str(th)] = {'kept': len(keep), 'late_share_pct': {nm: round(sum(1 for r in keep if r['year'] in L and int(r['topic_id']) == t) / dL * 100, 2) for t, nm in HEAD.items()},
                          'largest_group_in_licence_topic': int(C(g[np.flatnonzero(ul == 2)]).most_common(1)[0][1]), 'licence_unique_texts': int((ul == 2).sum())}
    sb = {r['topic_id']: float(r['late_minus_early_pp']) for r in rd(RUN / 'source_balanced_tests.csv')}
    afn = lambda t: (sum(int(r['topic_id']) == t for r in A if r['year'] in L and r['source'] == 'afnc') / sum(r['year'] in L and r['source'] == 'afnc' for r in A)
                     - sum(int(r['topic_id']) == t for r in A if r['year'] in E and r['source'] == 'afnc') / sum(r['year'] in E and r['source'] == 'afnc' for r in A)) * 100
    M['method'] = {
        'rerun_from_embeddings_ari': round(float(ari(ul, h2)), 4), 'rerun_clusters': len(set(h2) - {-1}),
        'jsd_2019_2020': {'all': round(jsd(dist(yr('2019')), dist(yr('2020'))), 3), 'sure_share_only': round(jsd(dist(yr('2019', 'sure_share')), dist(yr('2020', 'sure_share'))), 3)},
        'topic0_within_sure_share_pct': {y: round(sum(r['topic_id'] == '0' for r in yr(y, 'sure_share')) / len(yr(y, 'sure_share')) * 100, 1) for y in ('2019', '2020')},
        'headline_topics_by_source_[early_n,early_den,late_n,late_den]': per_source,
        'source_balanced_vs_afnc_change_div3': {HEAD[t]: [round(sb[str(t)], 2), round(afn(t) / 3, 2)] for t in (2, 11, 1)},
        'seed_stability': seeds, 'near_duplicate_collapse': dedup,
    }

    # 3 story 2 recall probe ----------------------------------------------
    q = {r['id'] for r in rd(RUN / 'migrant_scope_decisions.csv')}
    pat = 'ต่างด้าว|แรงงานข้ามชาติ|แรงงานต่างชาติ|ผู้ลี้ภัย|ผู้อพยพ|ผู้หนีภัย|โรฮิง|โรฮีน|ลักลอบ|แรงงานกัมพูชา|แรงงานลาว|เมียนมา|พม่า|ชาวกัมพูชา|คนกัมพูชา|ชาวเขมร|คนเขมร|ชาวลาว|คนลาว'
    noise = 'แผ่นดินไหว|รอยเลื่อน|รอยแยก|รัฐประหาร|ทหารพม่า|กองทัพ|ท่อ|ระเบิด|สึนามิ|พายุ|ไซโคลน|เขื่อน'
    txt = lambda r: (r['title'] or '') + ' ' + (r['claim_text'] or '')
    miss = [r for r in A if r['id'] not in q and re.search(pat, txt(r)) and not re.search(noise, txt(r))]
    M['story2'] = {'queue': len(q), 'never_screened_candidates': len(miss),
                   'clearly_relevant_ids_found_by_auditor': ['17106', '6389', '27145', '5180', '4571', '2802', '1117'],
                   'never_screened_list': [{'id': r['id'], 'date': r['date'], 'source': r['source'], 'claim': r['claim_text'][:140]} for r in sorted(miss, key=lambda r: r['date'])]}

    M['inputs_sha256'] = {'assignments.csv': sha(RUN / 'assignments.csv'), 'unique_embeddings.npy': sha(RUN / 'unique_embeddings.npy'),
                          'migrant_scope_decisions.csv': sha(RUN / 'migrant_scope_decisions.csv'), 'th_verify.db_bytes': DB.stat().st_size}
    (OUT / 'audit_metrics.json').write_text(json.dumps(M, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: M[k] for k in ('data', 'label_pairs')}, ensure_ascii=False, indent=1))
    print('method:', json.dumps({k: M['method'][k] for k in ('rerun_from_embeddings_ari', 'jsd_2019_2020', 'topic0_within_sure_share_pct', 'source_balanced_vs_afnc_change_div3', 'seed_stability', 'near_duplicate_collapse')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
