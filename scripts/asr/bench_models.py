#!/usr/bin/env python3
"""Measure a verdict-extraction model against the human labels.

The pipeline has exactly one accuracy number -- 89.9%, from qwen2.5:14b with
prompt v2 -- and that number belongs to a model no longer installed. Every
candidate since has been argued for on reputation. This runs them against the
105 records that carry BOTH a human verdict and a transcript, which is the only
evidence available about which is actually better at this job.

Reports per-class accuracy, not just overall: prompt v1 scored 91% on false and
20% on true, and an overall figure would have hidden that.
"""
import json, sys, time, urllib.request, collections
import asr_worker as W

model = sys.argv[1]
rows = [json.loads(l) for l in open('bench.jsonl')]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else len(rows)
rows = rows[:limit]

def ask(transcript, title):
    body = {'model': model, 'prompt': W.PROMPT.format(title=title, transcript=transcript)
            if '{transcript}' in W.PROMPT else W.PROMPT.format(title=title, body=transcript),
            'stream': False, 'format': 'json', 'think': False,  # qwen3.8 reasons by default and JSON mode then returns empty
            'options': {'temperature': 0, 'num_predict': int(__import__('os').getenv('NP','512'))}}
    req = urllib.request.Request('http://127.0.0.1:11434/api/generate',
                                 data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(json.loads(r.read())['response'])

hit = collections.Counter(); tot = collections.Counter(); errs = 0
t0 = time.time()
for i, r in enumerate(rows, 1):
    tot[r['human']] += 1
    try:
        out = ask(r['transcript'], r['title'])
        got = str(out.get('verdict', '')).strip().lower()
        if got == r['human']:
            hit[r['human']] += 1
    except Exception as e:
        errs += 1
        if errs <= 2: print('  err:', str(e)[:90], flush=True)
    if i % 20 == 0: print(f'  {i}/{len(rows)}', flush=True)
el = time.time() - t0
print()
print(f'MODEL {model}')
for k in ('true', 'false', 'misleading'):
    if tot[k]: print(f'  {k:11} {hit[k]:3}/{tot[k]:3}  {100*hit[k]/tot[k]:5.1f}%')
n = sum(tot.values()); h = sum(hit.values())
print(f'  {"OVERALL":11} {h:3}/{n:3}  {100*h/n:5.1f}%   errors={errs}  {el/max(n,1):.1f}s/record')
