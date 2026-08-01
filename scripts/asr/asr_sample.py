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
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _brand  # noqa: E402

LABEL_TH = {"false": "ปลอม", "true": "จริง",
            "misleading": "บิดเบือน", "altered_media": "ภาพ/คลิปดัดแปลง"}
# Verdict colours come from the palette, not from a rainbow. Red is the alert
# (a debunk), yellow the indicator (a qualified verdict), white the plain
# statement, grey the residual — same four roles the guide gives them.
VERDICT_CLASS = {"false": "v-false", "true": "v-true",
                 "misleading": "v-misleading", "altered_media": "v-altered"}

# Only what is specific to this page; everything else is the design system.
EXTRA_CSS = """
.card { border:var(--fnl-rule) solid var(--fnl-line); background:var(--fnl-surface-1);
  padding:var(--fnl-space-4); margin:var(--fnl-space-3) 0; }
.v { display:inline-block; font-family:var(--fnl-font-mono);
  font-size:var(--fnl-fs-meta); letter-spacing:0.08em; font-weight:700;
  padding:0.15em 0.7em; margin-bottom:var(--fnl-space-2);
  border:var(--fnl-rule) solid currentColor; }
.v-false { color:var(--fnl-red); }
.v-misleading { color:var(--fnl-yellow); }
.v-true { color:var(--fnl-white); }
.v-altered { color:var(--fnl-gray); }
.t { font-weight:700; margin:var(--fnl-space-1) 0 var(--fnl-space-2); }
.q { background:var(--fnl-black); border-left:var(--fnl-rule-heavy) solid var(--fnl-gray);
  padding:var(--fnl-space-2) var(--fnl-space-3); margin:var(--fnl-space-2) 0;
  font-size:var(--fnl-fs-small); color:var(--fnl-white); }
.q b { color:var(--fnl-yellow); font-family:var(--fnl-font-mono);
  font-size:var(--fnl-fs-meta); letter-spacing:0.06em; }
.card a { font-family:var(--fnl-font-mono); font-size:var(--fnl-fs-meta);
  color:var(--fnl-red); border-bottom:0; }
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

    total_labels = sum(len(v) for v in by.values())
    parts = [
        _brand.cover(
            "การตรวจทานภายใน · INTERNAL SPOT-CHECK",
            "ตรวจสอบตัวอย่างผลจากระบบถอดเสียง",
            subtitle="ASR pipeline label spot-check",
            chips=[_brand.chip(f"{total_labels:,} LABELS"),
                   _brand.chip("ยังไม่บันทึกลงฐานข้อมูล", "mute")],
            meta=[("SOURCE", html.escape(args.results.name)),
                  ("SAMPLING", "stratified by verdict")]),
        '<div class="fnl-note fnl-note--signal">'
        "<b>How to check:</b> read the quote &mdash; it is copied "
        "verbatim from what the host actually said in the closing seconds. "
        "If the quote supports the verdict, the label is good. "
        "Open the video only when the quote looks ambiguous.</div>",
    ]

    order = ["true", "misleading", "false", "altered_media"]
    for verdict in order:
        items = by.get(verdict, [])
        if not items:
            continue
        n = args.per_class + (args.true_extra if verdict == "true" else 0)
        step = max(1, len(items) / n)
        picked = [items[int(i * step)] for i in range(min(n, len(items)))]
        parts.append(_brand.sys_rule(
            f"{LABEL_TH.get(verdict, verdict)} · {verdict}",
            f"{len(picked)} / {len(items)}"))
        for r in picked:
            q = html.escape(r.get("quote", ""))
            cls = VERDICT_CLASS.get(verdict, "v-altered")
            parts.append(
                "<div class='card'>"
                f"<span class='v {cls}'>{LABEL_TH.get(verdict, verdict)}</span>"
                f"<div class='t'>{html.escape(r.get('title',''))}</div>"
                f"<div class='q'><b>ผู้ดำเนินรายการพูดว่า:</b><br>&ldquo;{q}&rdquo;</div>"
                f"<a href='{html.escape(r.get('url',''))}'>เปิดคลิปเพื่อตรวจสอบ &rarr;</a>"
                "</div>")

    parts.append(_brand.footer(f"{_brand.ORG_TH} · {_brand.ORG_EN}",
                               "ASR SPOT-CHECK · INTERNAL"))
    args.out.write_text(
        _brand.document("Spot-check: ASR labels",
                        f'<div class="fnl-doc">{"".join(parts)}</div>',
                        extra_css=EXTRA_CSS),
        encoding="utf-8")
    print(f"wrote {args.out}")
    for v in order:
        if by.get(v):
            print(f"  {v:14} {len(by[v]):5} labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
