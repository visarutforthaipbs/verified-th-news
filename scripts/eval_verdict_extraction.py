#!/usr/bin/env python3
"""
eval_verdict_extraction.py — score verdict extraction against a real answer key.

Why this can exist now
----------------------
Thai PBS embeds a schema.org ClaimReview block per article carrying the
publisher's own verdict. That is ground truth, so extraction quality can be
*measured* rather than eyeballed. The 2026-07-12 audit ("20 samples, 0 errors")
judged whether labels looked plausible against the article; scoring against the
answer key put the real `llm` error rate at 21%.

What it compares
----------------
Any (model, prompt) combination on the same fixed eval set, so model choice and
prompt wording can be separated. Both matter here:

* The incumbent prompt offers only false/true/misleading/unclear. The corpus
  also uses **altered_media**, so on a doctored-image story the model could not
  be right -- it had no such option and answered "false". That is a schema bug
  and no model swap fixes it.
* The incumbent model is qwen2.5:14b, a general multilingual model, while every
  article is Thai. scb10x/llama3.1-typhoon2-8b-instruct is Thai-specialised but
  smaller (8B vs 14B), so this trades language fit against capacity -- exactly
  the kind of question that should be answered with numbers.

Usage
-----
    python scripts/eval_verdict_extraction.py --list-models
    python scripts/eval_verdict_extraction.py --model qwen2.5:14b --prompt v1 -n 60
    python scripts/eval_verdict_extraction.py --sweep -n 60
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from build_dataset import normalize_verdict  # noqa: E402

OLLAMA_URL = "http://127.0.0.1:11435"
DB = "data/th_verify.db"

# ---------------------------------------------------------------------------
# Prompts under test
# ---------------------------------------------------------------------------

# The prompt currently shipped in llm_assist.py, reproduced verbatim so the
# comparison is honest. Note the missing altered_media option.
PROMPT_V1 = """อ่านบทความตรวจสอบข้อเท็จจริงต่อไปนี้ แล้วสกัด "ผลการตรวจสอบ" ที่ผู้ตรวจสอบระบุไว้

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

# v2 adds the missing category and attacks the observed failure mode directly:
# the model collapses nuanced verdicts into "fake". 41 of 70 observed errors were
# false-instead-of-misleading and 11 were false-instead-of-altered_media, so the
# rules below spell out the boundary and instruct a default away from "false".
PROMPT_V2 = """อ่านบทความตรวจสอบข้อเท็จจริงต่อไปนี้ แล้วสกัด "ผลการตรวจสอบ" ที่ผู้ตรวจสอบระบุไว้

ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น:
{{"verdict": "false" | "true" | "misleading" | "altered_media" | "unclear", "verdict_quote": "ประโยคที่คัดลอกตรงตัวจากบทความซึ่งระบุผลการตรวจสอบ"}}

กติกา (อ่านให้ครบก่อนตอบ):
- "altered_media" = สื่อถูกดัดแปลงทางเทคนิค เช่น ภาพตัดต่อ ภาพ/คลิปที่สร้างด้วย AI, deepfake, เสียงสังเคราะห์
  คำที่บ่งชี้: "ภาพปลอม", "คลิปปลอม", "สร้างด้วย AI", "ตัดต่อ", "deepfake"
- "misleading" = เนื้อหามีส่วนจริง แต่ถูกใช้ผิดบริบท ตัดตอน พาดหัวเกินจริง หรือเป็นของเก่า/สถานที่อื่น
  คำที่บ่งชี้: "ข่าวบิดเบือน", "จริงบางส่วน", "ผิดบริบท", "คลิปเก่า", "แท้จริงเป็นเหตุการณ์อื่น",
  "ไม่ได้เกิดขึ้นที่", "เป็นภาพจากปี"
- "false" = ข้อกล่าวอ้างถูกกุขึ้นทั้งหมด ไม่มีเหตุการณ์นั้นจริง
- "true" = บทความสรุปว่าเนื้อหาเป็นจริง
- "unclear" = บทความไม่ได้ระบุผลตรวจสอบ หรือผู้ตรวจสอบไม่ตัดสิน

ข้อควรระวังที่สำคัญที่สุด:
- อย่าเหมารวมทุกอย่างเป็น "false" นี่คือข้อผิดพลาดที่พบบ่อยที่สุด
- ถ้าสื่อต้นทางเป็นของจริงแต่ถูกเล่าผิด ให้ตอบ "misleading" ไม่ใช่ "false"
- ถ้าภาพหรือคลิปถูกดัดแปลง/สร้างด้วย AI ให้ตอบ "altered_media" ไม่ใช่ "false"
- ตอบ "false" เฉพาะเมื่อไม่มีเหตุการณ์ตามข้อกล่าวอ้างเลย
- verdict_quote ต้องคัดลอกตรงตัวจากบทความเท่านั้น ห้ามแต่งเอง

บทความ:
{text}"""

PROMPTS = {"v1": PROMPT_V1, "v2": PROMPT_V2}
LABELS = ("false", "true", "misleading", "altered_media", "unclear")


def ollama(model: str, prompt: str, num_predict: int = 250) -> str:
    body = {"model": model, "prompt": prompt, "stream": False, "format": "json",
            "options": {"temperature": 0, "num_predict": num_predict}}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["response"]


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def load_eval_set(db: str, limit: int, stratified: bool = False,
                  max_chars: int = 6000) -> list[dict]:
    """Thai PBS rows whose stored verdict came from ClaimReview (the answer key).

    Only rows with real article text are usable, and 'unknown' ground truth is
    excluded -- those are articles the publisher declined to rate, which measure
    abstention rather than extraction.
    """
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, source_id, title, explanation, verdict FROM fact_checks "
        "WHERE source='thaipbs' AND LENGTH(explanation) > 400 "
        "ORDER BY source_id"
    ).fetchall()
    out = []
    for r in rows:
        truth = normalize_verdict("thaipbs", r["verdict"])
        if truth in ("unknown",):
            continue
        out.append({"id": r["id"], "source_id": r["source_id"],
                    "text": r["explanation"][:max_chars], "truth": truth})
    if not limit or limit >= len(out):
        return out

    if stratified:
        # The archive is ~73% 'false', so a proportional sample carries only a
        # handful of misleading/altered_media rows -- too few to measure the very
        # confusion under investigation. Draw evenly per class instead. Accuracy
        # from a stratified sample is NOT comparable to the natural-distribution
        # number; read the per-class rates, and expect the headline figure to
        # look worse simply because the hard classes are over-represented.
        by_class: dict[str, list[dict]] = defaultdict(list)
        for s in out:
            by_class[s["truth"]].append(s)
        per = max(1, limit // len(by_class))
        picked = []
        for label in sorted(by_class):
            pool = by_class[label]
            step = max(1, len(pool) / per)
            picked.extend(pool[int(i * step)] for i in range(min(per, len(pool))))
        return picked

    # Deterministic spread across the archive rather than the newest N.
    step = len(out) / limit
    return [out[int(i * step)] for i in range(limit)]


def run_combo(model: str, prompt_key: str, samples: list[dict], delay: float) -> dict:
    prompt = PROMPTS[prompt_key]
    correct = guard_rejected = malformed = 0
    confusion: dict[tuple[str, str], int] = defaultdict(int)
    per_truth = Counter()
    started = time.time()

    for i, s in enumerate(samples, 1):
        try:
            raw = ollama(model, prompt.format(text=s["text"]))
            out = json.loads(raw)
        except Exception:
            malformed += 1
            continue
        pred = str(out.get("verdict", "")).strip()
        quote = str(out.get("verdict_quote", ""))
        if pred not in LABELS:
            malformed += 1
            continue
        # Same hallucination guard the production tool applies.
        if pred != "unclear" and _norm(quote) not in _norm(s["text"]):
            guard_rejected += 1
            continue
        per_truth[s["truth"]] += 1
        confusion[(s["truth"], pred)] += 1
        if pred == s["truth"]:
            correct += 1
        if i % 10 == 0:
            print(f"    {model} / {prompt_key}: {i}/{len(samples)}", flush=True)
        time.sleep(delay)

    scored = sum(per_truth.values())
    return {"model": model, "prompt": prompt_key, "n": len(samples),
            "scored": scored, "correct": correct,
            "accuracy": (correct / scored) if scored else 0.0,
            "guard_rejected": guard_rejected, "malformed": malformed,
            "seconds": round(time.time() - started, 1),
            "confusion": {f"{k[0]}->{k[1]}": v for k, v in sorted(confusion.items())}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--model", default="qwen2.5:14b")
    ap.add_argument("--prompt", default="v1", choices=list(PROMPTS))
    ap.add_argument("-n", "--samples", type=int, default=60)
    ap.add_argument("--delay", type=float, default=0.0)
    ap.add_argument("--sweep", action="store_true",
                    help="run every model x prompt combination")
    ap.add_argument("--models", nargs="*",
                    default=["qwen2.5:14b", "scb10x/llama3.1-typhoon2-8b-instruct:latest"])
    ap.add_argument("--max-chars", type=int, default=6000,
                    help="truncate article text; Thai tokenises densely so this "
                         "dominates latency")
    ap.add_argument("--stratified", action="store_true",
                    help="sample evenly per class instead of by natural frequency")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--out", default="data/eval")
    args = ap.parse_args()
    args.models_given = any(a == '--models' for a in sys.argv)

    if args.list_models:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=10) as r:
            for m in json.loads(r.read())["models"]:
                print(f"  {m['name']:50} {m.get('size',0)/1e9:.1f} GB")
        return 0

    samples = load_eval_set(args.db, args.samples, args.stratified, args.max_chars)
    print(f"eval set: {len(samples)} thaipbs articles with ClaimReview ground truth")
    print(f"truth distribution: {dict(Counter(s['truth'] for s in samples))}\n")

    # --models is honoured whenever it is given, not only under --sweep; the
    # earlier form silently ignored it and re-ran a single default model.
    if args.sweep:
        combos = [(m, p) for m in args.models for p in ("v1", "v2")]
    elif args.models_given:
        combos = [(m, args.prompt) for m in args.models]
    else:
        combos = [(args.model, args.prompt)]

    results = []
    for model, prompt_key in combos:
        print(f"--- {model}  prompt={prompt_key} ---", flush=True)
        res = run_combo(model, prompt_key, samples, args.delay)
        results.append(res)
        print(f"    accuracy {res['accuracy']:.1%} "
              f"({res['correct']}/{res['scored']} scored), "
              f"guard-rejected {res['guard_rejected']}, "
              f"malformed {res['malformed']}, {res['seconds']}s\n", flush=True)

    print("=" * 74)
    print(f"{'model':46} {'prompt':7} {'acc':>7} {'rej':>5}")
    for r in sorted(results, key=lambda x: -x["accuracy"]):
        print(f"{r['model']:46} {r['prompt']:7} {r['accuracy']:6.1%} {r['guard_rejected']:5}")

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = outdir / f"verdict_extraction_{stamp}.json"
    path.write_text(json.dumps(
        {"generated_at": stamp, "eval_set_size": len(samples),
         "truth_distribution": dict(Counter(s["truth"] for s in samples)),
         "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwritten: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
