#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asr_rescore.py — re-run verdict extraction over transcripts already produced.

The expensive part of the pipeline is downloading and transcribing audio; the
verdict extraction is one cheap LLM call. Because `asr_worker.py` stores the
transcript on every record, prompt changes can be evaluated in minutes against
the exact same audio instead of re-running the GPU for an hour.

Run this from the machine with the database, against the Ollama tunnel.

    python scripts/asr/asr_rescore.py results.jsonl --out rescored.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
VALID = {"false", "true", "misleading", "altered_media"}

# v2. The first prompt scored 91% on 'false' but only 20% on 'true': it kept
# downgrading a clear "จริง" to "misleading" whenever the host added any caveat.
# The cause was omitting the programme's own convention -- ชัวร์ก่อนแชร์ ends by
# telling the audience whether to share, and "แชร์ได้" IS the true verdict.
# Observed misses this fixes: "เรื่องนี้ชัวร์ครับ แชร์ได้ ผมยืนยัน" and
# "สรุปแฮงกินพาราอาจตายได้ แชร์ได้ครับ", both labelled misleading before.
PROMPT_V2 = """ต่อไปนี้คือถอดเสียงช่วงท้ายของรายการ "ชัวร์ก่อนแชร์"
ผู้ดำเนินรายการจะสรุปผลการตรวจสอบและบอกผู้ชมว่าควรแชร์หรือไม่

หัวข้อของคลิป: {title}

ถอดเสียง:
{transcript}

ตอบเป็น JSON เท่านั้น:
{{"verdict": "false" | "true" | "misleading" | "altered_media" | "unclear", "quote": "ประโยคที่คัดลอกตรงตัวจากถอดเสียงซึ่งระบุผลสรุป"}}

สัญญาณสำคัญที่สุด คือคำแนะนำเรื่องการแชร์ตอนท้าย:
- ถ้าผู้ดำเนินรายการบอกว่า "แชร์ได้", "แชร์ต่อได้", "เรื่องนี้ชัวร์", "ยืนยัน", "จริง" → ตอบ "true"
- ถ้าบอกว่า "ไม่ควรแชร์", "อย่าแชร์", "ไม่จริง", "ข่าวปลอม" → ตอบ "false"
- ถ้าบอกว่า "แชร์ได้แต่ต้องอธิบายเพิ่ม", "จริงบางส่วน", "ขาดบริบท", "ไม่ครบถ้วน" → ตอบ "misleading"
- ถ้าบอกว่าภาพหรือคลิปถูกตัดต่อ/สร้างด้วย AI → ตอบ "altered_media"
- ถ้าไม่ได้สรุปเลย → ตอบ "unclear"

ข้อควรระวังที่สำคัญมาก:
- ถ้าผู้ดำเนินรายการบอกว่า "แชร์ได้" ให้ตอบ "true" เสมอ
  แม้จะมีคำเสริม เช่น "แต่ไม่บ่อย" "แต่ต้องระวัง" "แต่ขึ้นอยู่กับ"
  คำเสริมเหล่านี้ไม่ได้ทำให้คำตอบเปลี่ยนเป็น "misleading"
- ตอบ "misleading" เฉพาะเมื่อผู้ดำเนินรายการบอกว่า "ตัวข้อกล่าวอ้างเอง" ไม่ถูกต้องครบถ้วน
  ไม่ใช่เพราะมีข้อยกเว้นเล็กน้อย
- quote ต้องคัดลอกตรงตัวจากถอดเสียงเท่านั้น ห้ามแต่งขึ้นเอง"""


# v3. v2 fixed 'true' (20% -> 100%) and 'false' (91% -> 97%) but collapsed
# 'misleading' from 79% to 43%: narrowing misleading to "the claim itself is
# incomplete" pushed 8 borderline cases into false. v3 keeps v2's decisive
# share-instruction rule and restores v1's broader misleading cues, with the
# distinction stated explicitly -- fabricated vs real-but-misrepresented.
PROMPT_V3 = """ต่อไปนี้คือถอดเสียงช่วงท้ายของรายการ "ชัวร์ก่อนแชร์"
ผู้ดำเนินรายการจะสรุปผลการตรวจสอบและบอกผู้ชมว่าควรแชร์หรือไม่

หัวข้อของคลิป: {title}

ถอดเสียง:
{transcript}

ตอบเป็น JSON เท่านั้น:
{{"verdict": "false" | "true" | "misleading" | "altered_media" | "unclear", "quote": "ประโยคที่คัดลอกตรงตัวจากถอดเสียงซึ่งระบุผลสรุป"}}

ขั้นตอนการตัดสิน ทำตามลำดับ:

ขั้นที่ 1 — ผู้ดำเนินรายการบอกให้แชร์ได้หรือไม่?
- ถ้าบอกว่า "แชร์ได้", "แชร์ต่อได้", "เรื่องนี้ชัวร์", "ยืนยัน", "เป็นเรื่องจริง" → ตอบ "true"
- คำเสริมเช่น "แต่ไม่บ่อย" "แต่ต้องระวัง" "แต่ขึ้นอยู่กับ" ไม่ทำให้เปลี่ยนเป็นอย่างอื่น
- ถ้าเข้าข้อนี้ ให้หยุด ตอบ "true" ทันที

ขั้นที่ 2 — ถ้าบอกว่าไม่ควรแชร์ ให้ดูว่าเป็นแบบไหน
- ข้อกล่าวอ้าง "ถูกกุขึ้นทั้งหมด" ไม่มีเหตุการณ์นั้นจริงเลย → ตอบ "false"
- ข้อกล่าวอ้าง "มีส่วนจริง" แต่ถูกเล่าผิด → ตอบ "misleading"
  สัญญาณของ misleading: "จริงบางส่วน", "ไม่ครบถ้วน", "ขาดบริบท", "เกินจริง",
  "ข้อมูลเก่า", "ต้องมีเงื่อนไข", "ไม่ใช่ทั้งหมด", "เข้าใจผิด", "แล้วแต่กรณี",
  "แล้วแต่นโยบาย", "ไม่ได้แปลว่า"
- ภาพหรือคลิปถูกตัดต่อ/สร้างด้วย AI → ตอบ "altered_media"

ขั้นที่ 3 — ไม่ได้สรุปเลย → ตอบ "unclear"

สำคัญ: "ไม่ควรแชร์" อย่างเดียวไม่ได้แปลว่า "false" เสมอไป
ต้องดูว่าข้อกล่าวอ้างนั้นเท็จทั้งหมด หรือแค่จริงไม่ครบ

quote ต้องคัดลอกตรงตัวจากถอดเสียงเท่านั้น ห้ามแต่งขึ้นเอง"""

PROMPTS = {"v2": PROMPT_V2, "v3": PROMPT_V3}


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def ollama(prompt: str) -> dict:
    body = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
            "format": "json", "options": {"temperature": 0, "num_predict": 300}}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(json.loads(r.read())["response"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--prompt", default="v3", choices=["v2", "v3"])
    args = ap.parse_args()

    records = [json.loads(l) for l in args.results.read_text(encoding="utf-8").splitlines() if l.strip()]
    have_transcript = [r for r in records if r.get("transcript")]
    print(f"{len(have_transcript)} transcripts to re-score "
          f"(of {len(records)} records)")

    stats = {"labelled": 0, "unclear": 0, "rejected": 0, "error": 0}
    with args.out.open("w", encoding="utf-8") as fh:
        for i, r in enumerate(records, 1):
            out = dict(r)
            tr = r.get("transcript")
            if not tr:
                fh.write(json.dumps(out, ensure_ascii=False) + "\n")
                continue
            try:
                res = ollama(PROMPTS[args.prompt].format(title=r["title"], transcript=tr))
                verdict = str(res.get("verdict", "")).strip()
                quote = str(res.get("quote", ""))
                out["raw_verdict"], out["quote"] = verdict, quote
                if verdict not in VALID:
                    out["status"] = "unclear"
                    out.pop("verdict", None)
                    stats["unclear"] += 1
                elif norm(quote) not in norm(tr):
                    out["status"] = "rejected_quote_not_in_transcript"
                    out.pop("verdict", None)
                    stats["rejected"] += 1
                else:
                    out["status"] = "labelled"
                    out["verdict"] = verdict
                    stats["labelled"] += 1
            except Exception as exc:
                out["status"] = "error"
                out["error"] = str(exc)[:200]
                stats["error"] += 1
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")
            if i % 20 == 0:
                print(f"  {i}/{len(records)} {stats}", flush=True)
    print(f"done: {stats}\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
