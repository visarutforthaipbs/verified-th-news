"""Local-LLM helpers running on the aipower box (RTX 3090, Ollama).

Two subcommands:

  extract-verdicts   Label remaining unknown cofact/thaipbs records by
                     extracting the verdict the fact-checker already wrote
                     in the article text. Writes verdict_origin='llm'.
                     The extracted quote must appear verbatim in the source
                     text or the record is left untouched (hallucination
                     guard). Never touches human/source-labeled rows.

  summarize          VerifyDesk helper: given a claim, retrieve related
                     fact-checks from the semantic index and generate a
                     source-backed Thai evidence summary with citations.

Usage:
  python scripts/llm_assist.py extract-verdicts [--limit 50] [--dry-run]
  python scripts/llm_assist.py summarize "ข้อความที่ต้องตรวจสอบ"

Env:
  OLLAMA_URL   default http://192.168.31.19:11434  (aipower)
  OLLAMA_MODEL default qwen2.5:14b
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

sys.path.insert(0, str(Path(__file__).parent))

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://192.168.31.19:11434")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
DB = "data/th_verify.db"

VALID = {"false", "true", "misleading"}

EXTRACT_PROMPT = """อ่านบทความตรวจสอบข้อเท็จจริงต่อไปนี้ แล้วสกัด "ผลการตรวจสอบ" ที่ผู้ตรวจสอบระบุไว้

ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น:
{{"verdict": "false" | "true" | "misleading" | "unclear", "verdict_quote": "ประโยคที่คัดลอกตรงตัวจากบทความซึ่งระบุผลการตรวจสอบ"}}

กติกา:
- "false" = บทความสรุปว่าเนื้อหาเป็นเท็จ/ข่าวปลอม/ไม่จริง
- "true" = บทความสรุปว่าเนื้อหาเป็นจริง
- "misleading" = บทความสรุปว่าบิดเบือน/จริงบางส่วน/ทำให้เข้าใจผิด
- "unclear" = บทความไม่ได้ระบุผลตรวจสอบชัดเจน (เช่น เป็นข่าวกิจกรรม บทสัมภาษณ์ งานเสวนา)
- verdict_quote ต้องคัดลอกตรงตัวจากบทความเท่านั้น ห้ามแต่งเอง

บทความ:
{text}"""

SUMMARY_PROMPT = """คุณเป็นผู้ช่วยนักตรวจสอบข้อเท็จจริง จงเขียนสรุปหลักฐานภาษาไทยสำหรับข้อความที่ได้รับแจ้ง โดยอ้างอิงเฉพาะผลตรวจสอบเดิมที่ให้มาเท่านั้น ห้ามเพิ่มข้อมูลจากความรู้ของคุณเอง

รูปแบบ:
1. ข้อความที่ได้รับแจ้ง (1 บรรทัด)
2. สิ่งที่พบจากคลังตรวจสอบ (อ้างอิงหมายเลข [1], [2] ตามรายการ)
3. ข้อสรุปเบื้องต้นและระดับความมั่นใจ
4. สิ่งที่ยังต้องตรวจสอบเพิ่ม

ข้อความที่ได้รับแจ้ง: {claim}

ผลตรวจสอบเดิมที่เกี่ยวข้อง:
{evidence}"""


def ollama(prompt: str, json_mode: bool = False, num_predict: int = 600) -> str:
    body: dict = {
        "model": MODEL, "prompt": prompt, "stream": False,
        "options": {"temperature": 0, "num_predict": num_predict},
    }
    if json_mode:
        body["format"] = "json"
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["response"]


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def extract_verdicts(limit: int, dry_run: bool) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from th_verify.models import utc_now

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, source, title, explanation FROM fact_checks "
        "WHERE verdict='unknown' AND source IN ('cofact','thaipbs') "
        "AND verdict_origin='' AND LENGTH(explanation) > 200 "
        "ORDER BY id LIMIT ?", (limit,),
    ).fetchall()
    print(f"candidates: {len(rows)}")
    labeled = skipped = rejected = 0
    for r in rows:
        text = r["explanation"][:6000]
        try:
            out = json.loads(ollama(EXTRACT_PROMPT.format(text=text),
                                    json_mode=True, num_predict=250))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  id={r['id']} error: {e}")
            continue
        verdict = out.get("verdict", "unclear")
        quote = out.get("verdict_quote", "")
        if verdict not in VALID:
            skipped += 1
            continue
        if _norm(quote) not in _norm(text):  # hallucination guard
            rejected += 1
            print(f"  id={r['id']} REJECTED (quote not in text): {quote[:60]}")
            continue
        labeled += 1
        print(f"  id={r['id']} -> {verdict} | {quote[:70]}")
        if not dry_run:
            con.execute(
                "UPDATE fact_checks SET verdict=?, verdict_origin='llm',"
                " labeled_at=? WHERE id=? AND verdict_origin NOT LIKE 'human%'",
                (verdict, utc_now(), r["id"]),
            )
            con.commit()
    print(f"labeled={labeled} unclear={skipped} rejected={rejected}"
          f"{' (dry run, nothing written)' if dry_run else ''}")


def summarize(claim: str) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from th_verify.search import get_searcher

    hits = get_searcher().search(claim, top_k=4)
    hits = [h for h in hits if h["score"] >= 0.85]
    if not hits:
        print("ไม่พบผลตรวจสอบเดิมที่ใกล้เคียงในคลังข้อมูล — ต้องตรวจสอบใหม่ทั้งหมด")
        return
    evidence = "\n".join(
        f"[{i}] ({h['source']}, {(h['published_at'] or '')[:10]}, "
        f"ผล: {h['label']}, ความคล้าย {h['score']:.0%}) {h['claim_text']}\n"
        f"    สรุป: {h['explanation_snippet'][:300]}\n    ลิงก์: {h['url']}"
        for i, h in enumerate(hits, 1)
    )
    print(ollama(SUMMARY_PROMPT.format(claim=claim, evidence=evidence)))
    print("\n--- แหล่งอ้างอิง ---")
    for i, h in enumerate(hits, 1):
        print(f"[{i}] {h['url']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("extract-verdicts")
    p1.add_argument("--limit", type=int, default=50)
    p1.add_argument("--dry-run", action="store_true")
    p2 = sub.add_parser("summarize")
    p2.add_argument("claim")
    args = ap.parse_args()
    if args.cmd == "extract-verdicts":
        extract_verdicts(args.limit, args.dry_run)
    else:
        summarize(args.claim)


if __name__ == "__main__":
    main()
