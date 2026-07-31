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


def llm_narrative(claims: list[dict], stats: dict) -> str | None:
    """Ask the local model for an editorial read of the week.

    Grounded deliberately: it receives only headlines from this window plus the
    computed counts, and is told not to introduce facts. Returns None on any
    failure so the report still builds without the GPU.
    """
    sample = "\n".join(f"- [{LABEL_TH.get(c['label'], c['label'])}] {c['claim'][:110]}"
                       for c in claims[:60])
    prompt = f"""คุณเป็นบรรณาธิการข่าวตรวจสอบข้อเท็จจริงของไทย
เขียนบทวิเคราะห์ภาพรวมข่าวลวงประจำสัปดาห์ ความยาว 3 ย่อหน้า

ข้อมูลสถิติสัปดาห์นี้:
- ตรวจสอบทั้งหมด {stats['total']} เรื่อง
- ข่าวปลอม/บิดเบือน/ดัดแปลง {stats['negative']} เรื่อง
- หมวดที่พบมากที่สุด: {stats['top_theme']}
- ข่าวลวงเวียนซ้ำจากอดีต {stats['recirculating']} เรื่อง

รายการข่าวที่ตรวจสอบสัปดาห์นี้:
{sample}

กติกา:
- วิเคราะห์เฉพาะจากรายการข้างต้นเท่านั้น ห้ามเพิ่มข้อมูลหรือตัวเลขที่ไม่ได้ให้มา
- ย่อหน้า 1: ภาพรวมและแนวโน้มเด่นของสัปดาห์
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
    A("# รายงานสถานการณ์ข่าวลวงรายสัปดาห์")
    A("## TH Verify Weekly Misinformation Report")
    A("")
    A(f"**ช่วงข้อมูล:** {start} ถึง {end}  ")
    A(f"**จัดทำเมื่อ:** {datetime.now():%Y-%m-%d %H:%M}  ")
    A(f"**แหล่งข้อมูล:** คลังตรวจสอบข้อเท็จจริง TH Verify "
      f"({', '.join(SOURCE_TH[s] for s in by_source)})")
    A("")
    A("---")
    A("")
    A("## 1. ภาพรวมสัปดาห์นี้")
    A("")
    A(f"| ตัวชี้วัด | สัปดาห์นี้ | สัปดาห์ก่อน | เปลี่ยนแปลง |")
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
        A("> *บทวิเคราะห์ส่วนนี้ร่างโดยโมเดลภาษาท้องถิ่นจากรายการข่าวในสัปดาห์นี้เท่านั้น "
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
          "หน่วยงานที่ถูกแอบอ้างซ้ำหลายครั้งในสัปดาห์เดียว "
          "บ่งชี้ว่ากำลังตกเป็นเป้าของแคมเปญหลอกลวง ไม่ใช่เหตุการณ์เดี่ยว")
        A("")
        A("| หน่วยงานที่ถูกแอบอ้าง | จำนวนครั้ง |")
        A("| :--- | ---: |")
        for name, items in impers:
            A(f"| {name} | {len(items)} |")
        A("")
        top_name, top_items = impers[0]
        if len(top_items) > 1:
            A(f"**ข้อสังเกต:** {top_name} ถูกแอบอ้างถึง {len(top_items)} ครั้งในสัปดาห์เดียว "
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
        A("ข่าวลวงที่ถูกตรวจสอบไปแล้วในอดีต แต่กลับมาแพร่ซ้ำในสัปดาห์นี้ "
          "เป็นสัญญาณว่าการแก้ข่าวครั้งแรกยังเข้าไม่ถึงผู้รับสาร")
        A("")
        A("| ข่าวสัปดาห์นี้ | เคยตรวจสอบเมื่อ | ความคล้าย |")
        A("| :--- | :--- | ---: |")
        for c, first in recirc[:12]:
            A(f"| [{c['claim'][:80]}]({c['url']}) | {first['date']} | {first['score']:.2f} |")
        A("")

    if ai_items:
        A(f"## 7. ข่าวลวงที่เกี่ยวข้องกับ AI ({len(ai_items)} เรื่อง)")
        A("")
        for c in ai_items[:10]:
            A(f"- **[{LABEL_TH.get(c['label'], c['label'])}]** "
              f"[{c['claim'][:100]}]({c['url']}) — {SOURCE_TH.get(c['source'], c['source'])}, {c['date']}")
        A("")

    A("## 8. รายการข่าวลวงทั้งหมดในสัปดาห์นี้")
    A("")
    A("| วันที่ | ผลตรวจสอบ | เรื่อง | สำนัก |")
    A("| :--- | :--- | :--- | :--- |")
    for c in sorted(neg, key=lambda x: x["date"], reverse=True):
        A(f"| {c['date']} | {LABEL_TH.get(c['label'], c['label'])} | "
          f"[{c['claim'][:90]}]({c['url']}) | {SOURCE_TH.get(c['source'], c['source'])} |")
    A("")
    A("---")
    A("")
    A("*รายงานนี้สร้างจากคลังข้อมูล TH Verify โดยนับเฉพาะผลการตรวจสอบที่สำนักข่าวระบุเอง "
      "หรือผ่านการตรวจโดยมนุษย์ ผลที่ได้จากการเดาด้วยคีย์เวิร์ดถูกตัดออกจากรายงานนี้ตามนโยบาย*")
    return "\n".join(L)


MD_INLINE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


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
            out.append(f"<h{lvl}>{inline(line[lvl:].strip())}</h{lvl}>")
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


CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: "Sarabun","Noto Sans Thai","Helvetica Neue",sans-serif;
       font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; }
h1 { font-size: 20pt; margin: 0 0 2pt; color: #0f172a; }
h2 { font-size: 13pt; margin: 16pt 0 6pt; padding-bottom: 3pt;
     border-bottom: 2px solid #0f172a; color: #0f172a; }
h3 { font-size: 11pt; margin: 10pt 0 4pt; }
p { margin: 0 0 6pt; }
p.li { margin: 0 0 3pt; padding-left: 8pt; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 12pt;
        font-size: 9pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th { background: #0f172a; color: #fff; text-align: left; padding: 5pt 6pt;
     font-weight: 600; }
td { border-bottom: 1px solid #e2e8f0; padding: 4pt 6pt; vertical-align: top; }
tr:nth-child(even) td { background: #f8fafc; }
a { color: #1d4ed8; text-decoration: none; }
blockquote { border-left: 3px solid #cbd5e1; margin: 8pt 0; padding: 4pt 10pt;
             color: #475569; font-size: 9pt; background: #f8fafc; }
hr { border: 0; border-top: 1px solid #cbd5e1; margin: 12pt 0; }
"""


def write_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Print the HTML to PDF with headless Chrome.

    Chrome is used because no Python PDF library is installed here and, more
    importantly, it shapes Thai script correctly -- most lightweight PDF writers
    render Thai vowels and tone marks in the wrong positions.
    """
    chrome = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not Path(chrome).exists():
        print("  (PDF skipped: Google Chrome not found)", file=sys.stderr)
        return False
    try:
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri()],
            check=True, capture_output=True, timeout=120)
        return pdf_path.exists()
    except Exception as exc:
        print(f"  (PDF failed: {exc})", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--outdir", type=Path, default=OUTPUT_DIR)
    args = ap.parse_args()

    end = args.end or datetime.now().strftime("%Y-%m-%d")
    start = args.start or (datetime.strptime(end, "%Y-%m-%d")
                           - timedelta(days=args.days)).strftime("%Y-%m-%d")
    prev_start = (datetime.strptime(start, "%Y-%m-%d")
                  - timedelta(days=args.days)).strftime("%Y-%m-%d")

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
            "recirculating": len(recirc)})
    con.close()

    md = build_markdown(cur, prev, recirc, narrative, start, end)
    args.outdir.mkdir(parents=True, exist_ok=True)
    stem = f"weekly_fakenews_{start}_to_{end}"
    md_path = args.outdir / f"{stem}.md"
    html_path = args.outdir / f"{stem}.html"
    pdf_path = args.outdir / f"{stem}.pdf"

    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(
        f"<!doctype html><html lang='th'><head><meta charset='utf-8'>"
        f"<title>รายงานข่าวลวงรายสัปดาห์ {start} – {end}</title>"
        f"<style>{CSS}</style></head><body>{markdown_to_html(md)}</body></html>",
        encoding="utf-8")

    print(f"\nmarkdown : {md_path}")
    print(f"html     : {html_path}")
    if write_pdf(html_path, pdf_path):
        print(f"pdf      : {pdf_path} ({pdf_path.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
