from __future__ import annotations

from collections.abc import AsyncIterator

from ..models import FactCheckRecord
from .base import Collector, CollectorError


class AfncCollector(Collector):
    name = "afnc"
    endpoint = "https://opendata.antifakenewscenter.com/api/export-posts"

    async def collect(self, *, mode: str = "delta", limit: int | None = None) -> AsyncIterator[FactCheckRecord]:
        from datetime import date, timedelta
        from datetime import datetime
        from urllib.parse import parse_qs, urlparse

        end = date.today()
        start = end - timedelta(days=7 if mode == "delta" else 365 * 20)
        response = await self.client.post(self.endpoint, json={
            "search": "", "start_date": start.isoformat(), "end_date": end.isoformat(), "term_id": 0,
        })
        if response.is_error:
            raise CollectorError(f"AFNC returned HTTP {response.status_code}")
        rows = response.json().get("data", [])
        for index, row in enumerate(rows):
            if limit and index >= limit:
                return
            url = row.get("guid", "")
            query_id = parse_qs(urlparse(url).query).get("p", [None])[0]
            source_id = str(query_id or f"{row.get('post_date_gmt','')}|{row.get('post_title','')}")
            published = row.get("post_date_gmt")
            try:
                parsed = datetime.strptime(published, "%d/%m/%Y %H:%M:%S")
                if parsed.year > 2400:
                    parsed = parsed.replace(year=parsed.year - 543)
                published = parsed.isoformat()
            except (TypeError, ValueError):
                pass
            yield FactCheckRecord(
                source=self.name, source_id=source_id, source_url=url,
                title=row.get("post_title", ""), claim=row.get("post_title", ""),
                explanation=row.get("post_content", ""), verdict=row.get("status_label", "unknown"),
                category=row.get("news_type", ""), published_at=published,
                raw=row,
            )
