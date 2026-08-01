#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asr_sample.py — build a human-reviewable sample of pipeline labels.

Auditing a machine label should not require watching the video. Every accepted
record carries the transcript and the exact quote the verdict was drawn from, so
a reviewer can usually agree or disagree by reading two lines. This renders that
into a clickable page.

Sampling is stratified by verdict rather than proportional, because the classes
carry different risk. 'true' is the one to scrutinise: it is the minority class,
it is the one an earlier prompt got wrong 80% of the time, and mislabelling a
debunk as true is the most damaging error the pipeline can make.

    python scripts/asr/asr_sample.py full_results.jsonl --out sample.html
"""

from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path

LABEL_TH = {"false": "ปลอม", "true": "จริง",
            "misleading": "บิดเบือน", "altered_media": "ภาพ/คลิปดัดแปลง"}
COLOR = {"false": "#dc2626", "true": "#16a34a",
         "misleading": "#d97706", "altered_media": "#7c3aed"}

CSS = """
body{font-family:"Sarabun","Noto Sans Thai",-apple-system,sans-serif;
 max-width:900px;margin:0 auto;padding:24px;line-height:1.6;color:#111}
h1{font-size:22px;margin-bottom:4px}
.sub{color:#666;font-size:14px;margin-bottom:24px}
.grp{font-size:17px;margin:28px 0 6px;padding-bottom:6px;border-bottom:2px solid #111}
.card{border:1px solid #e5e7eb;border-radius:8px;padding:14px 16px;margin:10px 0}
.v{display:inline-block;color:#fff;padding:2px 10px;border-radius:12px;
 font-size:13px;font-weight:600;margin-bottom:6px}
.t{font-weight:600;margin:4px 0 8px}
.q{background:#f8fafc;border-left:3px solid #cbd5e1;padding:8px 12px;
 margin:8px 0;font-size:14px;color:#334155}
.q b{color:#111}
a{color:#1d4ed8;text-decoration:none;font-size:13px}
.hint{background:#fffbeb;border:1px solid #fde68a;border-radius:6px;
 padding:10px 14px;font-size:14px;margin:16px 0}
@media(prefers-color-scheme:dark){
 body{background:#0b0f19;color:#e5e7eb}
 .card{border-color:#1f2937;background:#111827}
 .q{background:#0f172a;border-left-color:#334155;color:#cbd5e1}
 .q b{color:#f3f4f6}
 .hint{background:#1c1917;border-color:#78350f;color:#fde68a}
 .grp{border-bottom-color:#e5e7eb}
 a{color:#93c5fd}}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--per-class", type=int, default=12)
    ap.add_argument("--true-extra", type=int, default=8,
                    help="extra 'true' samples; it is the highest-risk class")
    args = ap.parse_args()

    recs = [json.loads(l) for l in args.results.read_text(encoding="utf-8").splitlines() if l.strip()]
    by: dict[str, list] = defaultdict(list)
    for r in recs:
        if r.get("status") == "labelled":
            by[r["verdict"]].append(r)

    parts = [f"<h1>ตรวจสอบตัวอย่างผลจากระบบถอดเสียง</h1>",
             f"<div class='sub'>Spot-check sample &mdash; "
             f"{sum(len(v) for v in by.values()):,} labels total, "
             f"showing a stratified sample. Nothing is written to the database yet.</div>",
             "<div class='hint'><b>How to check:</b> read the quote &mdash; it is copied "
             "verbatim from what the host actually said in the closing seconds. "
             "If the quote supports the verdict, the label is good. "
             "Open the video only when the quote looks ambiguous.</div>"]

    order = ["true", "misleading", "false", "altered_media"]
    for verdict in order:
        items = by.get(verdict, [])
        if not items:
            continue
        n = args.per_class + (args.true_extra if verdict == "true" else 0)
        step = max(1, len(items) / n)
        picked = [items[int(i * step)] for i in range(min(n, len(items)))]
        parts.append(f"<div class='grp'>{LABEL_TH.get(verdict, verdict)} "
                     f"({verdict}) &mdash; showing {len(picked)} of {len(items)}</div>")
        for r in picked:
            q = html.escape(r.get("quote", ""))
            parts.append(
                "<div class='card'>"
                f"<span class='v' style='background:{COLOR.get(verdict,'#555')}'>"
                f"{LABEL_TH.get(verdict, verdict)}</span>"
                f"<div class='t'>{html.escape(r.get('title',''))}</div>"
                f"<div class='q'><b>ผู้ดำเนินรายการพูดว่า:</b><br>&ldquo;{q}&rdquo;</div>"
                f"<a href='{html.escape(r.get('url',''))}'>เปิดคลิปเพื่อตรวจสอบ &rarr;</a>"
                "</div>")

    args.out.write_text(
        f"<!doctype html><html lang='th'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Spot-check: ASR labels</title><style>{CSS}</style></head>"
        f"<body>{''.join(parts)}</body></html>", encoding="utf-8")
    print(f"wrote {args.out}")
    for v in order:
        if by.get(v):
            print(f"  {v:14} {len(by[v]):5} labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
