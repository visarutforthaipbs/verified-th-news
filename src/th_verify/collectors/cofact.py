from __future__ import annotations

import re
from collections.abc import AsyncIterator
from xml.etree import ElementTree

from selectolax.parser import HTMLParser

from ..models import FactCheckRecord
from .base import Collector


def clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", HTMLParser(value or "").text(separator=" ")).strip()


class CofactCollector(Collector):
    name = "cofact"
    sitemap = "https://blog.cofact.org/post-sitemap.xml"

    async def collect(self, *, mode: str = "delta", limit: int | None = None) -> AsyncIterator[FactCheckRecord]:
        response = await self.get(self.sitemap)
        root = ElementTree.fromstring(response.content)
        entries = []
        for node in root.findall("{*}url"):
            loc = node.findtext("{*}loc", "").strip()
            modified = node.findtext("{*}lastmod", "").strip()
            if loc and "/th/" in loc:
                entries.append((modified, loc))
        entries.sort(reverse=True)
        if mode == "delta":
            entries = entries[: limit or 20]
        elif limit:
            entries = entries[:limit]

    async def _fetch_one(self, url: str, modified: str, sem: asyncio.Semaphore) -> FactCheckRecord | None:
        async with sem:
            try:
                response = await self.get(url)
                page = HTMLParser(response.text)
                article = page.css_first("main#site-content article") or page.css_first("article.post")
                if not article:
                    return None
                # Exclude related/recommended cards nested in the page shell.
                for extra in article.css("article article, .related-posts, .yarpp-related"):
                    extra.decompose()
                og_title = page.css_first('meta[property="og:title"]')
                heading = article.css_first("h1")
                title = heading.text(strip=True) if heading else (og_title.attributes.get("content", "") if og_title else "")
                title = re.sub(r"\s*\|\s*Cofact$", "", title)
                content_node = article.css_first(".entry-content") or article
                content = re.sub(r"\s+", " ", content_node.text(separator=" ", strip=True)).strip()
                published = page.css_first('meta[property="article:published_time"]')
                image = page.css_first('meta[property="og:image"]')
                match = re.search(r"post-(\d+)", article.attributes.get("class", "") + " " + article.attributes.get("id", ""))
                source_id = match.group(1) if match else url.rstrip("/").rsplit("/", 1)[-1]
                verdict = next((v for v in ("เนื้อหาเป็นเท็จ", "เนื้อหาที่ทำให้เข้าใจผิด", "เนื้อหาเป็นจริงบางส่วน", "เนื้อหาเป็นจริง") if v in content), "unknown")
                return FactCheckRecord(
                    source=self.name, source_id=source_id, source_url=url, title=title,
                    claim=title, explanation=content, verdict=verdict,
                    published_at=published.attributes.get("content") if published else modified,
                    updated_at=modified or None,
                    image_url=image.attributes.get("content") if image else None,
                    raw={"sitemap_lastmod": modified, "discovery": "post-sitemap.xml"},
                )
            except Exception:
                return None

    async def collect(self, *, mode: str = "delta", limit: int | None = None) -> AsyncIterator[FactCheckRecord]:
        import asyncio
        response = await self.get(self.sitemap)
        root = ElementTree.fromstring(response.content)
        entries = []
        for node in root.findall("{*}url"):
            loc = node.findtext("{*}loc", "").strip()
            modified = node.findtext("{*}lastmod", "").strip()
            if loc and "/th/" in loc:
                entries.append((modified, loc))
        entries.sort(reverse=True)
        if mode == "delta":
            entries = entries[: limit or 20]
        elif limit:
            entries = entries[:limit]

        sem = asyncio.Semaphore(15)
        tasks = [self._fetch_one(url, modified, sem) for modified, url in entries]
        for task in asyncio.as_completed(tasks):
            record = await task
            if record is not None:
                yield record

