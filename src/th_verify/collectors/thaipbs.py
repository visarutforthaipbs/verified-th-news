from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from urllib.parse import urljoin, urlparse

from datetime import datetime
from selectolax.parser import HTMLParser

from ..models import FactCheckRecord
from .base import Collector

VERDICT_LABELS = ("ข่าวปลอม", "ข่าวบิดเบือน", "ข่าวจริง", "ภาพปลอม")


def parse_thai_date(text: str) -> str | None:
    if not text:
        return None
    months = {
        "ม.ค.": 1, "ก.พ.": 2, "มี.ค.": 3, "เม.ย.": 4, "พ.ค.": 5, "มิ.ย.": 6,
        "ก.ค.": 7, "ส.ค.": 8, "ก.ย.": 9, "ต.ค.": 10, "พ.ย.": 11, "ธ.ค.": 12
    }
    pattern = r"(\d{1,2})\s+(" + "|".join(re.escape(k) for k in months.keys()) + r")\s+(\d{2,4})"
    match = re.search(pattern, text)
    if not match:
        return None
    day = int(match.group(1))
    month_name = match.group(2)
    year_val = int(match.group(3))
    if year_val < 100:
        year_val += 2500
    christian_year = year_val - 543
    month = months[month_name]
    try:
        dt = datetime(christian_year, month, day)
        return dt.date().isoformat()
    except ValueError:
        return None


def parse_claim_reviewed(tree: HTMLParser) -> str | None:
    """The claim as Thai PBS themselves state it, from ClaimReview.claimReviewed.

    The article headline is written for readers and frequently contains the
    conclusion: "โพสต์อ้างข่าวปลอม ตำรวจยศสูงไหว้นักการเมือง ชี้เป็นภาพ AI ตรวจสอบพบ
    เป็นภาพจริง ปี 61". Stored as the claim, that teaches a model the answer and
    makes the review room show a summary where a claim belongs. claimReviewed for
    the same record is simply "ตำรวจยศสูงไหว้นักการเมือง".

    Often the two are identical -- Thai PBS reuses the headline when it is already
    claim-shaped -- so callers should keep the headline as `title` regardless and
    only let this fill `claim`.
    """
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.text())
        except (ValueError, TypeError):
            continue
        candidates = payload.get("@graph", []) if isinstance(payload, dict) else payload
        if isinstance(payload, dict) and not payload.get("@graph"):
            candidates = [payload]
        if not isinstance(candidates, list):
            continue
        for item in candidates:
            if isinstance(item, dict) and item.get("@type") == "ClaimReview":
                c = item.get("claimReviewed")
                if isinstance(c, str) and c.strip():
                    return c.strip()
    return None


def _spans_multiple_articles(node) -> bool:
    """True when a listing container covers more than one article card."""
    if node is None:
        return False
    seen = set()
    for anchor in node.css("a[href]"):
        path = urlparse(anchor.attributes.get("href", "")).path
        if "/verify/content/" in path:
            seen.add(path.rstrip("/"))
            if len(seen) > 1:
                return True
    return False


def parse_claim_review(tree: HTMLParser) -> tuple[str | None, str | None]:
    """Read the publisher's own schema.org ClaimReview block.

    Thai PBS Verify embeds a ClaimReview per article carrying the verdict as
    ``reviewRating.alternateName`` and the real publication date as
    ``datePublished``. Both are authoritative and per-article, unlike anything
    scraped from the listing page.

    ``ratingValue`` is deliberately ignored: articles have been observed with
    ``ratingValue: 5`` (the "best" end of the scale) alongside
    ``alternateName: ภาพปลอม``, so the numeric rating does not track the label.
    """
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            payload = json.loads(node.text())
        except (ValueError, TypeError):
            continue
        candidates = payload.get("@graph", []) if isinstance(payload, dict) else payload
        if isinstance(payload, dict) and not payload.get("@graph"):
            candidates = [payload]
        if not isinstance(candidates, list):
            continue
        for item in candidates:
            if not isinstance(item, dict) or item.get("@type") != "ClaimReview":
                continue
            rating = item.get("reviewRating") or {}
            verdict = rating.get("alternateName") if isinstance(rating, dict) else None
            published = item.get("datePublished")
            return (
                verdict.strip() if isinstance(verdict, str) and verdict.strip() else None,
                published.strip() if isinstance(published, str) and published.strip() else None,
            )
    return None, None


class ThaiPbsCollector(Collector):
    name = "thaipbs"
    base = "https://www.thaipbs.or.th/verify/category/all"

    async def detail(self, url: str) -> tuple[str, str | None, str | None, str | None, str | None]:
        response = await self.get(url)
        tree = HTMLParser(response.text)
        claim_verdict, claim_published = parse_claim_review(tree)
        claim_reviewed = parse_claim_reviewed(tree)
        article = tree.css_first("article.single-content")
        if not article:
            return "", claim_published, None, claim_verdict, claim_reviewed
        # Recommendations are nested after the authored content; drop them before text extraction.
        for selector in ("section.single-recommend", "section.single-author", "section.single-tags"):
            for node in article.css(selector):
                node.decompose()
        text = re.sub(r"\s+", " ", article.text(separator=" ", strip=True)).strip()
        image = tree.css_first('meta[property="og:image"]')
        published = tree.css_first('meta[property="article:published_time"]')
        meta_published = published.attributes.get("content") if published else None
        return (
            text,
            claim_published or meta_published,
            (image.attributes.get("content") if image else None),
            claim_verdict,
            claim_reviewed,
        )

    async def collect(self, *, mode: str = "delta", limit: int | None = None) -> AsyncIterator[FactCheckRecord]:
        page = 1
        emitted = 0
        seen: set[str] = set()
        while True:
            response = await self.get(self.base, params={"page": page} if page > 1 else None)
            tree = HTMLParser(response.text)
            candidates = []
            for a in tree.css("a[href]"):
                href = urljoin(self.base, a.attributes.get("href", ""))
                text = re.sub(r"\s+", " ", a.text(strip=True))
                path = urlparse(href).path
                if "/verify/content/" in path and href not in seen and text:
                    seen.add(href)
                    candidates.append((a, href, text))
            if not candidates:
                return
            for node, href, title in candidates:
                # Walk up for the card's own text, but never past the point where the
                # container starts covering a neighbouring article. An earlier version
                # only checked a 140-character floor, which routinely overshot into a
                # multi-card wrapper; every record cut from such a wrapper then inherited
                # the *first* card's verdict and date. Cross-contaminated gold labels are
                # far worse than a missing one, so the walk stops at the card boundary.
                container = node.parent
                for _ in range(4):
                    parent = container.parent if container is not None else None
                    if parent is None or _spans_multiple_articles(parent):
                        break
                    if len(container.text()) > 140:
                        break
                    container = parent
                if container is not None and _spans_multiple_articles(container):
                    container = None
                block = re.sub(r"\s+", " ", container.text(separator=" ", strip=True) if container else title)
                source_id = urlparse(href).path.rstrip("/").split("/")[-1]
                detail, published_at, image_url, claim_verdict, claim_reviewed = await self.detail(href)
                # The article's own ClaimReview wins; the listing block is only a fallback.
                verdict = claim_verdict or next((v for v in VERDICT_LABELS if v in block), "unknown")
                if not published_at:
                    published_at = parse_thai_date(block)
                yield FactCheckRecord(
                    source=self.name, source_id=source_id, source_url=href, title=title,
                    claim=claim_reviewed or title,
                    explanation=detail or block, verdict=verdict,
                    published_at=published_at, image_url=image_url,
                    raw={"archive_text": block, "detail_fetched": bool(detail)},
                )
                emitted += 1
                if limit and emitted >= limit:
                    return
            if mode == "delta":
                return
            page += 1

