from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx

from ..models import FactCheckRecord


class CollectorError(RuntimeError):
    pass


class Collector(ABC):
    name: str

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    @abstractmethod
    async def collect(self, *, mode: str = "delta", limit: int | None = None) -> AsyncIterator[FactCheckRecord]:
        raise NotImplementedError

    async def get(self, url: str, **kwargs) -> httpx.Response:
        response = await self.client.get(url, **kwargs)
        if response.is_error:
            try:
                message = response.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                message = ""
            detail = f": {message}" if message else ""
            # Do not call raise_for_status(): its exception renders the request URL,
            # including API keys passed as query parameters.
            raise CollectorError(f"upstream returned HTTP {response.status_code}{detail}")
        return response
