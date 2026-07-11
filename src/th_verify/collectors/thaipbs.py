from __future__ import annotations

import re
from collections.abc import AsyncIterator
from urllib.parse import urljoin, urlparse

from datetime import datetime
from selectolax.parser import HTMLParser

from ..models import FactCheckRecord
from .base import Collector


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


class ThaiPbsCollector(Collector):
    name = "thaipbs"
    base = "https://www.thaipbs.or.th/verify/category/all"

    async def detail(self, url: str) -> tuple[str, str | None, str | None]:
        response = await self.get(url)
        tree = HTMLParser(response.text)
        article = tree.css_first("article.single-content")
        if not article:
            return "", None, None
        # Recommendations are nested after the authored content; drop them before text extraction.
        for selector in ("section.single-recommend", "section.single-author", "section.single-tags"):
            for node in article.css(selector):
                node.decompose()
        text = re.sub(r"\s+", " ", article.text(separator=" ", strip=True)).strip()
        image = tree.css_first('meta[property="og:image"]')
        published = tree.css_first('meta[property="article:published_time"]')
        return text, (published.attributes.get("content") if published else None), (image.attributes.get("content") if image else None)

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
                container = node.parent
                for _ in range(4):
                    if container is None or len(container.text()) > 140:
                        break
                    container = container.parent
                block = re.sub(r"\s+", " ", container.text(separator=" ", strip=True) if container else title)
                source_id = urlparse(href).path.rstrip("/").split("/")[-1]
                verdict = next((v for v in ("ข่าวปลอม", "ข่าวบิดเบือน", "ข่าวจริง", "ภาพปลอม") if v in block), "unknown")
                detail, published_at, image_url = await self.detail(href)
                if not published_at:
                    published_at = parse_thai_date(block)
                yield FactCheckRecord(
                    source=self.name, source_id=source_id, source_url=href, title=title,
                    claim=title, explanation=detail or block, verdict=verdict,
                    published_at=published_at, image_url=image_url,
                    raw={"archive_text": block, "detail_fetched": bool(detail)},
                )
                emitted += 1
                if limit and emitted >= limit:
                    return
            if mode == "delta":
                return
            page += 1

