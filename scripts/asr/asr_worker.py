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
import shutil
import subprocess
import urllib.request
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
# Chosen by measurement, not reputation: benchmarked against the 105 records
# holding both a human verdict and a transcript (scripts/asr/bench_models.py).
#   qwen2.5:14b   59.0%   misleading 32.4%
#   qwen3.8:27b   66.7%   misleading 32.4%
#   typhoon-s-8b  67.6%   misleading 51.4%   <- this
#   pathumma-8b   64.8%   misleading 54.1%
# Both Thai 8B models beat both Qwen models by ~20 points on misleading, which
# is where the programme's three-way convention lives. Scale does not help: the
# 27B matched the 14B to the decimal. At 5GB this also fits beside whisper.
OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "hf.co/mradermacher/typhoon-s-thaillm-8b-instruct-research-preview-GGUF:Q4_K_M")
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
# The quote is capped at one short sentence, and that cap is load-bearing.
#
# Unconstrained, the model returned the WHOLE transcript as its "quote" -- median
# 470 characters. Two things went wrong with that. A reviewer cannot check a
# quote that is simply the transcript again, which defeats the point of showing
# one. And the verbatim-quote guard rejected 37% of records because a single
# stray character anywhere in 440 voids the match: one traced case reproduced
# 441 of 442 characters, then "corrected" Sureandshare to Sureandแชร์ at
# position 437.
#
# Measured on 150 RANDOM human-labelled records (2026-08-25), capped vs not:
#   true        75.0% -> 81.2%
#   false       79.5% -> 84.1%
#   misleading  59.5% -> 52.4%     <- the cost, and it is real
#   overall     72.0% -> 74.0%     median quote 470 -> 102 chars
#
# Adopted despite the misleading regression, on the reasoning that every record
# goes to a human in /review?mode=verify: a 102-character quote gets read and
# checked, a 470-character one does not. The cap likely improves what the HUMAN
# catches by more than it costs in what the model gets right unaided. The real
# fix for `misleading` is elsewhere anyway -- the closing tail does not contain
# the distinction, because the host says อย่าแชร์ for false and misleading
# alike; only the expert's early answer separates them (see HANDOFF, two-signal).
PROMPT = """ต่อไปนี้คือถอดเสียงช่วงท้ายของรายการ "ชัวร์ก่อนแชร์"
ผู้ดำเนินรายการจะสรุปผลการตรวจสอบและบอกผู้ชมว่าควรแชร์หรือไม่

หัวข้อของคลิป: {title}

ถอดเสียง:
{transcript}

ตอบเป็น JSON เท่านั้น:
{{"verdict": "false" | "true" | "misleading" | "altered_media" | "unclear", "quote": "ประโยคเดียวสั้น ๆ ไม่เกิน 120 ตัวอักษร คัดลอกตรงตัวจากถอดเสียง ซึ่งระบุผลสรุป"}}

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
- quote ต้องคัดลอกตรงตัวจากถอดเสียงเท่านั้น ห้ามแต่งขึ้นเอง
- quote ต้องสั้น ไม่เกิน 1 ประโยค (ไม่เกิน 120 ตัวอักษร) ห้ามคัดลอกทั้งถอดเสียง"""


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def ollama(prompt: str) -> dict:
    body = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
            # think=False is not optional. Typhoon-S is Qwen3-based and Ollama
            # enables reasoning by default; combined with format="json" the
            # response comes back EMPTY, which surfaces as a JSON decode error on
            # every single record. It cost a 25-record pilot to find, having
            # already been fixed once in bench_models.py and not carried across.
            "format": "json", "think": False,
            "options": {"temperature": 0, "num_predict": 512}}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(json.loads(r.read())["response"])


AUDIO_CACHE = Path(os.getenv("AUDIO_CACHE", "")) if os.getenv("AUDIO_CACHE") else None

# Skip captions with USE_CAPTIONS=0 to force the audio path (useful when
# comparing the two, or if YouTube's Thai ASR regresses).
USE_CAPTIONS = os.getenv("USE_CAPTIONS", "1") != "0"
_THAI = "\u0e00-\u0e7f"


def _despace(text: str) -> str:
    """YouTube's Thai ASR puts a space between syllables; Thai does not.

    Left in, every downstream string comparison sees different text for the same
    words -- including the verbatim-quote guard, which would then reject nearly
    everything the model quoted.
    """
    text = re.sub(r"\[[^\]]{0,20}\]", " ", text)          # [เพลง], [ดนตรี]
    text = re.sub(f"(?<=[{_THAI}]) (?=[{_THAI}])", "", text)
    return re.sub(r"\s+", " ", text).strip()


class CaptionsRateLimited(RuntimeError):
    """YouTube returned 429 for the caption text.

    Distinguished from "this video has no Thai captions" because the responses
    are opposite instructions: no captions means fall back to audio, 429 means
    stop and come back later, or fetch from a machine whose IP is not burnt.
    An earlier version returned None for both and a rate-limited batch looked
    exactly like a batch of videos without subtitles.
    """


def fetch_tail_captions(url: str, seconds: int) -> str | None:
    """The closing `seconds` of the Thai auto-captions, or None if there are none.

    Tried before downloading anything. The download is this pipeline's expensive
    and fragile half -- half of 1,858 attempts failed to throttling on
    2026-08-17 -- while captions are a light request that succeeded on every
    video whose audio had 403'd. Measured on 32 records with both a human
    verdict and a whisper transcript, caption text scored 81.2% against
    whisper's 75.0%, so this costs no accuracy.

    Only the TAIL, deliberately. Passing the whole programme scored 68.8% on the
    same records: the verdict statement gets diluted among everything else said.
    """
    try:
        import yt_dlp
    except ImportError:
        return None
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True,
                               "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        auto = info.get("automatic_captions") or {}
        track = auto.get("th") or auto.get("th-orig")
        if not track:
            return None
        j3 = next((x for x in track if x.get("ext") == "json3"), track[0])
        data = json.loads(urllib.request.urlopen(j3["url"], timeout=40).read())
        dur = info.get("duration") or 0
        events = [e for e in data.get("events", []) if e.get("segs")]
        tail = [e for e in events
                if (e.get("tStartMs", 0) / 1000) >= max(0, dur - seconds)]
        text = _despace(" ".join(s.get("utf8", "") for e in tail for s in e["segs"]))
        return text or None
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise CaptionsRateLimited(url) from None
        return None
    except Exception:
        return None


def fetch_tail_audio(url: str, seconds: int, workdir: Path,
                     cache_key: str | None = None) -> Path | None:
    """Download audio and keep only the closing `seconds`.

    yt-dlp writes the whole track; ffmpeg then trims from the end. Trimming
    server-side is not possible.

    Set AUDIO_CACHE to keep the trimmed clip. The download is the unreliable and
    slow half of this pipeline -- roughly half of 105 attempts failed on
    2026-08-17 -- and without a cache every experiment re-downloads everything.
    That is what made comparing two ASR models impossible: the baseline
    transcripts were six weeks old, the challenger's had to be re-fetched, and
    half the audio would not come down. A few GB of mp3 buys repeatable
    experiments and takes YouTube off the critical path.
    """
    if AUDIO_CACHE and cache_key:
        cached = AUDIO_CACHE / f"{cache_key}.mp3"
        if cached.exists():
            return cached
    raw = workdir / "a.mp3"
    trimmed = workdir / "tail.mp3"
    for p in (raw, trimmed):
        p.unlink(missing_ok=True)
    r = subprocess.run(
        # --js-runtimes node: YouTube needs JS to decipher some stream formats and
        # yt-dlp only enables deno by default, so without this it warns and then
        # fails a share of downloads outright. Node 22 is installed on the GPU box.
        [YTDLP, "--js-runtimes", "node",
         "-f", "bestaudio", "-x", "--audio-format", "mp3",
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
    if AUDIO_CACHE and cache_key and trimmed.exists():
        AUDIO_CACHE.mkdir(parents=True, exist_ok=True)
        shutil.copy2(trimmed, AUDIO_CACHE / f"{cache_key}.mp3")
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

    # Whisper is loaded on first use, not up front. When captions cover the whole
    # batch -- which they do for 2022+ material -- the GPU is never touched at
    # all, so this can run on a machine without one.
    model = None

    def whisper():
        nonlocal model
        if model is None:
            from faster_whisper import WhisperModel
            t0 = time.time()
            model = WhisperModel(args.model, device="cuda", compute_type="float16")
            print(f"whisper {args.model} loaded in {time.time()-t0:.1f}s", flush=True)
        return model

    global USE_CAPTIONS
    stats = {"labelled": 0, "unclear": 0, "rejected": 0, "unavailable": 0, "error": 0}
    with tempfile.TemporaryDirectory() as td, args.out.open("a", encoding="utf-8") as fh:
        workdir = Path(td)
        for i, t in enumerate(tasks, 1):
            rec = {"id": t["id"], "url": t["url"], "title": t["title"]}
            try:
                transcript = None
                if USE_CAPTIONS:
                    try:
                        transcript = fetch_tail_captions(t["url"], args.tail_seconds)
                    except CaptionsRateLimited:
                        # Loud, and only once: every later record would 429 too,
                        # and a run that silently downgraded to audio would look
                        # like the captions simply were not there.
                        if USE_CAPTIONS:
                            print("  captions rate-limited (429) from this host --"
                                  " falling back to audio for the rest of the run",
                                  flush=True)
                        USE_CAPTIONS = False
                    if transcript:
                        rec["transcript_source"] = "captions"
                if transcript is None:
                    audio = fetch_tail_audio(t["url"], args.tail_seconds, workdir,
                                             cache_key=str(t.get("id") or ""))
                    if audio is None:
                        rec["status"] = "unavailable"
                        stats["unavailable"] += 1
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
                        if i % 5 == 0:
                            print(f"  {i}/{len(tasks)}  {stats}", flush=True)
                        continue
                    segs, _ = whisper().transcribe(str(audio), language="th", beam_size=5)
                    transcript = " ".join(s.text.strip() for s in segs).strip()
                    rec["transcript_source"] = "whisper"
                if True:
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
