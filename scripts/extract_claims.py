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
from th_verify.normalized import clean_claim_text, is_factcheck  # noqa: E402
from _canonical import assert_canonical  # noqa: E402

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435")
# Typhoon is SCB10X's Thai-tuned model and it shows on this task: on the same
# 12 Thai PBS articles it produced a usable claim for all 12 where qwen2.5:14b
# managed 10, and its wordings track how the post was actually phrased rather
# than paraphrasing the headline back. Overridable, since the comparison should
# be repeated whenever the archive's mix changes.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "scb10x/typhoon2.5-qwen3-30b-a3b:latest")

# If any of these survive into the "claim", the model has restated the finding.
VERDICT_WORDS = re.compile(
    r"ข่าวปลอม|ข่าวจริง|ข่าวบิดเบือน|ภาพปลอม|ไม่เป็นความจริง|เป็นความจริง|"
    r"ตรวจสอบพบ|ที่แท้|แท้จริง|สร้าง(?:จาก|ด้วย)\s*AI|เป็นคลิปเก่า|เป็นภาพเก่า|บิดเบือน|"
    # "พบเป็นเพียงคลื่นลม", "พบเป็นปรากฏการณ์เกิดขึ้นทุกปี" -- Thai PBS's usual way
    # of writing the finding into the headline. Two of the first 376 extractions
    # came back with the headline intact because nothing here matched it.
    # เท่านั้น ("only") was tried here and removed: it is ordinary vocabulary,
    # and it rejected real claims such as
    # "มุสลิมสามารถซื้อที่ดินได้ไม่จำกัด ส่วนชาวพุทธ…เท่านั้น".
    r"พบเป็น|พบว่าเป็น")

# A headline still opening this way after cleaning is addressed to the reader,
# not a statement of what was claimed.
WARNING_LEAD = re.compile(r"^(ระวัง|เตือน|อย่าหลงเชื่อ|โปรดระวัง|พบ|เผย)")

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


# Quoting the post faithfully brings the post's decoration with it -- flags,
# rockets, sirens. The claim is the proposition, not the styling.
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U0000FE0F\U00002B00-\U00002BFF\U00002190-\U000021FF]+")


def tidy(claim: str) -> str:
    claim = _EMOJI.sub(" ", claim)
    claim = re.sub(r"\s*[.\u00b7\-–—:;,]+\s*$", "", claim)
    return re.sub(r"\s{2,}", " ", claim).strip()


def _grams(s: str, n: int = 3) -> set[str]:
    """Character n-grams, because Thai does not put spaces between words.

    The first version of this guard split on whitespace. In Thai that yields one
    token for a whole clause, so a faithful short claim -- "ตำรวจยศสูงไหว้นักการเมือง"
    against a headline containing exactly that phrase -- scored an overlap of 1
    and was thrown away as unrelated. 85 of the first 555 extractions were
    rejected for that reason, and the good ones among them were being discarded
    for a property of the writing system.
    """
    s = re.sub(r"[\s“”\"'·,()\[\]?!.]+", "", s or "")
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _same(a: str, b: str) -> bool:
    """Equal once punctuation and spacing stop mattering."""
    norm = lambda s: re.sub(r"[\s\u201c\u201d\"'?!.\u00b7:;,\-–—]+", "", s or "")
    return norm(a) == norm(b)


def judge(claim: str, title: str, body: str) -> str | None:
    """Return a rejection reason, or None if the claim is acceptable."""
    if not claim or len(claim) < 12:
        return "too short"
    if len(claim) > 220:
        return "too long"
    if VERDICT_WORDS.search(claim):
        return "contains a verdict"
    # Handing the headline back is not an extraction. The caller already
    # compares against the *cleaned* title; this catches the raw one, which
    # differs by a quote mark often enough to slip past.
    if _same(claim, title):
        return "same as the headline"
    # Share of the claim that can be found in the article. A model that drifted
    # onto another story scores near zero; a faithful rewording scores high even
    # when it reorders or trims.
    g = _grams(claim)
    if not g:
        return "too short"
    if len(g & (_grams(title) | _grams(body[:2500]))) / len(g) < 0.45:
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
    ap.add_argument("--needs-work", action="store_true",
                    help="only rows the rule cleaner demonstrably fails on")
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
        f"SELECT id, source, title, claim, explanation, verdict, verdict_origin "
        f"FROM fact_checks WHERE {' AND '.join(where)} ORDER BY id DESC "
        f"LIMIT {'-1' if args.needs_work else '?'}",
        params if args.needs_work else [*params, args.limit]).fetchall()

    if args.needs_work:
        # Running a model over every AFNC row would spend five hours to change a
        # fifth of them: the rule cleaner already strips "ข่าวปลอม อย่าแชร์!" from
        # 10,192 of 16,993, and 2,205 are not fact-checks at all -- weekly
        # roundups and announcements that nobody should be extracting a claim
        # from. What is left is the residue the rules cannot handle: a headline
        # that still opens as a warning ("ระวัง!! มิจฯ อ้างตรวจสอบบัญชี..."), or
        # one long enough that it is plainly a summary rather than a claim.
        kept = []
        for r in rows:
            if not is_factcheck(r["source"], r["title"], r["verdict"],
                                (r["explanation"] or "")[:120], r["verdict_origin"]):
                continue
            cleaned = clean_claim_text(r["title"], r["source"])
            if WARNING_LEAD.match(cleaned) or len(cleaned) > 110:
                kept.append(r)
        print(f"{len(rows)} rows -> {len(kept)} the rules fail on")
        rows = kept[: args.limit]

    print(f"{len(rows)} candidates ({OLLAMA_MODEL})\n")

    accepted, rejected = [], {}
    for r in rows:
        try:
            out = ollama(PROMPT.format(title=r["title"], body=r["explanation"][:3500]))
        except Exception as exc:
            # Named, because "error: 13" three runs running tells you nothing
            # about whether the model is timing out, refusing, or emitting
            # something that is not JSON -- and only one of those is worth a fix.
            kind = f"error ({type(exc).__name__})"
            rejected[kind] = rejected.get(kind, 0) + 1
            continue
        claim = tidy(str(out.get("claim", "")))
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
