"""Assistant title/claim scope screening, then unsupervised migrant subtopics.

This is NOT human frame validation. Decisions remain visible for editorial review.
"""
import sys,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from discovered_timeline import OUT,read,write,tokens,sha

# Explicit record-level decisions after reading the retrieved claim/title list.
RESIDENTS=set('''16390 15735 15731 15549 15406 14882 14480 14318
13929 13918 13904 13201 13177 12036 11134 11087 10046 9740
7946 7940 7273 27645 6542 6381 6278 6249 6120 6100 5929
5600 5541 5522 5515 5366 5235 5170 5062 27802 16862 17289 27076
4787 4776 4750 4720 4644 4327 3650 3625 3548 3233 3176 28124
3044 3034 26964 27940 17138 2232 1927 28091 26851 1639 1623
1600 1473 27700 27675 27959 27584 27544 1311 1233 1215 1174 1146
830 28026 655 561 527 451 396 27211 298 286 27187 252 28118 224
219 138 99 89 69 39 28176 28224 28891'''.split())
CROSSBORDER=set('''26985 27891 3045 2644 2582 26872 1601 28080 1543 1540
1319 1166 1162 1079 1003 737 26715 580 58'''.split())
UNCLEAR=set('''13339 11489 10114 3536 1531 1905 3102'''.split())

def main():
    allrows=read(OUT/'assignments.csv'); candidates=read(OUT/'migrant_semantic_review.csv')
    ids={r['id'] for r in candidates}
    assert RESIDENTS|CROSSBORDER|UNCLEAR <= ids
    decisions=[]
    for r in candidates:
        scope=('resident_refugee_status' if r['id'] in RESIDENTS else 'crossborder_people_services' if r['id'] in CROSSBORDER else 'unclear' if r['id'] in UNCLEAR else 'out_of_scope')
        decisions.append(dict(r,assistant_scope=scope,scope_basis='assistant read claim/title, not full-source verification',
            scope_evidence=r['title'],human_scope='',human_frame='',human_review_status='pending'))
    write('migrant_scope_decisions.csv',decisions)
    rows=[r for r in decisions if r['id'] in RESIDENTS|CROSSBORDER]
    unique=list(dict.fromkeys(r['claim_text'] for r in allrows)); ix={t:i for i,t in enumerate(unique)}
    texts=list(dict.fromkeys(r['claim_text'] for r in rows)); X=np.load(OUT/'unique_embeddings.npy')[[ix[t] for t in texts]]
    from bertopic import BERTopic
    from bertopic.dimensionality import BaseDimensionalityReduction
    from umap import UMAP
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer
    Z=UMAP(n_neighbors=10,n_components=5,min_dist=0.,metric='cosine',random_state=42).fit_transform(X)
    sweep=[]
    for method in ['eom','leaf']:
        for size in [5,8,12,20]:
            lab=HDBSCAN(min_cluster_size=size,min_samples=3,cluster_selection_method=method).fit_predict(Z)
            sweep.append({'method':method,'min_cluster_size':size,'topics':len(set(lab)-{-1}),'noise_pct':float(np.mean(lab==-1)*100)})
    write('migrant_screened_sensitivity.csv',sweep)
    model=BERTopic(language='multilingual',embedding_model=None,umap_model=BaseDimensionalityReduction(),
        hdbscan_model=HDBSCAN(min_cluster_size=8,min_samples=3,cluster_selection_method='leaf'),
        vectorizer_model=CountVectorizer(tokenizer=tokens,token_pattern=None,lowercase=False,min_df=1),verbose=True)
    labels,_=model.fit_transform(texts,embeddings=Z); lookup=dict(zip(texts,map(int,labels)))
    rows=[dict(r,screened_subtopic=lookup[r['claim_text']]) for r in rows]
    write('migrant_screened_assignments.csv',rows)
    summary=[]; examples=[]; timeline=[]
    for t in sorted(set(labels)):
        group=[r for r in rows if r['screened_subtopic']==t]
        idx=np.flatnonzero(np.array(labels)==t); centre=X[idx].mean(0); centre/=np.linalg.norm(centre)
        reps=idx[np.argsort(-(X[idx]@centre))[:6]]
        er=[next(r for r in group if r['claim_text']==texts[i]) for i in reps]
        for rank,r in enumerate(er,1): examples.append(dict(r,representative_rank=rank))
        summary.append({'subtopic_id':int(t),'machine_keywords':' | '.join(w for w,v in model.get_topic(t)[:8]),
            'records':len(group),'representative_ids':';'.join(r['id'] for r in er),
            'interpretation_status':'assistant-screened scope; no human-validated narrative label'})
        for year in range(2015,2027):
            for scope in ['all_screened','resident_refugee_status']:
                base=[r for r in rows if int(r['year'])==year and (scope=='all_screened' or r['assistant_scope']==scope)]
                n=len(base); count=sum(r['screened_subtopic']==t for r in base)
                timeline.append({'year':year,'scope':scope,'subtopic_id':int(t),'count':count,'denominator':n,
                    'share_pct':100*count/n if n else '',
                    'status':'exploratory assistant-screened subtopic, NOT human-validated frame prevalence'})
    write('migrant_screened_topics.csv',summary); write('migrant_screened_exemplars.csv',examples)
    write('migrant_screened_timeline.csv',timeline)
    model.topics_over_time([r['claim_text'] for r in rows],[int(r['year']) for r in rows],
        topics=[r['screened_subtopic'] for r in rows],global_tuning=False,evolution_tuning=False).to_csv(
        OUT/'migrant_screened_words_over_time.csv',index=False,encoding='utf-8-sig')
    metrics={'reviewed_candidates':len(candidates),'assistant_in_scope':len(rows),
        'resident_records':len(RESIDENTS),'crossborder_records':len(CROSSBORDER),'unclear':len(UNCLEAR),
        'unique_texts':len(texts),'subtopics':len(set(labels)-{-1}),
        'noise_records':sum(r['screened_subtopic']==-1 for r in rows),
        'screening':'assistant claim/title-only record-level decisions, human review pending',
        'selection':'leaf, min_cluster_size=8, min_samples=3; fine-grained exploratory themes; full sweep saved',
        'umap':{'n_neighbors':10,'n_components':5,'min_dist':0,'random_state':42,'metric':'cosine'},
        'script_sha256':sha(Path(__file__)),
        'csv_sha256':{p.name:sha(p) for p in OUT.glob('migrant_screened*.csv')}}
    (OUT/'migrant_screened_metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2))
    print(json.dumps(metrics,ensure_ascii=False,indent=2)); print(summary)

if __name__=='__main__': main()
