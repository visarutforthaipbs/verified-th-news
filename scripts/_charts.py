#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_charts.py — inline SVG charts for Fake News Lab reports.

Pure string-built SVG: no chart library, no JavaScript, no network. The reports
are printed to PDF by headless Chrome and are mailed around as standalone files,
so anything requiring a runtime or a fetch would render as a blank box in the
document that matters most.

Design decisions, and why
-------------------------
* **Magnitude charts use one hue, not a palette.** Theme counts, impersonation
  counts and source counts are a single measure compared across categories. Giving
  each bar its own colour would encode rank as identity -- the colour would change
  meaning whenever the ordering changed. One red, sorted, with the value written
  on the bar.
* **Verdicts use the status palette** (red=false, yellow=misleading, white=true,
  grey=residual) because there the category *is* the meaning, and those four roles
  are already fixed by the identity guide and used elsewhere in the system.
  Status colour never travels alone: every segment is labelled.
* **Direct labels everywhere, no y-axis of numbers.** The guide asks for charts
  that are simple and high-contrast; a value at the end of each bar removes a
  whole axis and the eye movement that goes with it.
* Bars carry an SVG <title>, which browsers surface as a native tooltip at no
  cost and which print ignores.

Palette note: validated against the brand's black surface with the dataviz
validator -- CVD separation ΔE 19.2, normal-vision 19.8, all four ≥ 3:1 contrast.
Its lightness-band and chroma-floor checks are categorical-palette rules and do
not apply to a status palette containing deliberate neutrals.
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta

RED = "var(--fnl-red, #F20D1B)"
YELLOW = "var(--fnl-yellow, #FFD400)"
WHITE = "var(--fnl-white, #F2F2F2)"
GRAY = "var(--fnl-gray, #7A7A7A)"
INK = "var(--fnl-white, #F2F2F2)"
MUTED = "var(--fnl-gray, #7A7A7A)"
SURFACE = "var(--fnl-black, #000000)"

# The palette has five colours and the verdict set has five members, two of
# which would otherwise both land on grey -- "ภาพ/คลิปดัดแปลง" and "ยังไม่ระบุผล"
# rendered identically in the same chart, so the legend could not tell them
# apart. altered_media takes a hatched fill instead: a distinct mark without
# inventing a sixth brand colour, and it doubles as the texture channel the
# accessibility pass wants for colourblind and forced-colour readers. The
# diagonal stripe is already in the identity guide as a caution motif.
HATCH_ID = "fnlHatch"
HATCH = f'url(#{HATCH_ID})'
STATUS = {"false": RED, "misleading": YELLOW, "true": WHITE,
          "altered_media": HATCH, "other": GRAY, "unknown": GRAY}

HATCH_DEF = (
    f'<defs><pattern id="{HATCH_ID}" width="6" height="6" '
    f'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
    f'<rect width="6" height="6" fill="{SURFACE}"/>'
    f'<rect width="3" height="6" fill="{GRAY}"/></pattern></defs>')

# 4px rounded data-end anchored to the baseline, per the mark spec.
RADIUS = 4


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _wrap(inner: str, width: int, height: int, title: str, desc: str = "") -> str:
    return (
        f'<figure class="fnl-fig">'
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="auto" '
        f'role="img" aria-label="{_esc(title)}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="var(--fnl-font-body)">'
        + HATCH_DEF
        + f"<title>{_esc(title)}</title>"
        + (f"<desc>{_esc(desc)}</desc>" if desc else "")
        + inner + "</svg></figure>")


def hbar(rows: list[tuple[str, int]], *, title: str = "", unit: str = "เรื่อง",
         color: str | None = None, max_rows: int = 12,
         label_width: int = 240) -> str:
    """Horizontal bars, one hue, sorted, value written at the bar end.

    Horizontal because Thai category names are long and unabbreviable; rotating
    them under a column chart would make them unreadable.
    """
    rows = [r for r in rows if r[1] > 0][:max_rows]
    if not rows:
        return ""
    bar_h, gap, pad_t, pad_b = 26, 10, 6, 6
    width = 760
    plot_x = label_width + 12
    plot_w = width - plot_x - 64
    height = pad_t + len(rows) * (bar_h + gap) - gap + pad_b
    top = max(v for _, v in rows)
    fill = color or RED

    out = []
    for i, (label, value) in enumerate(rows):
        y = pad_t + i * (bar_h + gap)
        w = max(3, round(value / top * plot_w))
        out.append(
            f'<text x="{label_width}" y="{y + bar_h * 0.68}" text-anchor="end" '
            f'font-size="13" fill="{INK}">{_esc(label)}</text>')
        out.append(
            f'<rect x="{plot_x}" y="{y}" width="{w}" height="{bar_h}" '
            f'rx="{RADIUS}" ry="{RADIUS}" fill="{fill}">'
            f"<title>{_esc(label)}: {value} {_esc(unit)}</title></rect>")
        out.append(
            f'<text x="{plot_x + w + 8}" y="{y + bar_h * 0.68}" font-size="13" '
            f'font-weight="600" fill="{INK}">{value}</text>')
    return _wrap("".join(out), width, height, title or "แผนภูมิแท่ง",
                 f"{len(rows)} รายการ สูงสุด {top} {unit}")


def stacked_share(parts: list[tuple[str, int, str]], *, title: str = "",
                  unit: str = "เรื่อง") -> str:
    """One horizontal bar split into labelled shares.

    Used for the verdict mix. A pie would force angle comparison; a single
    stacked bar keeps it a length comparison and fits the page width. A 2px
    surface gap separates segments per the mark spec.
    """
    parts = [p for p in parts if p[1] > 0]
    if not parts:
        return ""
    total = sum(p[1] for p in parts)
    width, bar_h, legend_h = 760, 38, 46
    height = bar_h + legend_h + 16
    out, x = [], 0
    for name, value, color in parts:
        w = value / total * width
        out.append(
            f'<rect x="{x:.1f}" y="0" width="{max(0, w - 2):.1f}" height="{bar_h}" '
            f'fill="{color}"><title>{_esc(name)}: {value} {_esc(unit)} '
            f'({value / total * 100:.0f}%)</title></rect>')
        # Only label in-bar when the segment can hold the text.
        if w > 58:
            dark = color in (WHITE, YELLOW)
            out.append(
                f'<text x="{x + w / 2 - 1:.1f}" y="{bar_h * 0.64}" '
                f'text-anchor="middle" font-size="13" font-weight="700" '
                f'fill="{SURFACE if dark else INK}">'
                f"{value / total * 100:.0f}%</text>")
        x += w

    lx = 0
    for name, value, color in parts:
        out.append(f'<rect x="{lx}" y="{bar_h + 20}" width="11" height="11" '
                   f'rx="2" fill="{color}"/>')
        out.append(f'<text x="{lx + 17}" y="{bar_h + 30}" font-size="12.5" '
                   f'fill="{INK}">{_esc(name)} <tspan fill="{MUTED}">{value}</tspan></text>')
        lx += 30 + len(name) * 8.6 + len(str(value)) * 7
    return _wrap("".join(out), width, height, title or "สัดส่วนผลการตรวจสอบ",
                 f"รวม {total} {unit}")


def timeline(counts: dict[str, int], start: str, end: str, *,
             title: str = "", unit: str = "เรื่อง") -> str:
    """Daily volume as columns across the window.

    Change-over-time, so position-on-a-common-axis. Columns rather than a line
    because the series is a count of discrete events per day, and gaps (days with
    no publication) should read as gaps rather than being interpolated across.
    """
    d0 = datetime.strptime(start, "%Y-%m-%d")
    d1 = datetime.strptime(end, "%Y-%m-%d")
    days = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((d1 - d0).days)]
    if not days:
        return ""
    vals = [counts.get(d, 0) for d in days]
    top = max(vals) or 1
    width, plot_h, pad_b = 760, 120, 30
    height = plot_h + pad_b + 14
    slot = width / len(days)
    bw = max(2.0, slot - 2)

    out = [f'<line x1="0" y1="{plot_h}" x2="{width}" y2="{plot_h}" '
           f'stroke="{MUTED}" stroke-width="1" opacity="0.45"/>']
    peak_i = vals.index(top)
    for i, (d, v) in enumerate(zip(days, vals)):
        h = 0 if v == 0 else max(2, v / top * plot_h)
        x = i * slot
        # Built outside the f-string: an escaped quote inside an f-string
        # expression is a syntax error before Python 3.12 and this venv is 3.11.
        is_peak = i == peak_i
        fill = RED if is_peak else GRAY
        opacity = "" if is_peak else ' opacity="0.75"'
        out.append(
            f'<rect x="{x:.1f}" y="{plot_h - h:.1f}" width="{bw:.1f}" '
            f'height="{h:.1f}" rx="2" fill="{fill}"{opacity}>'
            f"<title>{d}: {v} {_esc(unit)}</title></rect>")
    # Label only the ends and the peak — never a number on every column.
    out.append(f'<text x="0" y="{plot_h + 16}" font-size="11" fill="{MUTED}">'
               f"{days[0][5:]}</text>")
    out.append(f'<text x="{width}" y="{plot_h + 16}" text-anchor="end" '
               f'font-size="11" fill="{MUTED}">{days[-1][5:]}</text>')
    px = peak_i * slot + bw / 2
    out.append(
        f'<text x="{min(max(px, 30), width - 30):.1f}" y="{plot_h - (top / top * plot_h) - 6:.1f}" '
        f'text-anchor="middle" font-size="12" font-weight="700" fill="{RED}">'
        f"{top}</text>")
    out.append(f'<text x="{min(max(px, 30), width - 30):.1f}" y="{plot_h + 16}" '
               f'text-anchor="middle" font-size="11" fill="{RED}">'
               f"{days[peak_i][5:]}</text>")
    return _wrap("".join(out), width, height, title or "ปริมาณรายวัน",
                 f"สูงสุด {top} {unit} เมื่อ {days[peak_i]}")


def columns(rows: list[tuple[str, int]], *, title: str = "", unit: str = "เรื่อง",
            highlight: str | None = None, note: str = "") -> str:
    """Named columns across a common baseline — a short, ordered series.

    `timeline` above is the daily version and takes a date range; this one takes
    the categories already named (years, months, quarters), which is what a
    multi-year series needs: a decade of daily columns would be 3,650 slivers.

    Every column is labelled underneath because the set is short enough to
    afford it, but only the peak carries its value, plus `highlight` if given —
    a partial final year, say, which must not be read as a fall.
    """
    rows = [r for r in rows if r[0] is not None]
    if not rows:
        return ""
    vals = [v for _, v in rows]
    top = max(vals) or 1
    width, plot_h, pad_b = 760, 150, 34
    height = plot_h + pad_b + 16
    slot = width / len(rows)
    bw = min(64.0, max(6.0, slot - 14))

    peak_i = vals.index(top)
    out = [f'<line x1="0" y1="{plot_h}" x2="{width}" y2="{plot_h}" '
           f'stroke="{MUTED}" stroke-width="1" opacity="0.45"/>']
    for i, (label, v) in enumerate(rows):
        h = 0 if v == 0 else max(2, v / top * plot_h)
        x = i * slot + (slot - bw) / 2
        is_peak = i == peak_i
        is_hl = label == highlight
        fill = RED if is_peak else GRAY
        opacity = "" if is_peak or is_hl else ' opacity="0.75"'
        out.append(
            f'<rect x="{x:.1f}" y="{plot_h - h:.1f}" width="{bw:.1f}" '
            f'height="{h:.1f}" rx="{RADIUS}" fill="{fill}"{opacity}>'
            f"<title>{_esc(label)}: {v} {_esc(unit)}</title></rect>")
        if is_peak or is_hl:
            out.append(
                f'<text x="{x + bw / 2:.1f}" y="{plot_h - h - 7:.1f}" '
                f'text-anchor="middle" font-size="12.5" font-weight="700" '
                f'fill="{RED if is_peak else INK}">{v}</text>')
        out.append(
            f'<text x="{x + bw / 2:.1f}" y="{plot_h + 18}" text-anchor="middle" '
            f'font-size="11.5" fill="{RED if is_peak else MUTED}">{_esc(label)}</text>')
    if note:
        out.append(f'<text x="0" y="{plot_h + 34}" font-size="11" '
                   f'fill="{MUTED}">{_esc(note)}</text>')
    return _wrap("".join(out), width, height, title or "ปริมาณตามช่วงเวลา",
                 f"สูงสุด {top} {unit} ที่ {rows[peak_i][0]}")


def kpi_row(items: list[tuple[str, str, str | None, str]]) -> str:
    """Hero numbers: (label, value, delta, tone). Not a chart -- four numbers
    compared to nothing do not need axes, and a stat tile reads faster."""
    cells = []
    for label, value, delta, tone in items:
        color = {"up": RED, "down": WHITE, "flat": MUTED}.get(tone, MUTED)
        d = (f'<span class="fnl-kpi-delta" style="color:{color}">{_esc(delta)}</span>'
             if delta else "")
        cells.append(
            f'<div class="fnl-kpi"><div class="fnl-kpi-label">{_esc(label)}</div>'
            f'<div class="fnl-kpi-value">{_esc(value)}{d}</div></div>')
    return f'<div class="fnl-kpi-row">{"".join(cells)}</div>'


CHART_CSS = """
.fnl-fig { margin: var(--fnl-space-3) 0 var(--fnl-space-5); page-break-inside: avoid; }
.fnl-kpi-row { display: grid; grid-template-columns: repeat(4, 1fr);
  gap: var(--fnl-space-3); margin: var(--fnl-space-4) 0 var(--fnl-space-5); }
.fnl-kpi { border-left: 3px solid var(--fnl-red); padding-left: var(--fnl-space-3); }
.fnl-kpi-label { font-family: var(--fnl-font-mono); font-size: var(--fnl-fs-meta);
  letter-spacing: .06em; color: var(--fnl-gray); margin-bottom: .25em; }
.fnl-kpi-value { font-family: var(--fnl-font-head); font-size: 1.9rem;
  font-weight: 700; line-height: 1.1; color: var(--fnl-white); }
.fnl-kpi-delta { font-size: .95rem; font-weight: 600; margin-left: .45em; }
@media print { .fnl-kpi-row { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 640px) { .fnl-kpi-row { grid-template-columns: repeat(2, 1fr); } }
"""
