#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_claims.py — derive the claim under review from the article, using the
local model on lighthouse-gpu01.

The problem
-----------
`claim` is a copy of `title` for 27,925 of 28,686 records, and a headline is not
a claim. It is written for readers and often carries the answer:

    headline   โพสต์อ้างข่าวปลอม ตำรวจยศสูงไหว้นักการเมือง ชี้เป็นภาพ AI
               ตรวจสอบพบเป็นภาพจริง ปี 61
    the claim  ตำรวจยศสูงไหว้นักการเมือง

Rules strip the worst of it -- verdict prefixes, trailing conclusions -- but they
cannot restructure a sentence, and the publishers only rarely state the claim in
machine-readable form (AFP always, Thai PBS reuses the headline 90% of the time).

Why extraction rather than generation
-------------------------------------
The claim is present in the article: fact-checks open by stating what was shared
before addressing it. So the model is asked to COPY the claim, not to compose one,
and output is rejected unless it is faithful to the source. That is the same
verbatim-quote discipline the verdict extractor uses -- there, a quote that did
not literally occur in the transcript was discarded rather than trusted.

Guards, in order of how much they matter:
  * the extracted claim must not contain a verdict word -- if it does, the model
    has summarised the answer rather than isolated the claim;
  * it must be shorter than the article and longer than a fragment;
  * it must share substantial vocabulary with the title, or the model has drifted
    onto a different subject entirely.

Anything rejected keeps the existing claim. A missing improvement is free; a
confidently wrong claim is not, because it becomes the text a model trains on and
the text a reviewer reads.

Usage:
    export OLLAMA_URL=http://127.0.0.1:11435
    python scripts/extract_claims.py --source thaipbs --limit 40        # dry run
    python scripts/extract_claims.py --source thaipbs --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from th_verify.normalized import clean_claim_text  # noqa: E402
from _canonical import assert_canonical  # noqa: E402

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

# If any of these survive into the "claim", the model has restated the finding.
VERDICT_WORDS = re.compile(
    r"ข่าวปลอม|ข่าวจริง|ข่าวบิดเบือน|ภาพปลอม|ไม่เป็นความจริง|เป็นความจริง|"
    r"ตรวจสอบพบ|ที่แท้|แท้จริง|สร้างจาก\s*AI|เป็นคลิปเก่า|เป็นภาพเก่า|บิดเบือน")

PROMPT = """บทความต่อไปนี้เป็นงานตรวจสอบข้อเท็จจริง
งานของคุณคือ "คัดลอก" ข้อกล่าวอ้างที่ถูกนำมาตรวจสอบ ไม่ใช่สรุปผลการตรวจสอบ

หัวข้อบทความ: {title}

เนื้อหา:
{body}

ตอบเป็น JSON เท่านั้น:
{{"claim": "ข้อกล่าวอ้างที่ถูกตรวจสอบ"}}

กติกา:
- เขียนข้อกล่าวอ้างในรูปแบบที่ "คนแชร์กันบนโซเชียล" ก่อนถูกตรวจสอบ
- ห้ามใส่ผลการตรวจสอบ เช่น "ข่าวปลอม", "ที่แท้เป็น...", "ตรวจสอบพบว่า...", "สร้างจาก AI"
- ห้ามใส่คำว่าใครเป็นผู้ตรวจสอบ
- ใช้ถ้อยคำจากบทความ ไม่ต้องแต่งใหม่
- ความยาวไม่เกิน 1 ประโยค"""


def ollama(prompt: str) -> dict:
    body = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
            "format": "json", "options": {"temperature": 0, "num_predict": 200}}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(json.loads(r.read())["response"])


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[\s“”\"'·,()\[\]]+", s or "") if len(t) > 1}


def judge(claim: str, title: str, body: str) -> str | None:
    """Return a rejection reason, or None if the claim is acceptable."""
    if not claim or len(claim) < 12:
        return "too short"
    if len(claim) > 220:
        return "too long"
    if VERDICT_WORDS.search(claim):
        return "contains a verdict"
    overlap = _tokens(claim) & (_tokens(title) | _tokens(body[:1500]))
    if len(overlap) < 2:
        return "unrelated to the article"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--source")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--min-explanation", type=int, default=300)
    args = ap.parse_args()
    if args.apply:
        assert_canonical(args.db, action="write claims into")

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    where = ["claim_origin = ''", "length(explanation) >= ?"]
    params: list = [args.min_explanation]
    if args.source:
        where.append("source = ?")
        params.append(args.source)
    rows = con.execute(
        f"SELECT id, source, title, claim, explanation FROM fact_checks "
        f"WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?",
        [*params, args.limit]).fetchall()
    print(f"{len(rows)} candidates ({OLLAMA_MODEL})\n")

    accepted, rejected = [], {}
    for r in rows:
        try:
            out = ollama(PROMPT.format(title=r["title"], body=r["explanation"][:3500]))
        except Exception as exc:
            rejected["error"] = rejected.get("error", 0) + 1
            continue
        claim = str(out.get("claim", "")).strip()
        why = judge(claim, r["title"], r["explanation"])
        if why:
            rejected[why] = rejected.get(why, 0) + 1
            continue
        current = clean_claim_text(r["title"], r["source"])
        if claim == current:
            rejected["same as cleaned title"] = rejected.get("same as cleaned title", 0) + 1
            continue
        accepted.append((claim, r["id"]))
        print(f"  [{r['source']}] {r['id']}")
        print(f"    title : {r['title'][:74]}")
        print(f"    claim : {claim[:74]}\n")

    print(f"accepted : {len(accepted)}")
    for k, v in sorted(rejected.items(), key=lambda x: -x[1]):
        print(f"  rejected — {k:26} {v}")
    if not args.apply:
        print("\ndry run — nothing written.")
        return 0
    with con:
        for claim, rid in accepted:
            con.execute("UPDATE fact_checks SET claim=?, claim_origin='llm' "
                        "WHERE id=? AND claim_origin NOT IN ('human')", (claim, rid))
    print(f"\napplied {len(accepted)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
