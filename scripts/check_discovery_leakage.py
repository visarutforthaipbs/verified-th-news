"""Refit sensitivity excluding residual editorial-warning matches; not a final clean corpus."""
import sys,json,re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from discovered_timeline import OUT,read,write,sha
import numpy as np
from umap import UMAP
from hdbscan import HDBSCAN
from sklearn.metrics import adjusted_rand_score

def main():
    rows=read(OUT/'assignments.csv'); texts=list(dict.fromkeys(r['claim_text'] for r in rows))
    rx=re.compile(r'ข่าวปลอม|อย่าแชร์|สร้างความเข้าใจผิด|สร้างความปั่นป่วน')
    idx=[i for i,t in enumerate(texts) if not rx.search(t)]
    X=np.load(OUT/'unique_embeddings.npy')[idx]
    Z=UMAP(n_neighbors=15,n_components=10,min_dist=0.,metric='cosine',random_state=42).fit_transform(X)
    labels=HDBSCAN(min_cluster_size=30,min_samples=5,metric='euclidean').fit_predict(Z)
    old={r['claim_text']:int(r['topic_id']) for r in rows}
    old_labels=np.array([old[texts[i]] for i in idx]); lookup=dict(zip([texts[i] for i in idx],map(int,labels)))
    kept=[dict(r,sensitivity_topic=lookup[r['claim_text']]) for r in rows if r['claim_text'] in lookup]
    comparison=[]
    for t in sorted(set(old_labels)-{-1}):
        original=old_labels==t
        candidates=[n for n in set(labels) if n!=-1]
        best=max(candidates,key=lambda n:np.sum(original & (labels==n))/np.sum(original | (labels==n)))
        jaccard=np.sum(original & (labels==best))/np.sum(original | (labels==best))
        item={'original_topic':int(t),'refit_topic':int(best),'jaccard_unique_texts':float(jaccard)}
        for name,years in [('early',{'2020','2021'}),('late',{'2024','2025'})]:
            group=[r for r in kept if r['year'] in years]
            count=sum(r['sensitivity_topic']==best for r in group)
            item[name+'_count']=count; item[name+'_denominator']=len(group); item[name+'_share_pct']=100*count/len(group)
        item['late_minus_early_pp']=item['late_share_pct']-item['early_share_pct']
        comparison.append(item)
    write('leakage_exclusion_sensitivity.csv',comparison)
    m={'excluded_records':len(rows)-len(kept),'remaining_records':len(kept),'fit_unique_texts':len(idx),
        'refit_clusters':len(set(labels)-{-1}),'noise_unique_pct':float(np.mean(labels==-1)*100),
        'adjusted_rand_index_including_noise':float(adjusted_rand_score(old_labels,labels)),
        'method':'refit same UMAP/HDBSCAN settings after removing warning-keyword matches; compare by maximum Jaccard',
        'caveat':'warning matches may include legitimate claim wording; sensitivity, not an adjudicated exclusion rule',
        'script_sha256':sha(Path(__file__))}
    (OUT/'leakage_sensitivity_metrics.json').write_text(json.dumps(m,ensure_ascii=False,indent=2))
    print(m); print([r for r in comparison if r['original_topic'] in [1,2,4,6,7,11]])
if __name__=='__main__': main()
