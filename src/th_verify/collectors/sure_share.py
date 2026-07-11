from __future__ import annotations

import re
from collections.abc import AsyncIterator

from ..models import FactCheckRecord
from .base import Collector, CollectorError


class SureShareCollector(Collector):
    name = "sure_share"
    api = "https://www.googleapis.com/youtube/v3"

    def __init__(self, client, api_key: str | None):
        super().__init__(client)
        self.api_key = api_key

    async def _uploads_playlist(self) -> str:
        if not self.api_key:
            raise CollectorError("YOUTUBE_API_KEY is required for Sure & Share")
        data = (await self.get(f"{self.api}/channels", params={
            "part": "contentDetails", "forHandle": "SureAndShare", "key": self.api_key
        })).json()
        items = data.get("items", [])
        if not items:
            raise CollectorError("YouTube channel @SureAndShare was not found")
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    async def collect(self, *, mode: str = "delta", limit: int | None = None) -> AsyncIterator[FactCheckRecord]:
        playlist = await self._uploads_playlist()
        token = None
        emitted = 0
        while True:
            params = {"part": "snippet,contentDetails", "playlistId": playlist,
                      "maxResults": min(limit or 50, 50), "key": self.api_key}
            if token:
                params["pageToken"] = token
            data = (await self.get(f"{self.api}/playlistItems", params=params)).json()
            for item in data.get("items", []):
                snippet = item["snippet"]
                video_id = item.get("contentDetails", {}).get("videoId") or snippet["resourceId"]["videoId"]
                title = re.sub(r"^ชัวร์ก่อนแชร์\s*[:：|-]\s*", "", snippet.get("title", ""), flags=re.I)
                yield FactCheckRecord(
                    source=self.name, source_id=video_id,
                    source_url=f"https://www.youtube.com/watch?v={video_id}", title=title,
                    claim=title, explanation=snippet.get("description", ""),
                    published_at=snippet.get("publishedAt"),
                    image_url=snippet.get("thumbnails", {}).get("high", {}).get("url"), raw=item,
                )
                emitted += 1
                if limit and emitted >= limit:
                    return
            token = data.get("nextPageToken")
            if not token or mode == "delta":
                return

