#!/usr/bin/env python3
"""Audited snapshot -> E5/BERTopic discovery, temporal representations and review queues.

No database writes. Never interprets machine topics as human-validated narratives.
"""
import os
os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/thverify-mpl')
import csv
import hashlib
import importlib.metadata
import json
import re
import sys
from collections import Counter
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
OUT=ROOT/'runs/20260908_bertopic_v001'
INPUT=ROOT/'data/reports/journalist_handoff_2026-09-08'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,rows):
    if not rows: return
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
def bh(p):
    p=np.asarray(p); order=np.argsort(p); out=np.empty(len(p)); last=1.
    for j in range(len(p)-1,-1,-1):
        last=min(last,p[order[j]]*len(p)/(j+1)); out[order[j]]=last
    return out
def tokens(text):
    from pythainlp.tokenize import word_tokenize
    from pythainlp.corpus.common import thai_stopwords
    stop=thai_stopwords() | {'ข่าว','ปลอม','จริง','แชร์','บิดเบือน'}
    return [t.lower() for t in word_tokenize(text,engine='newmm') if len(t.strip())>1 and t not in stop and re.search('[ก-๙a-zA-Z]',t)]

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    records=read(INPUT/'02_false_misleading_altered_records.csv')
    unique=list(dict.fromkeys(r['claim_text'] for r in records))
    text_index={t:i for i,t in enumerate(unique)}
    record_index=np.array([text_index[r['claim_text']] for r in records])
    config={'input_sha256':sha(INPUT/'02_false_misleading_altered_records.csv'),
        'snapshot_cutoff':'2026-09-02','analysis_asof':'2026-09-08','not_live_snapshot':True,
        'model':'intfloat/multilingual-e5-small','prefix':'passage: ','normalize':True,
        'records':len(records),'fit_unique_exact_texts':len(unique),
        'umap':{'n_neighbors':15,'n_components':10,'min_dist':0.,'metric':'cosine','random_state':42},
        'hdbscan':{'min_cluster_size':30,'min_samples':5,'metric':'euclidean','cluster_selection_method':'eom'},
        'sweep':[15,30,50,80],'selection':'30 prespecified; other sizes sensitivity, not significance optimization',
        'time':'calendar year; 2015 and 2026 partial; denominator includes outliers',
        'topic_representation':'Thai newmm word tokens; c-TF-IDF; no global/evolution smoothing',
        'bertopic_language':'multilingual (preserve Thai in preprocessing)',
        'embedding_reuse_config_sha256':sha(ROOT/'data/index_20260903/config.json'),
        'embedding_reuse_vectors_sha256':sha(ROOT/'data/index_20260903/embeddings.npy'),
        'labels':'machine keywords only; human labels blank pending review',
        'packages':{p:importlib.metadata.version(p) for p in ['bertopic','sentence-transformers','umap-learn','hdbscan','numpy','pythainlp','scikit-learn']}}
    old=OUT/'config.json'
    if old.exists() and json.loads(old.read_text())['input_sha256']!=config['input_sha256']:
        raise RuntimeError('Input changed: choose a new versioned output directory')
    old.write_text(json.dumps(config,ensure_ascii=False,indent=2))
    cache=OUT/'unique_embeddings.npy'
    if not cache.exists():
        ix=ROOT/'data/index_20260903'
        meta=[json.loads(line) for line in (ix/'meta.jsonl').open()]
        vectors=np.load(ix/'embeddings.npy')
        existing={r['claim_text']:vectors[i] for i,r in enumerate(meta)}
        missing=[t for t in unique if t not in existing]
        print(f'Reuse {len(unique)-len(missing)} exact-text vectors; encode {len(missing)} missing',flush=True)
        if missing:
            corpus=OUT/'missing_corpus.jsonl'
            with corpus.open('w') as f:
                for i,t in enumerate(missing):
                    f.write(json.dumps(dict(id=f'missing-{i}',claim_text=t,source='derived',url='',label='',published_at='',explanation=''),ensure_ascii=False)+'\n')
            from th_verify.search import build_index
            build_index(corpus,OUT/'missing_index',batch_size=64)
            new=np.load(OUT/'missing_index/embeddings.npy')
            existing.update(dict(zip(missing,new)))
        np.save(cache,np.stack([existing[t] for t in unique]))
    X=np.load(cache)
    assert X.shape==(len(unique),384) and np.isfinite(X).all()
    assert np.allclose(np.linalg.norm(X,axis=1),1,atol=1e-4)
    from umap import UMAP
    from hdbscan import HDBSCAN
    from sklearn.metrics import adjusted_rand_score
    zpath=OUT/'umap10.npy'
    if not zpath.exists():
        print('UMAP 10-dimensional fit',flush=True)
        np.save(zpath,UMAP(**config['umap']).fit_transform(X))
    Z=np.load(zpath)
    sweep=[]; sweep_labels={}
    for size in config['sweep']:
        labels=HDBSCAN(**dict(config['hdbscan'],min_cluster_size=size)).fit_predict(Z)
        sweep_labels[size]=labels
        sweep.append({'min_cluster_size':size,'clusters':len(set(labels)-{-1}),
                      'noise_unique_pct':float(np.mean(labels==-1)*100)})
    for s in sweep: s['ARI_vs_size30_including_noise']=float(adjusted_rand_score(sweep_labels[30],sweep_labels[s['min_cluster_size']]))
    write('sensitivity.csv',sweep)
    print('Sweep',sweep,flush=True)
    from bertopic import BERTopic
    from bertopic.dimensionality import BaseDimensionalityReduction
    from sklearn.feature_extraction.text import CountVectorizer
    model=BERTopic(language='multilingual',embedding_model=None,umap_model=BaseDimensionalityReduction(),
        hdbscan_model=HDBSCAN(**config['hdbscan']),
        vectorizer_model=CountVectorizer(tokenizer=tokens,token_pattern=None,lowercase=False,min_df=2,ngram_range=(1,2)),
        calculate_probabilities=False,verbose=True)
    labels,_=model.fit_transform(unique,embeddings=Z)
    labels=np.array(labels); all_labels=labels[record_index]
    topics=sorted(set(labels)); years=sorted({int(r['year']) for r in records})
    assignments=[dict(r,topic_id=int(t)) for r,t in zip(records,all_labels)]
    write('assignments.csv',assignments)
    summary=[]; exemplars=[]
    for t in topics:
        idx=np.flatnonzero(labels==t); ridx=np.flatnonzero(all_labels==t)
        centre=X[idx].mean(0); centre/=np.linalg.norm(centre)
        nearest=idx[np.argsort(-(X[idx]@centre))[:6]]
        actual=[next(r for r in records if r['claim_text']==unique[i]) for i in nearest]
        counts=Counter(int(records[i]['year']) for i in ridx)
        peak=max(years,key=lambda y:counts[y]/sum(int(r['year'])==y for r in records))
        words=' | '.join(w for w,v in (model.get_topic(int(t)) or [])[:8])
        summary.append({'topic_id':int(t),'machine_keywords':words,'human_label':'','review_status':'pending',
            'records':len(ridx),'unique_texts':len(idx),'share_pct':len(ridx)/len(records)*100,
            'first_year':min(counts),'last_year':max(counts),'peak_share_year':peak,
            'representative_id':actual[0]['id'],'representative_claim':actual[0]['claim_text'],
            'representative_url':actual[0]['url'],'representative_method':'nearest cosine centroid, original E5; not geometric projection'})
        for rank,r in enumerate(actual,1): exemplars.append(dict(topic_id=int(t),rank=rank,**r))
    write('topics.csv',summary); write('topic_exemplars.csv',exemplars)
    timeline=[]
    for source in ['all',*sorted({r['source'] for r in records})]:
        for year in years:
            group=[r for r in assignments if int(r['year'])==year and (source=='all' or r['source']==source)]
            counts=Counter(r['topic_id'] for r in group)
            for t in topics:
                timeline.append({'source':source,'year':year,'topic_id':t,'count':counts[t],
                    'denominator':len(group),'share_pct':100*counts[t]/len(group) if group else '',
                    'partial_year':year in [2015,2026]})
    write('topic_timeline.csv',timeline)
    print('Temporal c-TF-IDF representations',flush=True)
    temporal=model.topics_over_time([r['claim_text'] for r in records],[int(r['year']) for r in records],
        topics=all_labels.tolist(),global_tuning=False,evolution_tuning=False)
    temporal.to_csv(OUT/'topic_words_over_time.csv',index=False,encoding='utf-8-sig')
    from scipy.spatial.distance import jensenshannon
    shifts=[]
    for a,b in zip(years,years[1:]):
        p=np.array([next(r['count'] for r in timeline if r['source']=='all' and r['year']==a and r['topic_id']==t) for t in topics]); p=p/p.sum()
        q=np.array([next(r['count'] for r in timeline if r['source']=='all' and r['year']==b and r['topic_id']==t) for t in topics]); q=q/q.sum()
        gain=int(np.argmax(q-p)); loss=int(np.argmin(q-p))
        shifts.append({'from_year':a,'to_year':b,'js_distance':float(jensenshannon(p,q,base=2)),
            'largest_gain_topic':topics[gain],'gain_pp':float((q-p)[gain]*100),
            'largest_loss_topic':topics[loss],'loss_pp':float((q-p)[loss]*100),
            'status':'descriptive adjacent-year distance; not confirmed change point'})
    write('adjacent_year_shifts.csv',sorted(shifts,key=lambda r:-r['js_distance']))
    # Equal-source standardized difference; preserve actual early/late n in each source.
    blocks=[]; block_info=[]
    for source in sorted({r['source'] for r in records}):
        early=[r['topic_id'] for r in assignments if r['source']==source and int(r['year']) in [2020,2021]]
        late=[r['topic_id'] for r in assignments if r['source']==source and int(r['year']) in [2024,2025]]
        if min(len(early),len(late))<20: continue
        blocks.append((np.array(early+late)+1,len(early),len(late)))
        block_info.append({'source':source,'early_n':len(early),'late_n':len(late)})
    width=max(topics)+2
    def delta(blocks):
        return np.mean([np.bincount(x[n:],minlength=width)/m-np.bincount(x[:n],minlength=width)/n for x,n,m in blocks],axis=0)
    observed=delta(blocks); exceed=np.zeros(width); rng=np.random.default_rng(42)
    for _ in range(2000):
        simulated=delta([(rng.permutation(x),n,m) for x,n,m in blocks])
        exceed+=np.abs(simulated)>=np.abs(observed)-1e-12
    p=(exceed+1)/2001; q=bh(p)
    write('source_balanced_tests.csv',[{'topic_id':t,'late_minus_early_pp':float(observed[t+1]*100),
        'p_exploratory':float(p[t+1]),'q_bh':float(q[t+1]),'permutations':2000,
        'caveat':'fixed fitted topics; record exchangeability assumes independence; duplicate/temporal dependence unresolved'} for t in topics])
    # Semantic expansion from all explicit candidate texts; no fixed similarity cutoff claimed as truth.
    narrow=read(INPUT/'10_expanded_migrant_review.csv'); seed_ids={r['id'] for r in narrow}
    seed_idx=sorted({text_index[r['claim_text']] for r in narrow})
    similarities=X@X[seed_idx].T
    scores=similarities.max(axis=1); near_seed=similarities.argmax(axis=1)
    extra_idx=np.argsort(-scores)
    extra_idx=[i for i in extra_idx if i not in set(seed_idx)][:200]
    candidate_idx=set(seed_idx)|set(extra_idx)
    migrant=[]
    for r,t,i in zip(records,all_labels,record_index):
        if i not in candidate_idx: continue
        seed_text=unique[seed_idx[near_seed[i]]]
        seed=next(s for s in narrow if s['claim_text']==seed_text)
        migrant.append(dict(r,topic_id=int(t),retrieval_route='keyword_seed' if r['id'] in seed_ids else 'semantic_neighbor',
            similarity=float(scores[i]),nearest_seed_id=seed['id'],reviewed_scope='',reviewed_frame='',review_status='pending'))
    write('migrant_semantic_review.csv',migrant)
    # A separate discovered subtopic model on the retrieval pool, NOT a frame classifier.
    midx=sorted(candidate_idx); MX=X[midx]; mtexts=[unique[i] for i in midx]
    mmodel=BERTopic(language='multilingual',embedding_model=None,
        umap_model=UMAP(n_neighbors=10,n_components=5,min_dist=0.,metric='cosine',random_state=42),
        hdbscan_model=HDBSCAN(min_cluster_size=8,min_samples=3,metric='euclidean'),
        vectorizer_model=CountVectorizer(tokenizer=tokens,token_pattern=None,lowercase=False,min_df=1),verbose=True)
    ml,_=mmodel.fit_transform(mtexts,embeddings=MX)
    mlookup=dict(zip(midx,map(int,ml)))
    mrows=[dict(r,subtopic_id=mlookup[text_index[r['claim_text']]]) for r in migrant]
    write('migrant_subtopic_assignments.csv',mrows)
    ms=[]; mt=[]
    for t in sorted(set(ml)):
        group=[r for r in mrows if r['subtopic_id']==t]
        words=' | '.join(w for w,v in (mmodel.get_topic(t) or [])[:8])
        ids=np.array([i for i,label in zip(midx,ml) if label==t]); centre=X[ids].mean(0); centre/=np.linalg.norm(centre)
        reps=ids[np.argsort(-(X[ids]@centre))[:6]]
        example_ids=[next(r['id'] for r in group if r['claim_text']==unique[i]) for i in reps]
        ms.append({'subtopic_id':int(t),'machine_keywords':words,'candidate_records':len(group),
            'exemplar_ids':';'.join(example_ids),'human_narrative_label':'','review_status':'pending_scope_and_frame_review'})
        for year in years:
            n=sum(int(r['year'])==year for r in mrows); count=sum(int(r['year'])==year for r in group)
            mt.append({'year':year,'subtopic_id':int(t),'candidate_count':count,'candidate_denominator':n,
                'candidate_share_pct':100*count/n if n else '',
                'status':'retrieval_pool_only_not_validated_narrative_share'})
    write('migrant_subtopics.csv',ms); write('migrant_subtopic_timeline.csv',mt)
    mmodel.topics_over_time([r['claim_text'] for r in mrows],[int(r['year']) for r in mrows],
        topics=[r['subtopic_id'] for r in mrows],global_tuning=False,evolution_tuning=False).to_csv(
        OUT/'migrant_words_over_time.csv',index=False,encoding='utf-8-sig')
    recon=Counter((r['topic_id'],flag) for r in assignments for flag in r['topic_flags'].split(';'))
    write('keyword_reconciliation.csv',[{'topic_id':t,'keyword_flag':f,'records':n,'multi_label':True} for (t,f),n in sorted(recon.items())])
    recurring=[]
    for family in sorted({r['text_family'] for r in records}):
        group=[r for r in assignments if r['text_family']==family]
        if len({r['year'] for r in group})<2: continue
        recurring.append({'text_family':family,'records':len(group),'years':';'.join(sorted({r['year'] for r in group})),
            'claim_ids':';'.join(r['id'] for r in group),'example_claim':group[0]['claim_text'],
            'unit':'normalized text recurrence, not independently verified persuasion template'})
    write('recurring_text_families.csv',sorted(recurring,key=lambda r:-r['records']))
    metrics={'noise_records':int(sum(all_labels==-1)),'noise_share_pct':float(np.mean(all_labels==-1)*100),
        'discovered_topics':len(topics)-(-1 in topics),'source_test_blocks':block_info,
        'migrant_review_records':len(migrant),'migrant_semantic_extra_unique':len(extra_idx),
        'migrant_subtopics':len(set(ml)-{-1}),
        'scope_note':'retrieval expansion only; not validated migrant corpus or narrative prevalence',
        'embedding_sha256':sha(cache),'script_sha256':sha(Path(__file__)),
        'files_sha256':{p.name:sha(p) for p in OUT.glob('*.csv')}}
    (OUT/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
    print(json.dumps(metrics,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__': main()
