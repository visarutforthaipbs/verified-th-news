#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_weekly_fakenews_report.py — editorial weekly report on the misinformation
that was actually fact-checked in a given week.

This is the *content* weekly report, not the system-status one. Where
`build_weekly_report.py` describes the database, this describes what Thai
fact-checkers debunked: volume, themes, recirculating hoaxes, week-over-week
movement, and the notable individual claims.

Outputs Markdown, HTML and PDF to data/reports/.

Design notes
------------
* Reuses `build_brief.fetch`, `cluster_claims` and `find_recirculating` rather
  than reimplementing them, so the heuristic-demotion policy (a keyword guess is
  never shown as if the publisher issued that verdict) is applied identically.
* Every number is computed from the database. The narrative paragraph is
  optionally drafted by the local LLM, but only from claims present in the
  window, and it is labelled as machine-drafted in the output.
* PDF is produced by headless Chrome. No Python PDF library is installed, and
  Chrome renders Thai script correctly, which most of them do not.

Usage
-----
    python scripts/build_weekly_fakenews_report.py                 # last 7 days
    python scripts/build_weekly_fakenews_report.py --days 14
    python scripts/build_weekly_fakenews_report.py --start 2026-07-24 --end 2026-07-31
    python scripts/build_weekly_fakenews_report.py --no-llm        # skip narrative
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from _freshness import assert_fresh  # noqa: E402
from build_brief import fetch, find_recirculating  # noqa: E402
import _brand  # noqa: E402
import _charts  # noqa: E402
# Chrome-to-PDF lives in _pdf so this builder and build_issue_feature.py share
# one invocation and one set of flags.
from _pdf import write_pdf  # noqa: E402

OUTPUT_DIR = Path("data/reports")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")

SOURCE_TH = {
    "afnc": "ศูนย์ต่อต้านข่าวปลอม (AFNC)",
    "sure_share": "ชัวร์ก่อนแชร์ (MCOT)",
    "cofact": "Cofact Thailand",
    "afp": "AFP Fact Check Thailand",
    "thaipbs": "Thai PBS Verify",
}
LABEL_TH = {
    "false": "ข่าวปลอม",
    "misleading": "ข่าวบิดเบือน",
    "altered_media": "ภาพ/คลิปดัดแปลง",
    "true": "ข่าวจริง",
    "scam_alert": "เตือนภัยมิจฉาชีพ",
    "satire": "เสียดสี",
    "unknown": "ยังไม่ระบุผล",
}
NEGATIVE = ("false", "misleading", "altered_media")

# Thematic buckets. Keyword driven and deliberately transparent: an editor can
# read the rule that put a claim in a bucket, which matters more here than the
# marginal recall a classifier would add.
THEMES: list[tuple[str, list[str]]] = [
    # Checked first and deliberately so. The single largest pattern in the data is
    # criminals wearing an institution's name -- fake agency LINE/TikTok accounts,
    # forged billing SMS, spoofed broadcaster channels. Those claims also mention
    # money or policy words, so a generic finance bucket would swallow them and
    # hide the pattern; that is exactly what the first version of this report did.
    ("แอบอ้างหน่วยงานและองค์กร",
     ["แอบอ้าง", "ปลอมบัญชี", "บัญชีปลอม", "เพจปลอม", "บัญชีใหม่", "ไลน์",
      "line", "tiktok", "sms", "ลิงก์", "การไฟฟ้า", "กฟภ", "กฟผ", "ประปา",
      "ก.ล.ต.", "m-flow", "กรมสรรพากร", "ไปรษณีย์", "ธนาคารกรุง", "สวมรอย"]),
    ("การเงิน หลอกลงทุน และแก๊งคอลเซ็นเตอร์",
     ["เงิน", "ลงทุน", "หุ้น", "กู้", "สินเชื่อ", "โอน", "ธนาคาร", "คอลเซ็นเตอร์",
      "มิจฉาชีพ", "หลอก", "ดูดเงิน", "คริปโต", "ออมสิน", "เยียวยา", "ค่าปรับ"]),
    ("สุขภาพ ยา และผลิตภัณฑ์",
     ["สุขภาพ", "ยา", "รักษา", "มะเร็ง", "วัคซีน", "โรค", "กิน", "สมุนไพร",
      "อาหาร", "แพทย์", "โรงพยาบาล", "ป่วย", "ตับ", "ไต", "หัวใจ", "สมอง",
      "ปวด", "อาการ", "อวัยวะ", "เลือด", "ความดัน", "เบาหวาน", "นอน"]),
    ("นโยบายรัฐและสวัสดิการ",
     ["รัฐบาล", "ครม.", "กระทรวง", "นโยบาย", "ลงทะเบียน", "สิทธิ", "บัตร",
      "ประกาศ", "กรม", "ราชการ", "เลือกตั้ง"]),
    ("ภัยพิบัติและสภาพอากาศ",
     ["น้ำท่วม", "แผ่นดินไหว", "พายุ", "ภัยพิบัติ", "สึนามิ", "ไฟไหม้",
      "ฝน", "เตือนภัย", "ดินถล่ม"]),
    ("ความมั่นคง สงคราม และต่างประเทศ",
     ["ทหาร", "สงคราม", "ชายแดน", "อิสราเอล", "อิหร่าน", "กัมพูชา", "เมียนมา",
      "จีน", "สหรัฐ", "ระเบิด", "โจมตี", "ทรัมป์"]),
]
AI_RE = re.compile(r"(AI|เอไอ|deepfake|ดีปเฟก|ปัญญาประดิษฐ์|สร้างด้วย)", re.I)


# Organisations whose name gets borrowed by scammers. Tracked by name because a
# repeat target is the actionable signal: one fake PEA account is an incident,
# four in a week is a campaign the utility and its customers should be warned about.
IMPERSONATION_TARGETS: list[tuple[str, list[str]]] = [
    ("การไฟฟ้าส่วนภูมิภาค (กฟภ.)", ["การไฟฟ้าส่วนภูมิภาค", "กฟภ"]),
    ("การไฟฟ้าฝ่ายผลิต (กฟผ.)", ["การไฟฟ้าฝ่ายผลิต", "กฟผ"]),
    ("สำนักงานตำรวจแห่งชาติ", ["ตำรวจ", "ตร.", "สตช"]),
    ("ก.ล.ต.", ["ก.ล.ต."]),
    ("M-Flow / ทางหลวง", ["m-flow", "ทางหลวง", "มอเตอร์เวย์"]),
    ("กรมสรรพากร", ["สรรพากร"]),
    ("ไปรษณีย์ไทย", ["ไปรษณีย์"]),
    ("Thai PBS", ["thai pbs", "thaipbs", "ไทยพีบีเอส"]),
    ("การประปา", ["การประปา"]),
    ("ธนาคาร", ["ธนาคาร", "ออมสิน", "ธกส"]),
]


def impersonation_counts(claims: list[dict]) -> list[tuple[str, list[dict]]]:
    hits: dict[str, list[dict]] = defaultdict(list)
    for c in claims:
        low = c["claim"].lower()
        for name, kws in IMPERSONATION_TARGETS:
            if any(k in low for k in kws):
                hits[name].append(c)
                break
    return sorted(hits.items(), key=lambda kv: -len(kv[1]))


def theme_of(claim: str) -> str:
    for name, kws in THEMES:
        if any(k in claim for k in kws):
            return name
    return "อื่น ๆ"


def llm_narrative(claims: list[dict], stats: dict,
                  period: dict | None = None) -> str | None:
    """Ask the local model for an editorial read of the week.

    Grounded deliberately: it receives only headlines from this window plus the
    computed counts, and is told not to introduce facts. Returns None on any
    failure so the report still builds without the GPU.
    """
    sample = "\n".join(f"- [{LABEL_TH.get(c['label'], c['label'])}] {c['claim'][:110]}"
                       for c in claims[:60])
    P = period or {"th": "ประจำสัปดาห์", "this_th": "สัปดาห์นี้"}
    period_th = P["th"] if P["th"].startswith("ประจำ") else "ประจำ" + P["th"].replace("ราย", "")
    period_this = P["this_th"]
    prompt = f"""คุณเป็นบรรณาธิการข่าวตรวจสอบข้อเท็จจริงของไทย
เขียนบทวิเคราะห์ภาพรวมข่าวลวง{period_th} ความยาว 3 ย่อหน้า

ข้อมูลสถิติ{period_this}:
- ตรวจสอบทั้งหมด {stats['total']} เรื่อง
- ข่าวปลอม/บิดเบือน/ดัดแปลง {stats['negative']} เรื่อง
- หมวดที่พบมากที่สุด: {stats['top_theme']}
- ข่าวลวงเวียนซ้ำจากอดีต {stats['recirculating']} เรื่อง

รายการข่าวที่ตรวจสอบ{period_this}:
{sample}

กติกา:
- วิเคราะห์เฉพาะจากรายการข้างต้นเท่านั้น ห้ามเพิ่มข้อมูลหรือตัวเลขที่ไม่ได้ให้มา
- ย่อหน้า 1: ภาพรวมและแนวโน้มเด่นของช่วงเวลานี้
- ย่อหน้า 2: รูปแบบการหลอกลวงที่น่าสังเกตและกลุ่มเป้าหมาย
- ย่อหน้า 3: ข้อเสนอแนะต่อประชาชนและสื่อ
- เขียนเป็นภาษาไทย ไม่ต้องใส่หัวข้อ ไม่ต้องใส่ bullet"""
    body = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.3, "num_predict": 900}}
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/generate",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["response"].strip()
    except Exception as exc:
        print(f"  (narrative skipped: {exc})", file=sys.stderr)
        return None


def md_cell(text: str) -> str:
    """Escape a claim for use inside a Markdown table cell.

    Claim titles are publisher-written and some contain a literal pipe
    ("… Brain Rot | [REPLAY]"), which silently split the row into an extra
    column in both the Markdown and the rendered HTML table.
    """
    return text.replace("|", "\\|")


def period_labels(start: str, end: str) -> dict:
    """Name the report after the window it actually covers.

    The generator is usable over any range, but every label was hardcoded to
    "รายสัปดาห์"/WEEKLY. Asked for July, it produced a month of data under a
    weekly headline -- the same class of error as the stale "Week 31" report
    that summarised a two-week-old snapshot.
    """
    span = (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days
    if span <= 10:
        return {"th": "รายสัปดาห์", "en": "WEEKLY", "prev_th": "สัปดาห์ก่อน",
                "this_th": "สัปดาห์นี้", "overview_th": "ภาพรวมสัปดาห์นี้"}
    if span <= 45:
        return {"th": "รายเดือน", "en": "MONTHLY", "prev_th": "เดือนก่อน",
                "this_th": "เดือนนี้", "overview_th": "ภาพรวมเดือนนี้"}
    return {"th": "ตามช่วงเวลา", "en": "PERIOD", "prev_th": "ช่วงก่อนหน้า",
            "this_th": "ช่วงนี้", "overview_th": "ภาพรวมช่วงนี้"}


def build_markdown(cur: list[dict], prev: list[dict], recirc, narrative, start, end) -> str:
    total = len(cur)
    neg = [c for c in cur if c["label"] in NEGATIVE]
    by_source = Counter(c["source"] for c in cur)
    by_label = Counter(c["label"] for c in cur)
    by_theme = Counter(theme_of(c["claim"]) for c in neg)
    prev_neg = [c for c in prev if c["label"] in NEGATIVE]
    ai_items = [c for c in neg if AI_RE.search(c["claim"])]

    def delta(now: int, before: int) -> str:
        if before == 0:
            return "ใหม่" if now else "—"
        d = (now - before) / before * 100
        return f"{d:+.0f}%"

    L: list[str] = []
    A = L.append
    P = period_labels(start, end)
    A(f"# รายงานสถานการณ์ข่าวลวง{P['th']}")
    A(f"## TH Verify {P['en'].title()} Misinformation Report")
    A("")
    A(f"**ช่วงข้อมูล:** {start} ถึง {end}  ")
    A(f"**จัดทำเมื่อ:** {datetime.now():%Y-%m-%d %H:%M}  ")
    A(f"**แหล่งข้อมูล:** คลังตรวจสอบข้อเท็จจริง TH Verify "
      f"({', '.join(SOURCE_TH[s] for s in by_source)})")
    A("")
    A("---")
    A("")
    A(f"## 1. {P['overview_th']}")
    A("")
    A(f"| ตัวชี้วัด | {P['this_th']} | {P['prev_th']} | เปลี่ยนแปลง |")
    A("| :--- | ---: | ---: | ---: |")
    A(f"| เรื่องที่ถูกตรวจสอบทั้งหมด | {total} | {len(prev)} | {delta(total, len(prev))} |")
    A(f"| ข่าวปลอม/บิดเบือน/ดัดแปลง | {len(neg)} | {len(prev_neg)} | {delta(len(neg), len(prev_neg))} |")
    A(f"| ข่าวลวงเวียนซ้ำจากอดีต | {len(recirc)} | — | — |")
    A(f"| เกี่ยวข้องกับ AI/ดีปเฟก | {len(ai_items)} | — | — |")
    A("")

    if narrative:
        A("## 2. บทวิเคราะห์")
        A("")
        for para in [p for p in narrative.split("\n") if p.strip()]:
            A(para.strip())
            A("")
        A(f"> *บทวิเคราะห์ส่วนนี้ร่างโดยโมเดลภาษาท้องถิ่นจากรายการข่าวใน{P['this_th']}เท่านั้น "
          "และควรผ่านการตรวจแก้โดยบรรณาธิการก่อนเผยแพร่*")
        A("")

    A("## 3. หมวดข่าวลวงที่พบมากที่สุด")
    A("")
    A("| หมวด | จำนวน | สัดส่วน |")
    A("| :--- | ---: | ---: |")
    for theme, n in by_theme.most_common():
        A(f"| {theme} | {n} | {n / max(len(neg), 1) * 100:.0f}% |")
    A("")

    impers = impersonation_counts(neg)
    if impers:
        A("## 3.1 องค์กรที่ถูกแอบอ้างมากที่สุด")
        A("")
        A("ชื่อหน่วยงานที่มิจฉาชีพนำไปใช้สร้างความน่าเชื่อถือ "
          f"หน่วยงานที่ถูกแอบอ้างซ้ำหลายครั้งใน{P['this_th']} "
          "บ่งชี้ว่ากำลังตกเป็นเป้าของแคมเปญหลอกลวง ไม่ใช่เหตุการณ์เดี่ยว")
        A("")
        A("| หน่วยงานที่ถูกแอบอ้าง | จำนวนครั้ง |")
        A("| :--- | ---: |")
        for name, items in impers:
            A(f"| {name} | {len(items)} |")
        A("")
        top_name, top_items = impers[0]
        if len(top_items) > 1:
            A(f"**ข้อสังเกต:** {top_name} ถูกแอบอ้างถึง {len(top_items)} ครั้งใน{P['this_th']} "
              f"ในรูปแบบที่ต่างกัน ควรแจ้งเตือนผู้ใช้บริการโดยตรง")
            A("")

    A("## 4. ผลการตรวจสอบจำแนกตามประเภท")
    A("")
    A("| ผลการตรวจสอบ | จำนวน |")
    A("| :--- | ---: |")
    for label, n in by_label.most_common():
        A(f"| {LABEL_TH.get(label, label)} | {n} |")
    A("")

    A("## 5. สำนักที่ตรวจสอบ")
    A("")
    A("| สำนัก | จำนวน |")
    A("| :--- | ---: |")
    for s, n in by_source.most_common():
        A(f"| {SOURCE_TH.get(s, s)} | {n} |")
    A("")

    if recirc:
        A(f"## 6. ข่าวลวงเวียนซ้ำ ({len(recirc)} เรื่อง)")
        A("")
        A(f"ข่าวลวงที่ถูกตรวจสอบไปแล้วในอดีต แต่กลับมาแพร่ซ้ำใน{P['this_th']} "
          "เป็นสัญญาณว่าการแก้ข่าวครั้งแรกยังเข้าไม่ถึงผู้รับสาร")
        A("")
        A(f"| ข่าว{P['this_th']} | เคยตรวจสอบเมื่อ | ความคล้าย |")
        A("| :--- | :--- | ---: |")
        for c, first in recirc[:12]:
            A(f"| [{md_cell(c['claim'][:80])}]({c['url']}) | {first['date']} | {first['score']:.2f} |")
        A("")

    if ai_items:
        A(f"## 7. ข่าวลวงที่เกี่ยวข้องกับ AI ({len(ai_items)} เรื่อง)")
        A("")
        for c in ai_items[:10]:
            A(f"- **[{LABEL_TH.get(c['label'], c['label'])}]** "
              f"[{c['claim'][:100]}]({c['url']}) — {SOURCE_TH.get(c['source'], c['source'])}, {c['date']}")
        A("")

    A(f"## 8. รายการข่าวลวงทั้งหมดใน{P['this_th']}")
    A("")
    A("| วันที่ | ผลตรวจสอบ | เรื่อง | สำนัก |")
    A("| :--- | :--- | :--- | :--- |")
    for c in sorted(neg, key=lambda x: x["date"], reverse=True):
        A(f"| {c['date']} | {LABEL_TH.get(c['label'], c['label'])} | "
          f"[{md_cell(c['claim'][:90])}]({c['url']}) | {SOURCE_TH.get(c['source'], c['source'])} |")
    A("")
    A("---")
    A("")
    A("*รายงานนี้สร้างจากคลังข้อมูล TH Verify โดยนับเฉพาะผลการตรวจสอบที่สำนักข่าวระบุเอง "
      "หรือผ่านการตรวจโดยมนุษย์ ผลที่ได้จากการเดาด้วยคีย์เวิร์ดถูกตัดออกจากรายงานนี้ตามนโยบาย*")
    return "\n".join(L)


MD_INLINE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MD_META = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
SECTION_NO = re.compile(r"^(\d+(?:\.\d+)?)\.?\s+(.*)$")


def split_front_matter(md: str) -> tuple[str, str, list[tuple[str, str]], str]:
    """Peel the title block off the Markdown so HTML can render it as a cover.

    Nothing is dropped -- the same title, subtitle and metadata are re-laid out
    into the brand's cover component. The Markdown file itself is untouched.
    """
    lines = md.split("\n")
    title = subtitle = ""
    meta: list[tuple[str, str]] = []
    body_start = 0
    for i, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("## ") and not subtitle:
            subtitle = line[3:].strip()
        elif line.startswith("# ") and not title:
            title = line[2:].strip()
        elif MD_META.match(line):
            k, v = MD_META.match(line).groups()
            meta.append((k, v.strip()))
        elif line == "---":
            body_start = i + 1
            break
    return title, subtitle, meta, "\n".join(lines[body_start:])


def markdown_to_html(md: str) -> str:
    """Minimal Markdown -> HTML. Only the subset this report emits."""
    out, in_table = [], False
    for raw in md.split("\n"):
        line = raw.rstrip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set(":- ") and c for c in cells):
                continue  # separator row
            if not in_table:
                out.append("<table>")
                in_table = True
                tag = "th"
            else:
                tag = "td"
            row = "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells)
            out.append(f"<tr>{row}</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if not line.strip():
            continue
        if line.startswith("#"):
            lvl = len(line) - len(line.lstrip("#"))
            text = line[lvl:].strip()
            # "## 3.1 องค์กรที่ถูกแอบอ้าง..." -> a mono SEC // 3.1 label ahead of
            # the heading, which is how the guide numbers a section.
            m = SECTION_NO.match(text)
            if lvl == 2 and m:
                out.append(f'<h2><span class="sec-no">SEC // {m.group(1)}</span>'
                           f"{inline(m.group(2))}</h2>")
            else:
                out.append(f"<h{lvl}>{inline(text)}</h{lvl}>")
        elif line.startswith(">"):
            out.append(f"<blockquote>{inline(line.lstrip('> '))}</blockquote>")
        elif line.startswith("- "):
            out.append(f"<p class='li'>• {inline(line[2:])}</p>")
        elif line.startswith("---"):
            out.append("<hr>")
        else:
            out.append(f"<p>{inline(line)}</p>")
    if in_table:
        out.append("</table>")
    return "\n".join(out)


def inline(s: str) -> str:
    s = html.escape(s)
    s = MD_INLINE_LINK.sub(r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)
    return s


# Everything visual now comes from assets/brand/fnl-design-system.css via
# _brand. Only what is specific to *this* report's markup stays here.
EXTRA_CSS = _charts.CHART_CSS + """
.sec-no { display:block; font-family:var(--fnl-font-mono);
  font-size:var(--fnl-fs-micro); letter-spacing:var(--fnl-track-mono);
  color:var(--fnl-signal-ink); margin-bottom:2px; }
p.li { margin:0 0 var(--fnl-space-1); padding-left:var(--fnl-space-3); }
"""


def _inject_after_heading(html_body: str, heading_starts: str, chart: str) -> str:
    """Place a figure immediately after the section heading it illustrates.

    Charts live only in the HTML/PDF; the Markdown stays a plain-text report that
    reads correctly in a terminal or a diff. Injection is done on the converted
    HTML rather than by embedding raw SVG in the Markdown, because the Markdown
    converter escapes HTML by design and should keep doing so.
    """
    if not chart:
        return html_body
    idx = html_body.find(heading_starts)
    if idx == -1:
        return html_body
    close = html_body.find("</h2>", idx)
    if close == -1:
        return html_body
    cut = close + len("</h2>")
    return html_body[:cut] + chart + html_body[cut:]


def build_charts(cur: list[dict], neg: list[dict], start: str, end: str) -> dict:
    """Every figure the report can show, keyed by the section it belongs to."""
    by_theme = Counter(theme_of(c["claim"]) for c in neg)
    by_source = Counter(c["source"] for c in cur)
    by_label = Counter(c["label"] for c in cur)
    daily = Counter(c["date"] for c in neg if c["date"])
    impers = impersonation_counts(neg)

    verdict_parts = [
        (LABEL_TH["false"], by_label.get("false", 0), _charts.STATUS["false"]),
        (LABEL_TH["misleading"], by_label.get("misleading", 0), _charts.STATUS["misleading"]),
        (LABEL_TH["altered_media"], by_label.get("altered_media", 0), _charts.STATUS["altered_media"]),
        (LABEL_TH["true"], by_label.get("true", 0), _charts.STATUS["true"]),
        (LABEL_TH["unknown"], by_label.get("unknown", 0), _charts.STATUS["unknown"]),
    ]
    return {
        "timeline": _charts.timeline(dict(daily), start, end,
                                     title="ปริมาณข่าวลวงที่ถูกตรวจสอบรายวัน"),
        "themes": _charts.hbar(by_theme.most_common(), title="หมวดข่าวลวง"),
        "impersonation": _charts.hbar([(n, len(v)) for n, v in impers],
                                      unit="ครั้ง", title="องค์กรที่ถูกแอบอ้าง",
                                      label_width=210),
        "verdicts": _charts.stacked_share(verdict_parts,
                                          title="สัดส่วนผลการตรวจสอบ"),
        "sources": _charts.hbar([(SOURCE_TH.get(s, s), n)
                                 for s, n in by_source.most_common()],
                                title="สำนักที่ตรวจสอบ", label_width=210),
    }


def _with_charts(html_body: str, ch: dict, P: dict) -> str:
    # markdown_to_html lifts the section number into <span class="sec-no">SEC // N</span>,
    # so anchor on that rather than on the raw "3.1 ..." text the Markdown carried.
    for marker, key in (("SEC // 1</span>", "timeline"),
                        ("SEC // 3</span>", "themes"),
                        ("SEC // 3.1</span>", "impersonation"),
                        ("SEC // 4</span>", "verdicts"),
                        ("SEC // 5</span>", "sources")):
        html_body = _inject_after_heading(html_body, marker, ch[key])
    return html_body


def render_html(md: str, cur: list[dict], neg: list[dict], recirc,
                start: str, end: str, *, economy: bool = False) -> str:
    """Wrap the converted Markdown in the Fake News Lab document shell."""
    _P = period_labels(start, end)
    title, subtitle, meta, body_md = split_front_matter(md)
    chips = [
        _brand.chip(f"ข่าวลวง{_P['this_th']} {len(neg)} เรื่อง", "alert"),
        _brand.chip(f"ตรวจสอบทั้งหมด {len(cur)} เรื่อง"),
    ]
    if recirc:
        chips.append(_brand.chip(f"เวียนซ้ำ {len(recirc)} เรื่อง", "arrow"))
    body = (
        _brand.cover(f"รายงาน{_P['th']} · {_P['en']} REPORT",
                     title or f"รายงานสถานการณ์ข่าวลวง{_P['th']}",
                     subtitle=subtitle, chips=chips, meta=meta)
        + _brand.sys_rule(f"SYS // {_P['en']}", f"{start} → {end}")
        + _with_charts(markdown_to_html(body_md),
                       build_charts(cur, neg, start, end), _P)
        + _brand.footer(
            f"{_brand.ORG_TH} · {_brand.ORG_EN}",
            f"TH VERIFY ARCHIVE · {start} → {end}")
    )
    return _brand.document(
        f"รายงานข่าวลวง{_P['th']} {start} – {end}",
        f'<div class="fnl-doc">{body}</div>',
        economy=economy, extra_css=EXTRA_CSS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--outdir", type=Path, default=OUTPUT_DIR)
    ap.add_argument("--print-economy", action="store_true",
                    help="render the opt-in light variant (white paper) instead "
                         "of the brand's black base — for desk printing only")
    args = ap.parse_args()

    end = args.end or datetime.now().strftime("%Y-%m-%d")
    start = args.start or (datetime.strptime(end, "%Y-%m-%d")
                           - timedelta(days=args.days)).strftime("%Y-%m-%d")
    # The comparison window must match the length of the reporting window, not
    # --days. With an explicit --start/--end the two diverge: asking for July
    # compared a 31-day month against the 7 days before it and reported "+356%".
    span_days = (datetime.strptime(end, "%Y-%m-%d")
                 - datetime.strptime(start, "%Y-%m-%d")).days
    prev_start = (datetime.strptime(start, "%Y-%m-%d")
                  - timedelta(days=span_days)).strftime("%Y-%m-%d")

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    assert_fresh(con)

    cur = fetch(con, start, end)
    prev = fetch(con, prev_start, start)
    print(f"window {start} .. {end}: {len(cur)} records "
          f"(previous week {len(prev)})")

    neg = [c for c in cur if c["label"] in NEGATIVE]
    print(f"  negative-label claims: {len(neg)}")
    recirc = find_recirculating(neg, start) if neg else []
    print(f"  recirculating: {len(recirc)}")

    narrative = None
    if not args.no_llm and neg:
        by_theme = Counter(theme_of(c["claim"]) for c in neg)
        print("  drafting narrative via local LLM ...")
        narrative = llm_narrative(cur, {
            "total": len(cur), "negative": len(neg),
            "top_theme": by_theme.most_common(1)[0][0] if by_theme else "—",
            "recirculating": len(recirc)}, period_labels(start, end))
    con.close()

    md = build_markdown(cur, prev, recirc, narrative, start, end)
    args.outdir.mkdir(parents=True, exist_ok=True)
    stem = f"weekly_fakenews_{start}_to_{end}"
    md_path = args.outdir / f"{stem}.md"
    html_path = args.outdir / f"{stem}.html"
    pdf_path = args.outdir / f"{stem}.pdf"

    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(render_html(md, cur, neg, recirc, start, end,
                                     economy=args.print_economy),
                         encoding="utf-8")

    print(f"\nmarkdown : {md_path}")
    print(f"html     : {html_path}")
    if write_pdf(html_path, pdf_path):
        print(f"pdf      : {pdf_path} ({pdf_path.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
