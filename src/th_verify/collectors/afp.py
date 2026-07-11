from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import urlparse

from ..models import FactCheckRecord
from .base import Collector, CollectorError


class AfpCollector(Collector):
    name = "afp"
    endpoint = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

    def __init__(self, client, api_key: str | None):
        super().__init__(client)
        self.api_key = api_key

    async def collect(self, *, mode: str = "delta", limit: int | None = None) -> AsyncIterator[FactCheckRecord]:
        if not self.api_key:
            raise CollectorError("GOOGLE_FACTCHECK_API_KEY is required for AFP")
        token = None
        emitted = 0
        while True:
            params = {
                "key": self.api_key,
                "languageCode": "th",
                # Exact publisher identifier returned by Google's index.
                "reviewPublisherSiteFilter": "factcheckthailand.afp.com",
                "pageSize": min(limit or 100, 100),
            }
            if token:
                params["pageToken"] = token
            data = (await self.get(self.endpoint, params=params)).json()
            for claim in data.get("claims", []):
                for review in claim.get("claimReview", []):
                    url = review.get("url", "")
                    host = urlparse(url).netloc.lower()
                    publisher = review.get("publisher", {}).get("site", "").lower()
                    if "afp.com" not in host and "afp" not in publisher:
                        continue
                    source_id = review.get("url") or f"{claim.get('text','')}|{review.get('reviewDate','')}"
                    yield FactCheckRecord(
                        source=self.name, source_id=source_id, source_url=url,
                        title=review.get("title") or claim.get("text", ""), claim=claim.get("text", ""),
                        verdict=review.get("textualRating", "unknown"),
                        published_at=review.get("reviewDate"), raw={"claim": claim, "review": review},
                    )
                    emitted += 1
                    if limit and emitted >= limit:
                        return
            token = data.get("nextPageToken")
            if not token or mode == "delta":
                return
