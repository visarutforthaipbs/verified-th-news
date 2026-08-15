#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_issue_feature.py — the news-feature edition of the Issue Focus Report.

`build_issue_report.py` writes a white paper: it leads with the stat pills and
the trend matrix, and the prose is a garnish. This writes the same topic as a
special report (รายงานพิเศษ) — headline, standfirst, narrative sections, pull
quotes, real cases with links, and a "what to do" close — with the numbers used
as evidence inside the story rather than as the story. Same topic configs, same
database, same label policy; a different reader.

One source, two surfaces: the HTML is a long-scroll article on screen and an A4
feature when printed (the print block in section 09 of the stylesheet turns the
reading column into two columns on paper). The PDF is that same file printed by
headless Chrome.

Where the prose comes from
--------------------------
A story file, `scripts/issue_topics/<slug>.story.json`, written by a human (or
by an assistant reading the actual records — but read them, and by hand: nothing
in this script drafts prose, and nothing machine-drafted ships unlabelled).

Every string in the story file is passed through `string.Template`, so prose can
carry `${total}`, `${fake_pct}`, `${peak_year_be}` and friends and stay true as
the database moves. Unknown tokens are left alone rather than raising, so a typo
shows up in the output as `${typo}` instead of killing the build.

Missing story file, or missing sections, degrade to loudly-marked analyst slots:
a draft must be recognisable as a draft when someone forwards the PDF.

Label policy (inherited, do not relax)
--------------------------------------
* `heuristic`-origin verdicts are demoted to "อื่นๆ" in every count, exactly as
  the white paper does — a keyword guess is never presented as a publisher's
  ruling.
* Case cards are stricter still: only `source` and `human` origins are eligible.
  A card names a publisher beside a verdict, and the 2026-07-31 ground-truth
  audit put the `llm` tier at ~21% wrong, mostly collapsing "บิดเบือน" into
  "ปลอม". That is fine inside an aggregate and not fine on a card that says
  Thai PBS ruled this false.

Usage
-----
    python scripts/build_issue_feature.py callcenter_scam
    python scripts/build_issue_feature.py callcenter_scam --init-story
    python scripts/build_issue_feature.py migrant --cases 8 --no-pdf
    python scripts/build_issue_feature.py callcenter_scam --publish ~/Sites/
    python scripts/build_issue_feature.py --list
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from string import Template

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from build_dataset import normalize_verdict  # noqa: E402
from build_issue_report import (  # noqa: E402  — one WHERE builder for both SKUs
    SOURCE_NAMES,
    TOPICS_DIR,
    build_where,
    load_topic,
)
from _freshness import assert_fresh  # noqa: E402
import _brand  # noqa: E402
import _charts  # noqa: E402
from _pdf import write_pdf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "th_verify.db"
OUT_DIR = ROOT / "data" / "reports"

# Cards state a verdict next to a publisher's name, so only the two gold tiers
# qualify. See the module docstring.
CASE_ORIGINS = ("source", "human")

BUCKET_TH = {"false": "ข่าวปลอม", "misleading": "บิดเบือน",
             "true": "ข่าวจริง", "other": "อื่นๆ"}
BUCKET_ORDER = ["false", "misleading", "true", "other"]
THAI_MONTHS_ABBR = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


# ── data ────────────────────────────────────────────────────────────────────

def fetch(con: sqlite3.Connection, cfg: dict) -> list[dict]:
    """Topic records with everything a feature needs: claim text, link, origin.

    The white paper's fetch drops the claim body and the verdict origin because
    it only ever renders counts. A card needs the sentence that circulated and
    the provenance that decides whether it may be shown at all.
    """
    where, params = build_where(cfg)
    rows = con.execute(
        "SELECT id, source, source_url, title, claim, explanation, verdict, "
        "       verdict_origin, published_at "
        f"FROM fact_checks WHERE {where}", params).fetchall()

    cats = cfg["categories"]
    out = []
    for r in rows:
        text = " ".join(filter(None, (r["title"], r["claim"],
                                      r["explanation"]))).lower()
        matched = [c["name"] for c in cats if any(k in text for k in c["keywords"])]

        label = normalize_verdict(r["source"], r["verdict"] or "")
        if r["verdict_origin"] == "heuristic":
            label = "unknown"
        bucket = label if label in ("false", "misleading", "true") else "other"

        date = (r["published_at"] or "")[:10]
        year = None
        if len(date) >= 4 and date[:4].isdigit():
            year = int(date[:4])

        out.append({
            "id": r["id"], "source": r["source"], "url": r["source_url"] or "",
            "title": (r["title"] or "").strip(), "claim": (r["claim"] or "").strip(),
            "bucket": bucket, "origin": r["verdict_origin"] or "",
            "categories": matched, "year": year, "date": date,
        })
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def compute(cfg: dict, records: list[dict], now: datetime) -> dict:
    """Everything quantitative in one dict — also the substitution namespace the
    story file writes against, which is why the keys are prose-shaped."""
    total = len(records)
    buckets = Counter(r["bucket"] for r in records)
    cat_counts = Counter(c for r in records for c in r["categories"])
    src_counts = Counter(r["source"] for r in records)
    cat_short = {c["name"]: c["short"] for c in cfg["categories"]}

    year_floor = cfg.get("year_floor", 2020)
    years = [y for y in range(year_floor, now.year + 1)]
    yearly = Counter(r["year"] for r in records if r["year"] in set(years))
    monthly = Counter(r["date"][:7] for r in records if len(r["date"]) >= 7)
    # The current year is partial and must never be read as a decline, so the
    # peak is taken over completed years only.
    complete = [y for y in years if y < now.year]
    peak_year = max(complete, key=lambda y: yearly.get(y, 0)) if complete else now.year

    # Momentum: the last 365 days against the 365 before them. Rolling windows
    # rather than calendar years, so the figure does not reset every January.
    d_now = now.toordinal()
    last12 = sum(1 for r in records if r["date"] and
                 _ordinal(r["date"]) is not None and d_now - _ordinal(r["date"]) <= 365)
    prev12 = sum(1 for r in records if r["date"] and
                 _ordinal(r["date"]) is not None
                 and 365 < d_now - _ordinal(r["date"]) <= 730)
    delta = ((last12 - prev12) / prev12 * 100) if prev12 else 0.0

    top_cat = cat_counts.most_common(1)[0] if cat_counts else ("—", 0)
    top_src = src_counts.most_common(1)[0] if src_counts else ("—", 0)
    labelled = total - buckets["other"]

    def pct(n: int, of: int) -> str:
        return f"{n / of * 100:.0f}" if of else "0"

    # Ranked category and source tokens: ${cat2_name} / ${cat2_count}. Ranks move
    # as the archive grows, so a sentence must cite the name alongside the count
    # — "${cat4_name} ${cat4_count} คดี" stays true when rank 4 changes hands,
    # while a bare "${cat4_count} คดี" would quietly start describing something
    # else.
    ranked: dict[str, str] = {}
    for i, (name, count) in enumerate(cat_counts.most_common(), 1):
        ranked[f"cat{i}_name"] = cat_short.get(name, name)
        ranked[f"cat{i}_count"] = f"{count:,}"
    for i, (src, count) in enumerate(src_counts.most_common(), 1):
        ranked[f"src{i}_name"] = SOURCE_NAMES.get(src, src)
        ranked[f"src{i}_count"] = f"{count:,}"

    return {
        **ranked,
        "records": records,
        "years": years, "yearly": yearly, "monthly": monthly, "buckets": buckets,
        "cat_counts": cat_counts, "cat_short": cat_short, "src_counts": src_counts,
        # ── substitution namespace (everything below is a string) ────────────
        "total": f"{total:,}",
        "fake": f"{buckets['false']:,}",
        "misleading": f"{buckets['misleading']:,}",
        "true": f"{buckets['true']:,}",
        "other": f"{buckets['other']:,}",
        "labelled": f"{labelled:,}",
        "fake_pct": pct(buckets["false"], total),
        "fake_pct_labelled": pct(buckets["false"], labelled),
        "misleading_pct": pct(buckets["misleading"], total),
        "span_from_be": str(year_floor + 543),
        "span_to_be": str(now.year + 543),
        "peak_year_be": str(peak_year + 543),
        "peak_count": f"{yearly.get(peak_year, 0):,}",
        "this_year_be": str(now.year + 543),
        "this_year_count": f"{yearly.get(now.year, 0):,}",
        "last12": f"{last12:,}",
        "prev12": f"{prev12:,}",
        "delta_pct": f"{delta:+.0f}",
        "delta_word": "เพิ่มขึ้น" if delta > 0 else ("ลดลง" if delta < 0 else "ทรงตัว"),
        "top_cat": cat_short.get(top_cat[0], top_cat[0]),
        "top_cat_count": f"{top_cat[1]:,}",
        "top_source": SOURCE_NAMES.get(top_src[0], top_src[0]),
        "top_source_count": f"{top_src[1]:,}",
        "n_sources": str(len(src_counts)),
        "date_th": thai_date(now.strftime("%Y-%m-%d")),
    }


def _ordinal(date: str) -> int | None:
    try:
        return datetime.strptime(date[:10], "%Y-%m-%d").toordinal()
    except ValueError:
        return None


def thai_date(date: str) -> str:
    """2026-07-09 → 9 ก.ค. 2569. Empty in, empty out — a missing publication
    date is common enough in the archive that it must not raise."""
    try:
        d = datetime.strptime(date[:10], "%Y-%m-%d")
    except ValueError:
        return "—"
    return f"{d.day} {THAI_MONTHS_ABBR[d.month - 1]} {d.year + 543}"


def pick_cases(cfg: dict, records: list[dict], want: int,
               pinned: list[int]) -> list[dict]:
    """The cases the feature shows: gold-tier verdicts, on-topic, recent, and no
    single publisher taking the whole grid.

    Automatic selection is a starting point, not an editor. The topic filter
    runs over title + claim + explanation, which is right for counting and too
    loose for a card: a fact-check whose *explanation* happens to mention a bank
    is inside the aggregate but is not an example of the issue. So a card also
    has to carry a topic keyword in its own title or claim, which is the closest
    machine-checkable stand-in for "this record is about the topic".

    Pin the ones that actually belong with `case_ids` in the story file; pinned
    records skip every filter below and keep their given order.
    """
    by_id = {r["id"]: r for r in records}
    out = [by_id[i] for i in pinned if i in by_id]
    missing = [i for i in pinned if i not in by_id]
    if missing:
        print(f"  !! pinned case_ids not in this topic's records: {missing}",
              file=sys.stderr)

    terms = _card_terms(cfg)
    eligible = [r for r in records
                if r["id"] not in {c["id"] for c in out}
                and r["bucket"] != "other"
                and r["origin"] in CASE_ORIGINS
                and r["url"] and (r["claim"] or r["title"])
                and _on_topic(r, terms)]

    # A cap rather than a round-robin. AFNC publishes several times a day and
    # would fill every card; but forcing one card per publisher was worse — it
    # promoted a decade-old tangential record purely because its source was
    # otherwise unrepresented.
    cap = max(1, -(-want // 2))
    per = Counter(r["source"] for r in out)
    seen = {_dedupe_key(r) for r in out}
    for r in eligible:                      # records arrive newest-first
        if len(out) >= want:
            break
        key = _dedupe_key(r)
        if key in seen or per[r["source"]] >= cap:
            continue
        seen.add(key)
        per[r["source"]] += 1
        out.append(r)
    # Only if the cap starved the grid do we let the dominant publisher refill.
    for r in eligible:
        if len(out) >= want:
            break
        key = _dedupe_key(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out[:want]


def _card_terms(cfg: dict) -> list[str]:
    """Topic keywords flattened, for the stricter title/claim check on cards."""
    terms = list(cfg.get("keywords_any", []))
    for combo in cfg.get("keyword_combos", []):
        for any_of in combo:
            terms.extend(any_of)
    return [t.lower() for t in terms if t]


def _on_topic(r: dict, terms: list[str]) -> bool:
    text = f"{r['title']} {r['claim']}".lower()
    return any(t in text for t in terms)


def _dedupe_key(r: dict) -> str:
    """Hoaxes recirculate and publishers re-run them with near-identical
    headlines; the archive has 631 such groups. Comparing the first 40
    characters of the letters-only text is enough to keep two cards from being
    the same story twice."""
    text = re.sub(r"[^\wก-๙]+", "", (r["claim"] or r["title"]).lower())
    return text[:40]


# ── story file ──────────────────────────────────────────────────────────────

def story_path(cfg: dict) -> Path:
    return TOPICS_DIR / f"{cfg['slug']}.story.json"


def load_story(cfg: dict) -> dict:
    p = story_path(cfg)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def counters(st: dict, records: list[dict]) -> dict:
    """Story-defined counters, so a sentence about one pattern inside the topic
    stays true as the archive grows.

    A feature's best lines are the specific ones — "the same fake refund page
    has come back for two years" — and those numbers are not in the generic
    stats. Writing them by hand dates the piece the day it is rebuilt. Instead
    the story file declares what to count:

        "counters": {
          "refund": {
            "all_of": [["ปปง", "ป.ป.ท"], ["คืนเงิน", "ลงทะเบียน"]],
            "bucket": "false"
          },
          "campaign": {"from": "2025-12", "to": "2026-02"}
        }

    which yields ${n_refund}, ${first_refund_be} and ${last_refund_be}, and
    ${n_campaign} for the window. Matching is over title + claim only (the same
    standard the case cards use): an explanation that merely mentions the words
    is not an instance of the thing.
    """
    out: dict[str, str] = {}
    for name, spec in (st.get("counters") or {}).items():
        groups = [[a.lower() for a in g] for g in spec.get("all_of", [])]
        # `from`/`to` are inclusive YYYY-MM bounds. A counter may be a window
        # alone (no keywords), which is how a story cites "the three months
        # around the election" without hardcoding a number that a later backfill
        # would silently falsify.
        lo, hi = spec.get("from", ""), spec.get("to", "")
        hits = []
        for r in records:
            if spec.get("bucket") and r["bucket"] != spec["bucket"]:
                continue
            month = r["date"][:7]
            if (lo and month < lo) or (hi and month > hi) or (lo or hi) and not month:
                continue
            text = f"{r['title']} {r['claim']}".lower()
            if all(any(a in text for a in g) for g in groups):
                hits.append(r)
        years = sorted(r["year"] for r in hits if r["year"])
        out[f"n_{name}"] = f"{len(hits):,}"
        out[f"first_{name}_be"] = str(years[0] + 543) if years else "—"
        out[f"last_{name}_be"] = str(years[-1] + 543) if years else "—"
    return out


def fill(text: str, ns: dict) -> str:
    """Substitute ${tokens}; leave unknown ones visible rather than raising."""
    return Template(text).safe_substitute(
        {k: v for k, v in ns.items() if isinstance(v, str)})


SLOT = ('<div class="feat-slot"><b>✍️ ช่องสำหรับบรรณาธิการ —</b> {what} '
        '(แก้ไขที่ <code>scripts/issue_topics/{slug}.story.json</code>)</div>')


def init_story(cfg: dict, ns: dict) -> Path:
    """Write a story skeleton pre-filled with this topic's real numbers, so the
    writer starts from the evidence instead of a blank file."""
    p = story_path(cfg)
    if p.exists():
        sys.exit(f"{p} already exists — edit it, or delete it first")
    top_cats = [ns["cat_short"].get(n, n) for n, _ in ns["cat_counts"].most_common(4)]
    skeleton = {
        "slug": cfg["slug"],
        "kicker": "รายงานพิเศษ",
        "headline_html": "✍️ พาดหัว — ใส่ <em>คำสำคัญ</em> ที่ต้องการเน้นด้วยสีแดง",
        "dek": "✍️ ความนำ 1–2 ประโยค บอกว่าเรื่องนี้คืออะไรและทำไมต้องอ่านตอนนี้",
        "byline": "กองบรรณาธิการ ห้องปฏิบัติการข่าวปลอม",
        "chips": [f"ตรวจสอบแล้ว ${{total}} คดี", f"ประเด็นเด่น: {top_cats[0] if top_cats else '—'}"],
        "lead_html": "✍️ ย่อหน้าเปิด",
        "sections": [
            {"heading": "✍️ หัวข้อที่ 1", "body_html": ["✍️ เนื้อหา"], "figure": "years"},
            {"heading": "✍️ หัวข้อที่ 2", "body_html": ["✍️ เนื้อหา"], "figure": "categories",
             "quote": {"text": "✍️ ประโยคเด่น", "cite": "แหล่งที่มา"}},
            {"heading": "✍️ หัวข้อที่ 3", "body_html": ["✍️ เนื้อหา"], "figure": "verdicts"},
        ],
        "cases_heading": "คดีตัวอย่างจากฐานข้อมูล",
        "cases_intro": "✍️ เกริ่นนำก่อนเข้าตัวอย่าง",
        "case_ids": [],
        "box": {"title": "ตัวเลขที่ควรรู้",
                "items": ["✍️ ข้อเท็จจริงสั้น ๆ", "✍️ ข้อเท็จจริงสั้น ๆ"]},
        "actions_heading": "สิ่งที่ควรทำ",
        "actions": ["✍️ ข้อแนะนำ", "✍️ ข้อแนะนำ", "✍️ ข้อแนะนำ"],
        "_tokens_available": sorted(k for k, v in ns.items() if isinstance(v, str)),
    }
    p.write_text(json.dumps(skeleton, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    return p


# ── rendering ───────────────────────────────────────────────────────────────

def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def figure(kind: str, ns: dict, now: datetime, sec: dict | None = None) -> str:
    """The chart a section asks for by name, or nothing if the name is unknown —
    a typo in a story file loses a figure, it does not lose the report."""
    sec = sec or {}
    if kind == "months":
        # A yearly chart cannot show an event: a campaign, a crisis or a court
        # ruling lives inside one bar. `from`/`to` on the section bound the
        # window; the default is the last two years.
        end = sec.get("to") or now.strftime("%Y-%m")
        start = sec.get("from") or f"{now.year - 2}-{now.month:02d}"
        months = []
        y, m = int(start[:4]), int(start[5:7])
        while f"{y:04d}-{m:02d}" <= end:
            months.append(f"{y:04d}-{m:02d}")
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        rows = [(f"{THAI_MONTHS_ABBR[int(k[5:7]) - 1]} {str(int(k[:4]) + 543)[2:]}",
                 ns["monthly"].get(k, 0)) for k in months]
        return _charts.columns(rows, title=sec.get("figure_title", "จำนวนคดีรายเดือน"),
                               note=sec.get("figure_note", ""))
    if kind == "years":
        rows = [(str(y + 543), ns["yearly"].get(y, 0)) for y in ns["years"]]
        return _charts.columns(
            rows, title="จำนวนคดีที่ถูกตรวจสอบในแต่ละปี",
            highlight=str(now.year + 543),
            note=f"* พ.ศ. {now.year + 543} เป็นข้อมูลถึง {thai_date(now.strftime('%Y-%m-%d'))}")
    if kind == "categories":
        rows = [(ns["cat_short"].get(n, n), c) for n, c in ns["cat_counts"].most_common()]
        return _charts.hbar(rows, title="ประเด็นที่พบมากที่สุด", label_width=200)
    if kind == "sources":
        rows = [(SOURCE_NAMES.get(s, s), c) for s, c in ns["src_counts"].most_common()]
        return _charts.hbar(rows, title="หน่วยงานที่ตรวจสอบ", label_width=220)
    if kind == "verdicts":
        parts = [(BUCKET_TH[b], ns["buckets"][b], _charts.STATUS.get(b, _charts.GRAY))
                 for b in BUCKET_ORDER]
        return _charts.stacked_share(parts, title="สัดส่วนผลการตรวจสอบ")
    return ""


def case_card(r: dict) -> str:
    claim = r["claim"] or r["title"]
    if len(claim) > 200:
        claim = claim[:200].rstrip() + "…"
    src = SOURCE_NAMES.get(r["source"], r["source"])
    link = (f'<a href="{esc(r["url"])}" target="_blank" rel="noopener">'
            f'ดูผลตรวจสอบ ↗</a>') if r["url"] else ""
    # The claim is printed at card size and the verdict in small mono above it,
    # so the card is read for a second before it is understood. Naming the claim
    # as a claim ("what was shared") is what keeps a skimmer from taking the
    # sentence as the report's own statement — the same reason a fact-check
    # headline never states the false claim bare.
    return (
        f'<article class="feat-case feat-case--{r["bucket"]}">'
        f'<div class="feat-case__verdict">ผลตรวจสอบ: {BUCKET_TH[r["bucket"]]}</div>'
        f'<div class="feat-case__label">สิ่งที่ถูกแชร์</div>'
        f'<p class="feat-case__claim">{esc(claim)}</p>'
        f'<div class="feat-case__foot"><span>{esc(src)} · {thai_date(r["date"])}</span>'
        f"{link}</div></article>")


def render(cfg: dict, st: dict, ns: dict, cases: list[dict], now: datetime,
           *, economy: bool = False) -> str:
    slug = cfg["slug"]
    F = lambda s: fill(s, ns)  # noqa: E731 — one-line alias used throughout

    kicker = esc(F(st.get("kicker", "รายงานพิเศษ")))
    headline = F(st["headline_html"]) if st.get("headline_html") else (
        f'ข่าวลวงเรื่อง <em>{esc(cfg.get("slug", ""))}</em> '
        f'{ns["total"]} คดีในฐานข้อมูลการตรวจสอบข้อเท็จจริงไทย')
    dek = (f'<p class="feat-dek">{F(st["dek"])}</p>' if st.get("dek")
           else SLOT.format(what="ความนำ (dek) ยังไม่ได้เขียน", slug=slug))
    byline = esc(F(st.get("byline", "กองบรรณาธิการ ห้องปฏิบัติการข่าวปลอม")))
    chips = "".join(_brand.chip(F(c), "alert" if i == 0 else "")
                    for i, c in enumerate(st.get("chips", [])))
    chips_html = f'<div class="feat-chips">{chips}</div>' if chips else ""

    lead = (f'<p class="feat-lead">{F(st["lead_html"])}</p>' if st.get("lead_html")
            else SLOT.format(what="ย่อหน้าเปิดเรื่องยังไม่ได้เขียน", slug=slug))

    kpis = _charts.kpi_row([
        ("คดีทั้งหมด", ns["total"], None, "flat"),
        ("ตัดสินว่าปลอม", ns["fake"], f'{ns["fake_pct"]}%', "up"),
        ("12 เดือนล่าสุด", ns["last12"], f'{ns["delta_pct"]}%',
         "up" if ns["delta_pct"].startswith("+") else "down"),
        ("หน่วยงานตรวจสอบ", ns["n_sources"], None, "flat"),
    ])

    body = []
    for i, sec in enumerate(st.get("sections", []), 1):
        paras = "".join(f"<p>{F(p)}</p>" for p in sec.get("body_html", []))
        quote = ""
        if sec.get("quote"):
            q = sec["quote"]
            cite = (f'<span class="fnl-quote__cite">{esc(F(q.get("cite", "")))}</span>'
                    if q.get("cite") else "")
            quote = (f'<blockquote class="fnl-quote fnl-quote--display">'
                     f'{F(q["text"])}{cite}</blockquote>')
        body.append(
            f'<section class="feat-sec">'
            f'{_brand.sys_rule(f"SEC // {i:02d}")}'
            f'<h2 class="feat-sec__head">{F(sec.get("heading", ""))}</h2>'
            f"{paras}{quote}{figure(sec.get('figure', ''), ns, now, sec)}</section>")
    if not body:
        body.append(SLOT.format(what="ยังไม่มีเนื้อหาบทความ (sections)", slug=slug)
                    + figure("years", ns, now) + figure("verdicts", ns, now))

    cases_html = ""
    if cases:
        intro = f"<p>{F(st['cases_intro'])}</p>" if st.get("cases_intro") else ""
        cases_html = (
            f'<section class="feat-sec">'
            f'{_brand.sys_rule("CASES // ตัวอย่างจริง")}'
            f'<h2 class="feat-sec__head">'
            f'{esc(F(st.get("cases_heading", "คดีตัวอย่างจากฐานข้อมูล")))}</h2>'
            f"{intro}"
            f'<div class="feat-cases">{"".join(case_card(r) for r in cases)}</div>'
            f'<p class="fnl-meta fnl-meta--tight">แสดงเฉพาะคดีที่คำตัดสินมาจาก'
            f'หน่วยงานผู้ตรวจสอบโดยตรง (หรือผ่านการตรวจโดยผู้เชี่ยวชาญของเรา) '
            f'เรียงจากใหม่ไปเก่า และกระจายตามหน่วยงาน</p></section>')

    box = ""
    if st.get("box"):
        items = "".join(f"<li>{F(i)}</li>" for i in st["box"].get("items", []))
        box = (f'<aside class="feat-box"><div class="feat-box__title">'
               f'{esc(F(st["box"].get("title", "ตัวเลขที่ควรรู้")))}</div>'
               f"<ul>{items}</ul></aside>")

    actions = ""
    if st.get("actions"):
        items = "".join(f"<li>{F(a)}</li>" for a in st["actions"])
        actions = (f'<section class="feat-sec">'
                   f'{_brand.sys_rule("ACT // สิ่งที่ควรทำ")}'
                   f'<h2 class="feat-sec__head">'
                   f'{esc(F(st.get("actions_heading", "สิ่งที่ควรทำ")))}</h2>'
                   f'<ol class="feat-actions">{items}</ol></section>')

    method = (
        f'<section class="feat-sec">{_brand.sys_rule("METHOD // ระเบียบวิธี")}'
        f'<div class="fnl-note"><p>รายงานฉบับนี้นับจากฐานข้อมูล TH Verify '
        f'ซึ่งรวบรวมผลการตรวจสอบข้อเท็จจริงจาก {ns["n_sources"]} หน่วยงาน '
        f'ได้แก่ {esc(", ".join(SOURCE_NAMES.get(s, s) for s, _ in ns["src_counts"].most_common()))} '
        f'คัดเฉพาะคดีที่เข้าเงื่อนไขคำค้นของประเด็นนี้ '
        f'{esc(cfg.get("methodology_note", ""))} '
        f'การจัดหมวดหมู่ทำโดยอัตโนมัติจากคำสำคัญ คดีหนึ่งจึงอาจอยู่ได้มากกว่าหนึ่งหมวด '
        f'คำตัดสินที่ได้จากการเดาด้วยระบบอัตโนมัติ (heuristic) '
        f'ถูกนับเป็น “อื่นๆ” เสมอ และไม่ถูกนำมาแสดงเป็นคดีตัวอย่าง</p>'
        f'<p><strong>ข้อจำกัด:</strong> ข้อมูลครอบคลุมเฉพาะเรื่องที่หน่วยงานข้างต้นเคยตรวจสอบ '
        f'จึงไม่ใช่ภาพรวมของข่าวลวงทั้งหมดในสังคม และข้อมูลปี พ.ศ. {ns["this_year_be"]} '
        f'เป็นข้อมูลถึงวันที่ {ns["date_th"]} เท่านั้น</p></div></section>')

    return _brand.document(
        F(re.sub(r"<[^>]+>", "", headline)),
        f"""
  <button class="fnl-btn fnl-btn--float dl-btn" onclick="window.print()">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
    ดาวน์โหลด PDF
  </button>

  <article class="fnl-article">
    <header class="feat-hero">
      <div class="feat-hero__brand">{_brand.mark(42)}
        <div class="feat-hero__org">{_brand.ORG_TH}<span>{_brand.ORG_EN}</span></div>
      </div>
      <div class="feat-kicker">{kicker}</div>
      <h1 class="feat-headline">{headline}</h1>
      {dek}
      <div class="feat-byline">
        <span><b>{byline}</b></span>
        <span>เผยแพร่ {ns["date_th"]}</span>
        <span>ข้อมูล {ns["total"]} คดี · พ.ศ. {ns["span_from_be"]}–{ns["span_to_be"]}</span>
      </div>
      {chips_html}
    </header>

    {lead}
    <div class="feat-kpi-span">{kpis}</div>

    {"".join(body)}
    {box}
    {cases_html}
    {actions}
    {method}

    {_brand.footer(f"© พ.ศ. {ns['span_to_be']} {_brand.ORG_TH} · {_brand.ORG_EN}",
                   "ตัวเลขสร้างอัตโนมัติจากฐานข้อมูล — ห้ามใช้อ้างอิงทางกฎหมาย")}
  </article>
""",
        economy=economy, extra_css=_charts.CHART_CSS)


# ── cli ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("topic", nargs="?", help="topic slug in scripts/issue_topics/ "
                                             "or a path to a config JSON")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", help="output HTML path "
                                  "(default data/reports/<slug>_feature.html)")
    ap.add_argument("--publish", help="also copy the HTML (and PDF) here")
    ap.add_argument("--cases", type=int, default=6, help="number of case cards")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--init-story", action="store_true",
                    help="write a story-file skeleton for this topic and exit")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--print-economy", action="store_true",
                    help="render the opt-in light variant — desk printing only")
    args = ap.parse_args()

    if args.list or not args.topic:
        for p in sorted(TOPICS_DIR.glob("*.json")):
            if p.name.endswith(".story.json"):
                continue
            has = (TOPICS_DIR / f"{p.stem}.story.json").exists()
            print(f"{p.stem:<20} {'story ✓' if has else 'story — (--init-story)'}")
        return 0

    cfg = load_topic(args.topic)
    now = datetime.now()

    con = sqlite3.connect(args.db)
    assert_fresh(con)
    con.row_factory = sqlite3.Row
    try:
        records = fetch(con, cfg)
    finally:
        con.close()
    if not records:
        sys.exit("no records matched this topic's keywords — nothing to report")

    ns = compute(cfg, records, now)

    if args.init_story:
        print(f"wrote {init_story(cfg, ns)}")
        return 0

    st = load_story(cfg)
    if not st:
        print(f"  no story file — rendering with analyst slots. "
              f"Start one with: --init-story", file=sys.stderr)
    ns.update(counters(st, records))
    cases = pick_cases(cfg, records, args.cases, st.get("case_ids", []))

    html_out = render(cfg, st, ns, cases, now, economy=args.print_economy)
    out = Path(args.out) if args.out else OUT_DIR / f"{cfg['slug']}_feature.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")
    print(f"wrote {out}  ({len(records)} records, {len(cases)} case cards)")

    pdf = out.with_suffix(".pdf")
    if not args.no_pdf and write_pdf(out, pdf):
        print(f"wrote {pdf}")

    if args.publish:
        dest = Path(args.publish).expanduser()
        if dest.is_dir():
            shutil.copy2(out, dest / out.name)
            if pdf.exists() and not args.no_pdf:
                shutil.copy2(pdf, dest / pdf.name)
            print(f"published to {dest}/")
        else:
            shutil.copy2(out, dest)
            print(f"published to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
