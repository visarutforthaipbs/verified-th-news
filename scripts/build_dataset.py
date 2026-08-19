"""Build train-ready datasets from data/th_verify.db.

Pipeline:
  1. Normalize the ~30 raw verdict strings into one taxonomy.
  2. Recover missing verdicts for cofact/thaipbs from article text (rule-based).
  3. Strip verdict-bearing title prefixes/suffixes to produce leak-free claim_text.
  4. Deduplicate on normalized claim text (keeps the earliest record).
  5. Export:
       data/exports/verdict_mapping.csv        raw -> normalized mapping with counts
       data/exports/classification_train.jsonl time split: published <= 2024-12-31
       data/exports/classification_val.jsonl   2025-01-01 .. 2025-06-30
       data/exports/classification_test.jsonl  2025-07-01 onward
       data/exports/rag_corpus.jsonl           all records incl. unlabeled, full text
       data/exports/REPORT.md                  summary statistics

Usage: python scripts/build_dataset.py [--db data/th_verify.db]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import unicodedata
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "src"))
from th_verify.normalized import (clean_claim_text, is_factcheck,
                                  has_inline_leak as _has_inline_leak)  # noqa: E402
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. Verdict taxonomy
#
# Labels:
#   false          - fabricated / untrue claim
#   true           - claim verified as true
#   misleading     - distorted, partly false, or missing context
#   altered_media  - doctored image/video or AI-generated media
#   satire         - satire mistaken for news
#   scam_alert     - warning about an active scam/phishing (not a claim verdict)
#   unknown        - no verdict available
# ---------------------------------------------------------------------------

VERDICT_MAP: dict[tuple[str, str], str] = {
    # --- afnc ---
    ("afnc", "ข่าวปลอม"): "false",
    ("afnc", "ข่าวจริง"): "true",
    ("afnc", "ข่าวบิดเบือน"): "misleading",
    ("afnc", "อาชญากรรมออนไลน์"): "scam_alert",
    # editorial/announcement content, not verdicts -> excluded from classification
    ("afnc", "คลังความรู้"): "unknown",
    ("afnc", "ข่าวอื่นๆ"): "unknown",
    ("afnc", "กิจกรรม"): "unknown",
    ("afnc", "ข่าวสาร"): "unknown",
    ("afnc", "นโยบายรัฐบาล-ข่าวสาร"): "unknown",
    ("afnc", "ผลิตภัณฑ์สุขภาพ"): "unknown",
    ("afnc", "ความสงบและความมั่นคง"): "unknown",
    ("afnc", "ยาเสพติด"): "unknown",
    ("afnc", "ภัยพิบัติ"): "unknown",
    ("afnc", "การเงิน-หุ้น"): "unknown",
    ("afnc", "unknown"): "unknown",
    # --- afp (case-folded before lookup) ---
    ("afp", "false"): "false",
    ("afp", "flase"): "false",  # source typo
    ("afp", "ปลอม"): "false",
    ("afp", "misleading"): "misleading",
    ("afp", "เข้าใจผิด"): "misleading",
    ("afp", "missing context"): "misleading",
    ("afp", "partly false"): "misleading",
    ("afp", "party false"): "misleading",  # source typo
    ("afp", "altered image"): "altered_media",
    ("afp", "doctored image"): "altered_media",
    ("afp", "ดัดแปลงภาพ"): "altered_media",
    ("afp", "ดัดแปลงวิดีโอ"): "altered_media",
    ("afp", "สร้างขึ้นโดยปัญญาประดิษฐ์"): "altered_media",
    ("afp", "satire"): "satire",
    ("afp", "1"): "unknown",  # source junk values
    ("afp", "varia"): "unknown",
    # --- cofact ---
    ("cofact", "ข่าวปลอม"): "false",
    ("cofact", "ข่าวจริง"): "true",
    ("cofact", "ข่าวบิดเบือน"): "misleading",
    ("cofact", "เนื้อหาเป็นเท็จ"): "false",
    ("cofact", "เนื้อหาเป็นจริง"): "true",
    ("cofact", "เนื้อหาที่ทำให้เข้าใจผิด"): "misleading",
    ("cofact", "unknown"): "unknown",
    # --- thaipbs ---
    ("thaipbs", "ข่าวปลอม"): "false",
    ("thaipbs", "ข่าวจริง"): "true",
    ("thaipbs", "ข่าวบิดเบือน"): "misleading",
    ("thaipbs", "ภาพปลอม"): "altered_media",
    ("thaipbs", "unknown"): "unknown",
    # Thai PBS also ships these two in ClaimReview.reviewRating.alternateName.
    # Neither is a verdict on the claim: "ไม่สแตมป์ข่าว" is an explicit refusal to
    # stamp one, and "ตรวจสอบแล้ว" only asserts that a check happened. They are
    # mapped to unknown deliberately rather than left to fall through, so that a
    # future reader can see the choice was made rather than missed. Do not guess a
    # polarity for them -- that would put invented labels in the gold tier.
    ("thaipbs", "ไม่สแตมป์ข่าว"): "unknown",
    ("thaipbs", "ตรวจสอบแล้ว"): "unknown",
    # --- sure_share: YouTube metadata, no verdicts ---
    ("sure_share", "unknown"): "unknown",
}


_NORMALIZED = {"false", "true", "misleading", "altered_media", "satire", "scam_alert"}


def normalize_verdict(source: str, raw: str) -> str:
    raw = raw.strip()
    if raw in _NORMALIZED:  # already-normalized label (e.g. human review UI)
        return raw
    key = (source, raw.lower() if source == "afp" else raw)
    return VERDICT_MAP.get(key, "unknown")


# ---------------------------------------------------------------------------
# 2. Verdict recovery for records the collectors left as 'unknown'
# ---------------------------------------------------------------------------

# cofact articles embed a structured verdict block, e.g.
#   "❌ ผลการตรวจสอบข้อเท็จจริง: **เนื้อหาเท็จ** ..."
COFACT_VERDICT_RE = re.compile(
    r"ผลการตรวจสอบ(?:ข้อเท็จจริง)?\s*[:：]?\s*\**\s*([^*\n]{1,80})"
)

# ordered: first match wins
_VERDICT_SPAN_RULES: list[tuple[str, list[str]]] = [
    ("misleading", ["ทำให้เข้าใจผิด", "บิดเบือน", "เข้าใจผิด", "มีทั้งจริงและเท็จ",
                    "จริงบางส่วน", "ขาดบริบท", "คลาดเคลื่อน"]),
    ("false", ["เท็จ", "ไม่จริง", "ข่าวปลอม", "ไม่เป็นความจริง", "หลอกลวง"]),
    ("true", ["เป็นจริง", "ข่าวจริง", "เป็นความจริง"]),
]


def _classify_span(span: str) -> str | None:
    for label, needles in _VERDICT_SPAN_RULES:
        if any(n in span for n in needles):
            return label
    return None


def recover_cofact_verdict(explanation: str) -> str | None:
    m = COFACT_VERDICT_RE.search(explanation)
    if m:
        label = _classify_span(m.group(1))
        if label:
            return label
    # fall back to the emoji immediately before the verdict block
    head = explanation[:3000]
    if "❌ ผลการตรวจสอบ" in head:
        return "false"
    if "✅ ผลการตรวจสอบ" in head:
        return "true"
    return None


# thaipbs verdicts are phrased inside the headline
_THAIPBS_TITLE_RULES: list[tuple[str, list[str]]] = [
    ("altered_media", ["สร้างจาก AI", "ปลอมจาก AI", "สร้างด้วย AI", "คลิปปลอม",
                       "ภาพปลอม", "จากเกม", "ตัดต่อ", "เอไอ"]),
    ("false", ["ข่าวปลอม", "ไม่ใช่เหตุการณ์", "ไม่เกี่ยวข้อง", "แอบอ้าง",
               "เพจปลอม", "หลอก", "อ้างเป็น", "ที่แท้เป็น", "แท้จริงเป็น",
               "แท้จริงคือ"]),
    ("true", ["เป็นคลิปจริง", "เป็นภาพจริง", "ข่าวจริง", "เรื่องจริง"]),
]


def recover_thaipbs_verdict(title: str) -> str | None:
    for label, needles in _THAIPBS_TITLE_RULES:
        if any(n in title for n in needles):
            return label
    return None


# thaipbs stores the publish date only inside the article text, in Thai
# Buddhist-era short form, e.g. "Date 10 ก.ค. 69"
_TH_MONTHS = {
    "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
    "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12,
}
_THAIPBS_DATE_RE = re.compile(
    r"Date\s+(\d{1,2})\s+(ม\.ค\.|ก\.พ\.|มี\.ค\.|เม\.ย\.|พ\.ค\.|มิ\.ย\.|"
    r"ก\.ค\.|ส\.ค\.|ก\.ย\.|ต\.ค\.|พ\.ย\.|ธ\.ค\.)\s+(\d{2})"
)


def recover_thaipbs_date(explanation: str) -> str | None:
    m = _THAIPBS_DATE_RE.search(explanation)
    if not m:
        return None
    day, month, yy = int(m.group(1)), _TH_MONTHS[m.group(2)], int(m.group(3))
    year = 2500 + yy - 543  # BE short year -> CE (e.g. 69 -> 2569 -> 2026)
    return f"{year:04d}-{month:02d}-{day:02d}"


# ---------------------------------------------------------------------------
# 3. Claim cleaning: strip verdict-bearing prefixes/suffixes (leakage removal)
# ---------------------------------------------------------------------------

_PREFIX_RES = [
    # afnc / thaipbs verdict prefixes
    re.compile(r"^ข่าวปลอม\s*[,!:]?\s*(อย่าแชร์|อย่าเชื่อ)?\s*[!:]*\s*"),
    re.compile(r"^ข่าวบิดเบือน\s*[,!:]?\s*(อย่าแชร์)?\s*[!:]*\s*"),
    re.compile(r"^ข่าวจริง\s*[,!:?]?\s*"),
    re.compile(r"^(ภาพปลอม|คลิปปลอม|ข่าวเตือนภัย|เตือนภัย)\s*[,!:]?\s*"),
    # Thai PBS prefixes 117 headlines with "ตรวจสอบแล้ว" ("we checked this:").
    # It is boilerplate, not a verdict -- those same records carry badges of
    # ข่าวปลอม (93), ข่าวบิดเบือน (12) and ข่าวจริง (9), so the phrase says only
    # that a check happened. Left in place it rides into claim_text, the
    # classification exports and the search index, where it is a marker that a
    # fact-check exists rather than part of the claim anybody actually made.
    re.compile(r"^ตรวจสอบแล้ว\s*[:：]?\s*"),
    # sure_share episode branding
    re.compile(r"^ชัวร์ก่อนแชร์\s*[A-Za-z\- ]*\s*[:|]\s*"),
    re.compile(r"^\[?REPLAY\]?\s*.{0,3}ชัวร์ก่อนแชร์[^:|]*[:|]\s*"),
]

# question/verdict suffixes that flag the claim as being under review
_SUFFIX_RES = [
    re.compile(r"\s*(จริงหรือ|จริงหรือไม่|จริงไหม|ใช่หรือไม่)\s*[?？!]*\s*$"),
    re.compile(r"\s*(แท้จริง(?:เป็น|คือ|สร้างจาก)[^,]{0,80})$"),
    # Conclusion clauses tacked onto a headline. Thai PBS in particular writes
    # "<the claim> ที่แท้สร้างจาก AI" or "<the claim> ตรวจสอบพบเป็นคลิปเก่า", which
    # states the answer. 133 records still carried one after prefix stripping.
    # Only trailing clauses are removed -- a claim that merely mentions AI in the
    # middle ("คลิป AI ของนายกฯ") is left alone.
    re.compile(r"\s*[-–—,]?\s*(ที่แท้|แท้จริง)(?:เป็น|คือ|จริง|สร้างจาก|แล้ว)?[^,]{0,60}$"),
    re.compile(r"\s*[-–—,]?\s*(ตรวจสอบ(?:แล้ว)?พบ|พบ)(?:เป็น|ว่าเป็น)?\s*(?:ภาพ|คลิป|ข่าว)?[^,]{0,50}$"),
    re.compile(r"\s*[-–—,]?\s*สร้าง(?:ขึ้น)?(?:ด้วย|จาก)\s*(?:AI|เอไอ|ปัญญาประดิษฐ์)[^,]{0,40}$", re.IGNORECASE),
]


# One implementation, imported. These rules previously existed in full here AND
# in normalized.py; they were still identical, but two copies of the same filter
# is how the build_dataset.py fossil at the repo root came about -- one gets
# edited, the other silently keeps producing month-old output.
clean_claim = clean_claim_text

# Imported for the same reason as clean_claim: one implementation, not two.
has_inline_leak = _has_inline_leak


def dedup_key(claim: str) -> str:
    """Aggressive normalization for duplicate detection."""
    t = unicodedata.normalize("NFC", claim).lower()
    t = re.sub(r"[\s​]+", "", t)
    t = re.sub(r"[^\wก-๙]+", "", t)
    return t


# ---------------------------------------------------------------------------
# 4/5. Build + export
# ---------------------------------------------------------------------------

TRAIN_END = "2024-12-31"
VAL_END = "2025-06-30"

CLASSIFICATION_LABELS = {"false", "true", "misleading", "altered_media",
                         "satire", "scam_alert"}


def split_for(date: str | None) -> str:
    if not date:
        return "train"  # undated records can't leak future info into test
    d = date[:10]
    if d <= TRAIN_END:
        return "train"
    if d <= VAL_END:
        return "val"
    return "test"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--out", default="data/exports")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT id, source, source_url, title, claim, claim_origin, explanation, verdict,"
        "       category, published_at, verdict_origin FROM fact_checks"
        "       ORDER BY COALESCE(published_at, '9999') ASC, id ASC"
    ).fetchall()

    raw_counts: Counter[tuple[str, str]] = Counter()
    recovered = Counter()
    records = []
    for r in rows:
        source, raw_verdict = r["source"], r["verdict"]
        raw_counts[(source, raw_verdict)] += 1
        label = normalize_verdict(source, raw_verdict)
        db_origin = r["verdict_origin"] or ""
        if label == "unknown":
            label_origin = ""
        elif db_origin in ("human", "heuristic", "llm"):
            label_origin = db_origin
        else:
            label_origin = "native"
        published = r["published_at"] or None

        if label == "unknown":
            if source == "cofact":
                rec = recover_cofact_verdict(r["explanation"])
                if rec:
                    label, label_origin = rec, "recovered_text"
            elif source == "thaipbs":
                rec = recover_thaipbs_verdict(r["title"])
                if rec:
                    label, label_origin = rec, "recovered_title"
        if source == "thaipbs" and not published:
            published = recover_thaipbs_date(r["explanation"])
        if label_origin.startswith("recovered"):
            recovered[(source, label)] += 1

        # Prefer a claim somebody or something actually derived over a headline
        # we cleaned with regexes. claim_origin says which rows have one:
        # 'source' is the publisher's own claimReviewed, 'human' a reviewer's
        # correction, 'llm' an extraction that passed the guards. The rest are
        # still copies of the title and go through clean_claim as before.
        #
        # This used to read `if source == "afp"`, from when AFP was the only
        # source with a real claim field. That stayed true until 1,246 Thai PBS
        # and Cofact claims were extracted -- and because the rule named a
        # source instead of asking about provenance, every one of them would
        # have been dropped here and never reached the corpus or the index.
        if (r["claim_origin"] or "") in ("source", "human", "llm") and r["claim"].strip():
            claim_text = r["claim"].strip()
        else:
            claim_text = clean_claim(r["title"], source)

        records.append({
            "id": r["id"],
            "source": source,
            "url": r["source_url"],
            "claim_text": claim_text,
            "title_raw": r["title"],
            "explanation": r["explanation"],
            "label": label,
            "label_origin": label_origin or "none",
            "verdict_raw": r["verdict"],
            "verdict_origin_raw": r["verdict_origin"],
            "category": r["category"],
            "published_at": published,
        })

    # -- dedup: keep earliest occurrence of each normalized claim ------------
    seen: dict[str, int] = {}
    dup_groups: defaultdict[str, int] = defaultdict(int)
    for rec in records:
        key = dedup_key(rec["claim_text"])
        if not key:
            rec["is_duplicate"] = False
            continue
        if key in seen:
            rec["is_duplicate"] = True
            dup_groups[key] += 1
        else:
            seen[key] = rec["id"]
            rec["is_duplicate"] = False

    # -- exports --------------------------------------------------------------
    with open(out / "verdict_mapping.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "raw_verdict", "normalized_label", "count"])
        for (source, raw), n in sorted(raw_counts.items()):
            w.writerow([source, raw, normalize_verdict(source, raw), n])

    splits: defaultdict[str, list[dict]] = defaultdict(list)
    for rec in records:
        if rec["label"] in CLASSIFICATION_LABELS and not rec["is_duplicate"] \
                and len(rec["claim_text"]) >= 15 \
                and not has_inline_leak(rec["claim_text"]):
            splits[split_for(rec["published_at"])].append(rec)

    cls_fields = ["id", "source", "url", "claim_text", "label", "label_origin",
                  "category", "published_at"]
    for name, items in splits.items():
        with open(out / f"classification_{name}.jsonl", "w") as f:
            for rec in items:
                f.write(json.dumps({k: rec[k] for k in cls_fields},
                                   ensure_ascii=False) + "\n")

    # The RAG corpus is what /check searches, so it must contain only things a
    # user could sensibly be told about. Unlabelled claims stay -- "we have this
    # on file, not yet rated" is a useful answer. Articles, event notices and
    # roundups do not: they outrank real fact-checks in the results and surface
    # with label "unknown", which tells the reader nothing.
    #
    # Observed before this filter: searching "เรียนฟรีถึงปริญญาเอก" returned a
    # Thai PBS policy explainer at 0.873 in FIRST place -- above the actual
    # relevant fact-check at 0.857. Thai PBS themselves rate that record
    # "ไม่สแตมป์ข่าว", i.e. they decline to stamp a verdict on it.
    n_nonclaim = 0
    with open(out / "rag_corpus.jsonl", "w") as f:
        for rec in records:
            if rec["is_duplicate"]:
                continue
            if not is_factcheck(rec["source"], rec["title_raw"],
                                rec.get("verdict_raw", ""), rec["explanation"],
                                rec.get("verdict_origin_raw", "")):
                n_nonclaim += 1
                continue
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"rag_corpus: excluded {n_nonclaim} non-claim records")

    # -- report ---------------------------------------------------------------
    label_counts = Counter(r["label"] for r in records if not r["is_duplicate"])
    n_dupes = sum(1 for r in records if r["is_duplicate"])
    lines = [
        "# th_verify dataset build report", "",
        f"Total records: {len(records)}  |  duplicates removed: {n_dupes}", "",
        "## Normalized label distribution (deduped)", "",
        "| label | count |", "|---|---|",
        *[f"| {k} | {v} |" for k, v in label_counts.most_common()],
        "", "## Recovered labels (rule-based)", "",
        "| source | label | count |", "|---|---|---|",
        *[f"| {s} | {l} | {n} |" for (s, l), n in sorted(recovered.items())],
        "", "## Classification splits (labeled, deduped, leak-stripped)", "",
        "| split | records | window |", "|---|---|---|",
        f"| train | {len(splits['train'])} | <= {TRAIN_END} |",
        f"| val | {len(splits['val'])} | {TRAIN_END} .. {VAL_END} |",
        f"| test | {len(splits['test'])} | > {VAL_END} |",
        "",
    ]
    for name in ("train", "val", "test"):
        c = Counter(r["label"] for r in splits[name])
        lines += [f"### {name} label balance", "",
                  "| label | count |", "|---|---|",
                  *[f"| {k} | {v} |" for k, v in c.most_common()], ""]

    # -- insight sections -----------------------------------------------------
    live = [r for r in records if not r["is_duplicate"]]

    def year_of(r: dict) -> str | None:
        return r["published_at"][:4] if r["published_at"] else None

    years = sorted({y for r in live if (y := year_of(r))})
    cat_year: defaultdict[str, Counter] = defaultdict(Counter)
    for r in live:
        if r["source"] == "afnc" and r["category"] and year_of(r):
            cat_year[r["category"]][year_of(r)] += 1
    top_cats = sorted(cat_year, key=lambda c: -sum(cat_year[c].values()))[:6]
    lines += ["## AFNC fact-checks by category and year (deduped)", "",
              "| category | " + " | ".join(years) + " | total |",
              "|---" * (len(years) + 2) + "|"]
    for cat in top_cats:
        row = [str(cat_year[cat].get(y, 0)) for y in years]
        lines.append(f"| {cat} | " + " | ".join(row)
                     + f" | {sum(cat_year[cat].values())} |")
    lines.append("")

    ai_rx = re.compile(r"AI|เอไอ|ปัญญาประดิษฐ์|deepfake|ดีพเฟค", re.IGNORECASE)
    ai_year = Counter(y for r in live
                      if ai_rx.search(r["title_raw"]) and (y := year_of(r)))
    lines += ["## AI-generated-content mentions per year", "",
              "| year | mentions |", "|---|---|",
              *[f"| {y} | {ai_year[y]} |" for y in years if ai_year.get(y)], ""]

    scam_topics = {
        "health cures / disease claims": re.compile(r"รักษา|โรค|มะเร็ง|สมุนไพร"),
        "investment schemes": re.compile(r"ลงทุน|หุ้น|ปันผล|ผลตอบแทน"),
        "loans / credit": re.compile(r"เงินกู้|สินเชื่อ|กู้เงิน"),
        "malicious apps / links": re.compile(r"แอปพลิเคชัน|ลิงก์|ดาวน์โหลด"),
        "govt / bank impersonation": re.compile(r"ธนาคาร|กระทรวง|กรม|เพจปลอม|แอบอ้าง"),
    }
    lines += ["## Recurring fake-claim topics (label=false, deduped)", "",
              "| topic | claims |", "|---|---|"]
    fakes = [r for r in live if r["label"] == "false"]
    for topic, rx in scam_topics.items():
        n = sum(1 for r in fakes if rx.search(r["claim_text"]))
        lines.append(f"| {topic} | {n} |")
    lines.append("")

    (out / "REPORT.md").write_text("\n".join(lines))

    print(f"records={len(records)} dupes_removed={n_dupes}")
    print(f"labels={dict(label_counts)}")
    print(f"recovered={dict(recovered)}")
    print({k: len(v) for k, v in splits.items()})
    print(f"exports written to {out}/")


if __name__ == "__main__":
    main()
