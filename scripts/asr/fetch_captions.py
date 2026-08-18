#!/usr/bin/env python3
"""Fetch YouTube Thai auto-captions instead of downloading and transcribing audio.

Why this exists
---------------
The audio pipeline's expensive, fragile half is the DOWNLOAD, not the GPU: on
2026-08-17 roughly half of 1,858 attempts failed to YouTube throttling, and the
run yielded 713 labels instead of ~1,340. Captions are a different, much lighter
request that succeeded on every video whose audio had 403'd.

Measured, not assumed. On 32 records carrying both a human verdict and a whisper
transcript, feeding Typhoon-S the caption text scored 81.2% against whisper's
75.0% -- so captions cost no accuracy. n=32 and the set had no `true` records,
so treat that as "no penalty" rather than "better".

Availability depends entirely on age:

    2016  4/7      2020  4/7      2024  7/7
    2018  0/7      2022  7/7      2026  7/7

2022 onward is reliable; before that it is not. That happens to fit the backlog:
4,344 of the 4,865 unlabelled Sure & Share records are 2022+, including 3,633 of
the 3,735 shorts. Whisper remains the fallback for the pre-2022 tail.

A warning about the FULL transcript. It is tempting to think that dropping the
45-second window must help, since a LIVE episode states its verdict mid-
programme. On standard episodes it made things WORSE -- 68.8% against 81.2% for
the tail, plus 4 errors -- because the verdict gets diluted among everything
else that was said. Use the tail by default; reach for the full text only where
the tail is known to fail (LIVE, podcasts, shorts).


Two variants per record so the comparison separates two questions:
  tail  -- the last 45s, matching exactly what whisper was given, which
           isolates ASR QUALITY (YouTube's Thai ASR vs whisper large-v3)
  full  -- the whole programme, which is what captions actually buy: no
           45-second window, so a verdict stated mid-episode is reachable

YouTube's Thai ASR emits a space between syllables ("ก็ สามารถ แชร์ ต่อ ได้").
Thai does not use word spaces, so that is an artefact of their tokeniser and is
stripped -- otherwise every downstream string match sees different text for the
same words.
"""
import json, re, sys, urllib.request
import yt_dlp

OPTS = {'quiet': True, 'skip_download': True, 'no_warnings': True}

def despace(t: str) -> str:
    t = re.sub(r'\[[^\]]{0,20}\]', ' ', t)           # [เพลง], [ดนตรี]
    t = re.sub(r'(?<=[฀-๿]) (?=[฀-๿])', '', t)
    return re.sub(r'\s+', ' ', t).strip()

def fetch(url):
    with yt_dlp.YoutubeDL(OPTS) as y:
        info = y.extract_info(url, download=False)
    auto = info.get('automatic_captions') or {}
    track = auto.get('th') or auto.get('th-orig')
    if not track:
        return None, None
    j3 = next((t for t in track if t.get('ext') == 'json3'), track[0])
    data = json.loads(urllib.request.urlopen(j3['url'], timeout=40).read())
    dur = info.get('duration') or 0
    ev = [e for e in data.get('events', []) if e.get('segs')]
    def join(events):
        return despace(' '.join(s.get('utf8', '') for e in events for s in e['segs']))
    tail = [e for e in ev if (e.get('tStartMs', 0)/1000) >= max(0, dur - 45)]
    return join(tail), join(ev)

rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
out_tail, out_full, miss = [], [], 0
for i, r in enumerate(rows, 1):
    try:
        tail, full = fetch(r['url'])
    except Exception as e:
        tail = full = None
    if not tail:
        miss += 1
    else:
        out_tail.append({**{k: r[k] for k in ('id','title','human')}, 'transcript': tail})
        out_full.append({**{k: r[k] for k in ('id','title','human')}, 'transcript': full[-12000:]})
    if i % 20 == 0:
        print(f'  {i}/{len(rows)}  (no captions: {miss})', flush=True)
json.dump(out_tail, open('cap_tail.json','w'), ensure_ascii=False)
json.dump(out_full, open('cap_full.json','w'), ensure_ascii=False)
print(f'captions for {len(out_tail)} of {len(rows)}; {miss} had none')
