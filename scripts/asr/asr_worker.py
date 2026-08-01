#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asr_worker.py — runs ON lighthouse-gpu01. Transcribes Sure & Share episodes and
extracts the verdict the presenter states aloud.

Why this exists
---------------
sure_share is 9,338 records of YouTube metadata with no native verdict: the
answer is spoken in the video and appears nowhere in the description. That left
~7,000 episodes unlabelled, and at the observed human rate (~6.6/day) the queue
was a three-year job. Whisper transcription was planned in 2026-07 and dropped
in favour of human labelling; it is revisited here because the labelling stalled.

Deliberate design choices
-------------------------
* **Only the tail of the audio is transcribed.** Sure & Share states its verdict
  in the closing seconds. Transcribing whole episodes costs ~5x more GPU time for
  material that is mostly the claim being restated, not the ruling.
* **Reads and writes JSONL, never the database.** The canonical DB lives on
  lighthouse-core and stays single-writer; this node produces artifacts that a
  separate, auditable step applies. Same separation the job system already uses.
* **Verbatim-quote guard**, as in llm_assist.py: the model must return a phrase
  that literally occurs in the transcript, or the record is rejected rather than
  labelled. A hallucinated verdict is far worse than a missing one.
* Transcript is always retained in the output so a human can audit any label
  without re-running the GPU.

Usage (on the GPU node)
-----------------------
    export LD_LIBRARY_PATH=$(find $PWD/.venv -name lib -path '*nvidia*' -type d | tr '\\n' ':')
    .venv/bin/python asr_worker.py --tasks tasks.jsonl --out results.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
VALID = {"false", "true", "misleading", "altered_media"}


def _tool(name: str) -> str:
    """Resolve a helper binary next to this interpreter before trusting PATH.

    yt-dlp is installed into the venv, and a non-interactive ssh session does not
    get the venv on PATH -- the first run of this worker failed all 50 tasks with
    'No such file or directory: yt-dlp' for exactly that reason.
    """
    local = Path(sys.executable).parent / name
    return str(local) if local.exists() else name


YTDLP = os.getenv("YTDLP") or _tool("yt-dlp")

# Prompt v2, chosen by measurement against the 115 human-labelled episodes.
# v1 scored 91% on false but only 20% on true: it downgraded a clear "จริง" to
# "misleading" whenever the host added a caveat, because it did not know the
# programme's own convention -- ชัวร์ก่อนแชร์ ends by telling viewers whether to
# share, and "แชร์ได้" IS the true verdict. Stating that lifted true to 100%,
# false to 97% and overall accuracy to 89.9%.
#
# A v3 that also tried to rescue "misleading" (43% here) regressed everything
# else to 74.7%, so v2 stands. Its residual weakness is calling some บิดเบือน
# "ปลอม" -- both are "do not share", so the direction is never reversed.
# See scripts/asr/asr_rescore.py to retry prompts against saved transcripts.
PROMPT = """ต่อไปนี้คือถอดเสียงช่วงท้ายของรายการ "ชัวร์ก่อนแชร์"
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


def fetch_tail_audio(url: str, seconds: int, workdir: Path) -> Path | None:
    """Download audio and keep only the closing `seconds`.

    yt-dlp writes the whole track; ffmpeg then trims from the end. Trimming
    server-side is not possible, but the download is small relative to the
    transcription cost so this is not the bottleneck.
    """
    raw = workdir / "a.mp3"
    trimmed = workdir / "tail.mp3"
    for p in (raw, trimmed):
        p.unlink(missing_ok=True)
    r = subprocess.run(
        [YTDLP, "-f", "bestaudio", "-x", "--audio-format", "mp3",
         "--audio-quality", "5", "--no-playlist", "--quiet", "--no-warnings",
         "-o", str(workdir / "a.%(ext)s"), url],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not raw.exists():
        return None
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(raw)], capture_output=True, text=True)
    try:
        total = float(dur.stdout.strip())
    except ValueError:
        return raw
    if total <= seconds:
        return raw
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(max(0, total - seconds)),
         "-i", str(raw), str(trimmed)], capture_output=True, timeout=120)
    return trimmed if trimmed.exists() else raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--tail-seconds", type=int, default=45)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    tasks = [json.loads(l) for l in args.tasks.read_text(encoding="utf-8").splitlines() if l.strip()]
    done = set()
    if args.out.exists():  # resumable: a 7,000-item run must survive interruption
        for line in args.out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["id"])
    tasks = [t for t in tasks if t["id"] not in done]
    if args.limit:
        tasks = tasks[: args.limit]
    print(f"{len(tasks)} to process ({len(done)} already done)", flush=True)

    from faster_whisper import WhisperModel
    t0 = time.time()
    model = WhisperModel(args.model, device="cuda", compute_type="float16")
    print(f"whisper {args.model} loaded in {time.time()-t0:.1f}s", flush=True)

    stats = {"labelled": 0, "unclear": 0, "rejected": 0, "unavailable": 0, "error": 0}
    with tempfile.TemporaryDirectory() as td, args.out.open("a", encoding="utf-8") as fh:
        workdir = Path(td)
        for i, t in enumerate(tasks, 1):
            rec = {"id": t["id"], "url": t["url"], "title": t["title"]}
            try:
                audio = fetch_tail_audio(t["url"], args.tail_seconds, workdir)
                if audio is None:
                    rec["status"] = "unavailable"
                    stats["unavailable"] += 1
                else:
                    segs, _ = model.transcribe(str(audio), language="th", beam_size=5)
                    transcript = " ".join(s.text.strip() for s in segs).strip()
                    rec["transcript"] = transcript
                    if len(transcript) < 40:
                        rec["status"] = "unclear"
                        stats["unclear"] += 1
                    else:
                        out = ollama(PROMPT.format(title=t["title"], transcript=transcript))
                        verdict = str(out.get("verdict", "")).strip()
                        quote = str(out.get("quote", ""))
                        rec["raw_verdict"], rec["quote"] = verdict, quote
                        if verdict not in VALID:
                            rec["status"] = "unclear"
                            stats["unclear"] += 1
                        elif norm(quote) not in norm(transcript):
                            rec["status"] = "rejected_quote_not_in_transcript"
                            stats["rejected"] += 1
                        else:
                            rec["status"] = "labelled"
                            rec["verdict"] = verdict
                            stats["labelled"] += 1
            except Exception as exc:
                rec["status"] = "error"
                rec["error"] = str(exc)[:200]
                stats["error"] += 1
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 5 == 0 or i == len(tasks):
                print(f"  {i}/{len(tasks)}  {stats}", flush=True)

    print(f"\ndone: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
