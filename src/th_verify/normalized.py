# -*- coding: utf-8 -*-
"""
normalized.py — Non-destructive normalization & high-precision topic classification layer.
Provides leak-free, standardized atomic claims and precise topic assignments
without modifying raw tables.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Generator, Any

# ---------------------------------------------------------------------------
# 1. Standardized Verdict Mapping
# ---------------------------------------------------------------------------

VERDICT_MAP: dict[tuple[str, str], str] = {
    # --- afnc ---
    ("afnc", "ข่าวปลอม"): "false",
    ("afnc", "ข่าวจริง"): "true",
    ("afnc", "ข่าวบิดเบือน"): "misleading",
    ("afnc", "อาชญากรรมออนไลน์"): "scam_alert",
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
    # --- afp (case-folded) ---
    ("afp", "false"): "false",
    ("afp", "flase"): "false",
    ("afp", "ปลอม"): "false",
    ("afp", "misleading"): "misleading",
    ("afp", "เข้าใจผิด"): "misleading",
    ("afp", "missing context"): "misleading",
    ("afp", "partly false"): "misleading",
    ("afp", "party false"): "misleading",
    ("afp", "altered image"): "altered_media",
    ("afp", "doctored image"): "altered_media",
    ("afp", "ดัดแปลงภาพ"): "altered_media",
    ("afp", "ดัดแปลงวิดีโอ"): "altered_media",
    ("afp", "สร้างขึ้นโดยปัญญาประดิษฐ์"): "altered_media",
    ("afp", "satire"): "satire",
    ("afp", "1"): "unknown",
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
    # Thai PBS Verify's own stamp taxonomy, taken from ClaimReview
    # reviewRating.alternateName. Six values, all of them recorded here so a
    # reader can see the whole vocabulary rather than discover it by a miss.
    # /verify/category/* are TOPIC categories (politics, environment, world-news)
    # and carry no verdict -- do not confuse the two.
    ("thaipbs", "ข่าวปลอม"): "false",
    ("thaipbs", "ข่าวจริง"): "true",
    ("thaipbs", "ข่าวบิดเบือน"): "misleading",
    ("thaipbs", "ภาพปลอม"): "altered_media",
    # The two non-polar stamps. Neither states whether the claim is true, so
    # neither can become a training label -- but they are real editorial
    # outcomes, not missing data, and mapping them to unknown is a decision
    # recorded here rather than an accident of a lookup failing.
    #   ไม่สแตมป์ข่าว  - examined, and Thai PBS declines to stamp a verdict
    #   ตรวจสอบแล้ว    - a check was performed; used as a catch-all badge
    ("thaipbs", "ไม่สแตมป์ข่าว"): "unknown",
    ("thaipbs", "ตรวจสอบแล้ว"): "unknown",
    ("thaipbs", "unknown"): "unknown",
    # --- sure_share ---
    ("sure_share", "unknown"): "unknown",
    ("sure_share", "false"): "false",
    ("sure_share", "true"): "true",
    ("sure_share", "misleading"): "misleading",
    ("sure_share", "ข่าวปลอม"): "false",
    ("sure_share", "ข่าวจริง"): "true",
    ("sure_share", "ข่าวบิดเบือน"): "misleading",
}

_NORMALIZED = {"false", "true", "misleading", "altered_media", "satire", "scam_alert"}

def normalize_verdict(source: str, raw_verdict: str) -> str:
    raw = (raw_verdict or "").strip()
    if raw in _NORMALIZED:
        return raw
    key = (source, raw.lower() if source == "afp" else raw)
    return VERDICT_MAP.get(key, "unknown")

# ---------------------------------------------------------------------------
# 2. Boilerplate Affixes & Leakage Stripping
# ---------------------------------------------------------------------------

_PREFIX_RES = [
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
    re.compile(r"^ชัวร์ก่อนแชร์\s*[A-Za-z\- ]*\s*[:|]\s*"),
    re.compile(r"^\[?REPLAY\]?\s*.{0,3}ชัวร์ก่อนแชร์[^:|]*[:|]\s*"),
    re.compile(r"^ศูนย์ต่อต้านข่าวปลอม\s*(?:ตรวจสอบพบว่า)?\s*[:|]\s*"),
]

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

def clean_claim_text(title: str, source: str) -> str:
    text = unicodedata.normalize("NFC", title or "").strip()
    changed = True
    while changed:
        changed = False
        for rx in _PREFIX_RES:
            new = rx.sub("", text)
            if new != text:
                text, changed = new, True
    for rx in _SUFFIX_RES:
        text = rx.sub("", text)
    return text.strip(" -–—|:!?")

_INLINE_LEAK_RE = re.compile(
    r"เป็นข่าวปลอม|ตรวจสอบแล้ว|ไม่เป็นความจริง|แท้จริง(?:เป็น|คือ|สร้าง)|"
    r"ข่าวปลอม|เป็นเรื่องจริง|ยืนยันว่าจริง"
)

def has_inline_leak(text: str) -> bool:
    return bool(_INLINE_LEAK_RE.search(text))

# ---------------------------------------------------------------------------
# 3. High-Precision Thai Topic Classifier Rules (Avoid Substring False Positives)
# ---------------------------------------------------------------------------

HIGH_PRECISION_TOPIC_RULES = [
    ("T07", "AI Deepfake & สื่อตัดต่อ", "#38bdf8", re.compile(r"deepfake|ดีพเฟก|สร้างจาก\s*ai|สร้างด้วย\s*ai|ปัญญาประดิษฐ์|เสียงสังเคราะห์|คลิป\s*ai|ภาพ\s*ai|เทคโนโลยี\s*ai", re.IGNORECASE)),
    ("T02", "โควิด-19 และวัคซีน", "#f59e0b", re.compile(r"โควิด|covid|วัคซีนโควิด|ฉีดวัคซีน|โอไมครอน|เดลตา|atk\b|swab|ฟ้าทะลายโจร.*โควิด", re.IGNORECASE)),
    ("T04", "หลอกลงทุนหุ้น & SET", "#a855f7", re.compile(r"ตลาดหลักทรัพย์|set\b|หลอกลงทุน|เทรดหุ้น|กองทุนทองคำ|ปันผล\s*รายวัน|ผลตอบแทน\s*สูง|เปิดพอร์ต|คริปโต|forex|บิตคอยน์", re.IGNORECASE)),
    ("T03", "สินเชื่อปลอม & คอลเซ็นเตอร์", "#f43f5e", re.compile(r"เงินกู้|สินเชื่อ|กู้เงิน|ดอกเบี้ยต่ำ|คอลเซ็นเตอร์|ดูดเงิน|โอนเงิน|แอดไลน์.*เงิน|แอปดูดเงิน|ลิงก์ปลอม|บัญชีม้า|ธนาคารออมสิน|ธ\.กรุงไทย|ปปง\.|ตำรวจสอบสวนกลาง|cib\b", re.IGNORECASE)),
    ("T06", "แรงงานต่างด้าว & สัญชาติ", "#fb923c", re.compile(r"แรงงานต่างด้าว|ต่างด้าว|ชาวพม่า|ชาวกัมพูชา|ชาวลาว|ชาวเวียดนาม|โรฮิงญา|แย่งอาชีพคนไทย|สัญชาติไทย|แจกสัญชาติ|บัตรประชาชนต่างด้าว|เกาะกูด|mou\s*44", re.IGNORECASE)),
    ("T08", "ภัยพิบัติ & สภาพอากาศ", "#94a3b8", re.compile(r"กรมอุตุนิยมวิทยา|พยากรณ์อากาศ|สภาพอากาศ|ฝนตกหนัก|พายุ|น้ำท่วม|แผ่นดินไหว|สึนามิ|เขื่อนแตก|อุณหภูมิลด", re.IGNORECASE)),
    ("T09", "การเมือง & การเลือกตั้ง", "#6366f1", re.compile(r"การเมือง|เลือกตั้ง|กกต\.|นายกรัฐมนตรี|พรรคการเมือง|พรรคเพื่อไทย|พรรคก้าวไกล|พรรคประชาชน|พรรคประชาธิปัตย์|พรรคพลังประชารัฐ|พรรครวมไทยสร้างชาติ|สภาผู้แทน|รัฐสภา|อภิปรายไม่ไว้วางใจ|ยุบสภา|ม\.112|มาตรา\s*112|ม็อบ|การชุมนุมประท้วง|ทำเนียบรัฐบาล", re.IGNORECASE)),
    ("T10", "ความมั่นคง & ภูมิรัฐศาสตร์", "#ec4899", re.compile(r"ชายแดนไทย|กองทัพไทย|เรือรบ|ขีปนาวุธ|สงครามโลก|อิหร่าน|อิสราเอล|ฮิซบอลลาห์|ทหารกัมพูชา|อธิปไตยทางทะเล", re.IGNORECASE)),
    ("T05", "นโยบายรัฐ & สวัสดิการ", "#06b6d4", re.compile(r"บัตรประชารัฐ|เงินดิจิทัล|เงินเยียวยา|แจกเงิน|สปสช\.|ประกันสังคม|เบี้ยผู้สูงอายุ|คนละครึ่ง|เงินช่วยเหลือ", re.IGNORECASE)),
    ("T01", "สุขภาพ อาหาร และยา", "#10b981", re.compile(r"มะเร็ง|สมุนไพร|รักษารักษา|ยารักษา|อาหารเสริม|วิตามิน|โรคไต|เบาหวาน|ความดัน|หัวใจ|ดวงตา|สายตา|มะนาว|โซดา|กระทรวงสาธารณสุข|อย\.|สรรพคุณ|ดื่มน้ำ|กินน้ำ|ยาหยอด|สภาวะ.*ดวงตา|วัย\s*60|สุขภาพ|ลูกชิ้น|สบู่|อาหาร|แมลง|เนื้อสัตว์", re.IGNORECASE)),
]

def classify_topic_precisely(text: str) -> tuple[str, str, str]:
    """Returns (topic_id, topic_name, color) with high precision compound matching."""
    for tid, name, color, rx in HIGH_PRECISION_TOPIC_RULES:
        if rx.search(text):
            return tid, name, color
    return "T99", "เรื่องทั่วไป / อื่นๆ", "#475569"

# ---------------------------------------------------------------------------
# 4. Broadcast / Talk Show Episode Detection
# ---------------------------------------------------------------------------

_BROADCAST_RX = re.compile(
    r"LIVE\s*EP|PODCAST|HIGHLIGHT|รอบวัน|สรุปข่าว|คุยข่าว|Motor Check",
    re.IGNORECASE
)

def is_broadcast_episode(title: str) -> bool:
    return bool(_BROADCAST_RX.search(title or ""))


# ---------------------------------------------------------------------------
# 4b. Is this record a fact-check at all?
# ---------------------------------------------------------------------------
#
# AFNC publishes more than fact-checks on the same feed -- a knowledge base,
# event notices, general news -- and its section name lands in the `verdict`
# column. Those records are not claims anybody adjudicated, so counting them as
# fact-checks inflates every total and pollutes topic analysis.
#
# The list is explicit rather than inferred from "the verdict does not
# normalise". That distinction matters: 5,646 Sure & Share records also fail to
# normalise, but they ARE fact-checks whose verdict is simply not labelled yet.
# Dropping those would delete the labelling backlog rather than the noise.
NON_FACTCHECK_SECTIONS = {
    "คลังความรู้",            # knowledge base articles
    "ข่าวอื่นๆ",              # general news
    "กิจกรรม",                # event notices
    "ข่าวสาร",                # announcements
    "นโยบายรัฐบาล-ข่าวสาร",   # policy bulletins
    "ความสงบและความมั่นคง",   # section name, not a verdict
    "ผลิตภัณฑ์สุขภาพ",
    "การเงิน-หุ้น",
    "ภัยพิบัติ",
}


# Cofact is a blog, and its WordPress category is the first thing in the stored
# explanation, before the title. The claim-check categories are "Top Fact Checks*"
# and "จริงหรือไม่ ?"; the rest are commentary, essays, event notices, or a weekly
# roundup that bundles many claims into one post and so cannot carry a single
# verdict. Detected from the publisher's own taxonomy rather than guessed from
# wording -- the same principle as AFNC's status_label.
COFACT_NON_CLAIM_CATEGORIES = (
    "บทความ",                # articles and special reports (incl. "บทความ-รายงานพิเศษ")
    "กิจกรรม",               # event notices
    "ข่าวลวงประจำสัปดาห์",   # weekly roundup of many claims — not atomic
)


def _cofact_category(explanation: str, title: str) -> str:
    """The category prefix Cofact stores ahead of the title, or '' if absent."""
    e = (explanation or "").strip()
    t = (title or "").strip()[:18]
    if not t:
        return ""
    idx = e.find(t)
    return e[:idx].strip() if 0 < idx < 90 else ""


# Sure & Share's recurring explainer formats. KEYWORD teaches a term,
# FACTSHEET summarises a topic, CHECK-LIST rounds up several stories -- none of
# them puts a single claim up for adjudication.
#
# But the format alone is not the test, and the owner's own labels prove it. Of
# 59 such records he judged by hand, 46 were "not a claim" and 13 carried a real
# verdict, because the programme also uses these formats for genuine checks:
# "ป่วยโควิด-19 ห้ามกินยาไอบูโพรเฟน จริงหรือ ? | ชัวร์ก่อนแชร์ FACTSHEET" is a claim
# whatever the branding says.
#
# "จริงหรือ" is what separates them. Against those 59 human judgements the rule
# below is right on 37 of 38 it excludes; a blanket format rule would have
# retired 13 real claims. When in doubt it keeps the record in the queue, which
# costs a reviewer one keystroke -- the opposite error costs a claim nobody ever
# looks at again.
SURE_SHARE_EXPLAINER_FORMATS = re.compile(
    r"KEYWORD|CHECK\s*-?\s*LIST|FACT\s*SHEET", re.IGNORECASE)


def is_factcheck(source: str, title: str, verdict: str,
                 explanation: str = "", verdict_origin: str = "") -> bool:
    """True when the record is an adjudicated claim rather than other content.

    Deliberately conservative: unlabelled is still a fact-check. Only material
    that was never a claim in the first place is excluded.

    A human ruling outranks every rule below it. Editors' Picks and Uncategorized
    on Cofact are mixed bags that no taxonomy separates, so a reviewer marking
    one "not a claim" is the only signal that exists -- and throwing that away
    would mean asking them the same question again next month.
    """
    if verdict_origin == "human_not_claim":
        return False
    if is_broadcast_episode(title):
        return False
    if (verdict or "").strip() in NON_FACTCHECK_SECTIONS:
        return False
    if source == "sure_share" and SURE_SHARE_EXPLAINER_FORMATS.search(title or ""):
        if "จริงหรือ" not in (title or ""):
            return False
    if source == "cofact" and explanation:
        cat = _cofact_category(explanation, title)
        if cat.startswith(COFACT_NON_CLAIM_CATEGORIES):
            return False
    return True

def dedup_key(text: str) -> str:
    t = unicodedata.normalize("NFC", text).lower()
    t = re.sub(r"[\s​]+", "", t)
    t = re.sub(r"[^\wก-๙]+", "", t)
    return t

# ---------------------------------------------------------------------------
# 5. Stream Clean & Normalized Records
# ---------------------------------------------------------------------------

def get_normalized_records(
    db_path: Path | str = "data/th_verify.db",
    filter_broadcasts: bool = True,
    filter_inline_leaks: bool = False,
    deduplicate: bool = False
) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT id, source, source_id, source_url, title, claim, explanation,
               verdict, category, published_at, fingerprint, verdict_origin
        FROM fact_checks
        ORDER BY COALESCE(published_at, '9999') ASC, id ASC
    """).fetchall()

    seen_keys: set[str] = set()
    cleaned_records = []

    for r in rows:
        title_raw = r["title"]
        source = r["source"]
        
        is_bc = is_broadcast_episode(title_raw)
        if filter_broadcasts and is_bc:
            continue
            
        if source == "afp" and r["claim"] and r["claim"].strip():
            claim_clean = r["claim"].strip()
        else:
            claim_clean = clean_claim_text(title_raw, source)
            
        if len(claim_clean) < 10:
            continue
            
        has_leak = has_inline_leak(claim_clean)
        if filter_inline_leaks and has_leak:
            continue
            
        norm_verdict = normalize_verdict(source, r["verdict"])
        
        dkey = dedup_key(claim_clean)
        is_dup = dkey in seen_keys
        if deduplicate and is_dup:
            continue
        seen_keys.add(dkey)
        
        pub_date = r["published_at"]
        clean_date = str(pub_date)[:10] if pub_date else None
        clean_year = str(pub_date)[:4] if pub_date and str(pub_date)[:4].isdigit() else None

        # Apply high-precision classification
        tid, tname, tcolor = classify_topic_precisely(claim_clean)

        cleaned_records.append({
            "id": r["id"],
            "source": source,
            "source_id": r["source_id"],
            "url": r["source_url"],
            "title_raw": title_raw,
            "claim_clean": claim_clean,
            "explanation": r["explanation"],
            "verdict_raw": r["verdict"],
            "verdict_normalized": norm_verdict,
            "verdict_origin": r["verdict_origin"] or "native",
            "category_raw": r["category"],
            "published_at_raw": pub_date,
            "published_date": clean_date,
            "published_year": clean_year,
            "topic_id": tid,
            "topic_name": tname,
            "topic_color": tcolor,
            "is_broadcast": is_bc,
            "has_inline_leak": has_leak,
            "is_duplicate": is_dup,
            "dedup_key": dkey
        })

    conn.close()
    return cleaned_records
