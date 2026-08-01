#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_brand.py — Fake News Lab brand assets for the HTML/PDF report builders.

One stylesheet, one mark, loaded from assets/brand/ and inlined into whatever
the builders write. Inlining rather than <link>ing is deliberate: the reports
are printed to PDF by headless Chrome over file:// and are handed to clients as
single files, so a relative stylesheet reference would break the moment the
file moved. Nothing here touches the network.

Usage:

    from _brand import document, cover, sys_rule

    html = document("รายงาน...", cover(...) + body_html)
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

BRAND_DIR = Path(__file__).resolve().parent.parent / "assets" / "brand"
CSS_PATH = BRAND_DIR / "fnl-design-system.css"
LOGO_PATH = BRAND_DIR / "fnl-logo.svg"
LOGO_ICON_PATH = BRAND_DIR / "fnl-logo-icon.svg"

ORG_TH = "ห้องปฏิบัติการข่าวปลอม"
ORG_EN = "FAKE NEWS LAB"
TAGLINE_TH = "ความจริงต้องมีโครงสร้างพื้นฐาน"

# The opt-in light rendering. Reports stay black unless a caller asks for this
# explicitly (--print-economy on the CLI); the brand is never silently inverted.
ECONOMY_CLASS = "fnl-print-economy"


@lru_cache(maxsize=None)
def css() -> str:
    """The design system, read once."""
    return CSS_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def _logo_source(icon: bool) -> str:
    return (LOGO_ICON_PATH if icon else LOGO_PATH).read_text(encoding="utf-8").strip()


def mark(size: int = 40, *, icon: bool = False) -> str:
    """The X mark as an inline <svg>, sized in px."""
    svg = _logo_source(icon)
    svg = re.sub(r'\swidth="[^"]*"\sheight="[^"]*"',
                 f' width="{size}" height="{size}"', svg, count=1)
    return svg.replace("\n", "")


def favicon_data_uri() -> str:
    """The icon mark as a data: URI — no file fetch, no emoji placeholder."""
    svg = _logo_source(True).replace("\n", "").replace('"', "'")
    for ch, esc in (("%", "%25"), ("#", "%23"), ("<", "%3C"), (">", "%3E")):
        svg = svg.replace(ch, esc)
    return "data:image/svg+xml," + svg


def sys_rule(label: str, ident: str = "") -> str:
    """A `SYS // 001` style mono rule that runs to the edge of the column."""
    id_html = f'<span class="fnl-sys__id">{ident}</span>' if ident else ""
    return f'<div class="fnl-sys"><span>{label}</span>{id_html}</div>'


def chip(text: str, kind: str = "") -> str:
    """A yellow signal chip. kind: "" (signal), "alert", "mute", "arrow"."""
    cls = "fnl-chip" + (f" fnl-chip--{kind}" if kind else "")
    return f'<span class="{cls}">{text}</span>'


def cover(kicker: str, title: str, *, subtitle: str = "",
          meta: list[tuple[str, str]] | None = None,
          chips: list[str] | None = None,
          tagline: bool = True) -> str:
    """Cover block: mark + org lockup, kicker, title, signal chips, metadata.

    `title` and `subtitle` are inserted as HTML so a caller can wrap a word in
    <em> for the Signal Red emphasis the guide asks for on covers. `chips` is
    the risk signal — the first step of the guide's communication formula
    (ส่งสัญญาณความเสี่ยง → แสดงหลักฐาน → บอกว่าควรทำอะไรต่อ).
    """
    rows = "".join(f"<div><dt>{k}</dt><dd>{v}</dd></div>" for k, v in (meta or []))
    meta_html = f'<dl class="fnl-metablock">{rows}</dl>' if rows else ""
    sub_html = f'<p class="fnl-cover__sub">{subtitle}</p>' if subtitle else ""
    chips_html = (f'<p class="fnl-cover__chips">{" ".join(chips)}</p>'
                  if chips else "")
    tag_html = (f'<p class="fnl-tagline">{ORG_EN} · <b>{TAGLINE_TH}</b></p>'
                if tagline else "")
    return (
        '<header class="fnl-cover">'
        '<div class="fnl-cover__brand">'
        f'{mark(46)}'
        f'<div class="fnl-cover__org">{ORG_TH}<span>{ORG_EN}</span></div>'
        "</div>"
        f'<div class="fnl-cover__kicker">{kicker}</div>'
        f'<h1 class="fnl-cover__title">{title}</h1>'
        f"{sub_html}{chips_html}{tag_html}{meta_html}"
        "</header>"
    )


def footer(left: str, right: str = "") -> str:
    return (f'<footer class="fnl-footer"><span>{left}</span>'
            f"<span>{right}</span></footer>")


STATIC_PAGES = [
    Path(__file__).resolve().parent.parent / "src" / "th_verify" / "static" / p
    for p in ("index.html", "review.html")
]
# Deliberately anchored to a newline-preceded tag and non-greedy: an earlier
# version matched the same marker inside the explanatory HTML comment above the
# block and swallowed everything between comment and stylesheet, which silently
# blanked both pages. Keep the marker out of prose.
_STYLE_BLOCK = re.compile(
    r"(\n<style data-fnl-design-system>)(.*?)(\n</style>)", re.S)


def sync_static() -> int:
    """Inline the canonical stylesheet into the FastAPI-served static pages.

    Those two pages are returned by FileResponse with no static mount, so they
    cannot <link> to anything, and the brand forbids a CDN. They therefore carry
    a copy of the stylesheet, and this keeps the copy honest. Run it after every
    change to fnl-design-system.css.
    """
    payload = ("\n/* ===== GENERATED — do not edit here. Source of truth: "
               "assets/brand/fnl-design-system.css\n"
               "   Re-inline with: python scripts/_brand.py sync-static ===== */\n"
               + css())
    changed = 0
    for page in STATIC_PAGES:
        src = page.read_text(encoding="utf-8")
        if not _STYLE_BLOCK.search(src):
            print(f"  !! no <style data-fnl-design-system> block in {page.name}")
            continue
        out = _STYLE_BLOCK.sub(lambda m: m.group(1) + payload + m.group(3), src, count=1)
        if out != src:
            page.write_text(out, encoding="utf-8")
            changed += 1
        print(f"  {page.name}: {'updated' if out != src else 'already current'}")
    return changed


def document(title: str, body: str, *, lang: str = "th", body_class: str = "",
             economy: bool = False, head_extra: str = "",
             extra_css: str = "") -> str:
    """A complete, self-contained brand document."""
    html_class = f' class="{ECONOMY_CLASS}"' if economy else ""
    body_attr = f' class="{body_class}"' if body_class else ""
    # @page cannot be scoped to a class, so the light variant's page-box colour
    # has to be appended rather than selected.
    page_override = "@page { background: #FFFFFF; }" if economy else ""
    style = f"<style>{css()}{extra_css}{page_override}</style>"
    return (
        f"<!doctype html>\n<html lang='{lang}'{html_class}>\n<head>\n"
        f'<meta charset="utf-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f'<link rel="icon" href="{favicon_data_uri()}">\n'
        f"{style}\n{head_extra}\n</head>\n<body{body_attr}>\n{body}\n</body>\n</html>\n"
    )


if __name__ == "__main__":
    import sys as _sys
    if _sys.argv[1:2] == ["sync-static"]:
        print("inlining fnl-design-system.css into the served static pages")
        sync_static()
    else:
        print(__doc__)
        print("commands:\n  sync-static   re-inline the stylesheet into "
              "src/th_verify/static/*.html")
