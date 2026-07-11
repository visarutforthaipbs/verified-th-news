from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class FactCheckRecord:
    source: str
    source_id: str
    source_url: str
    title: str
    claim: str = ""
    explanation: str = ""
    verdict: str = "unknown"
    category: str = ""
    published_at: str | None = None
    updated_at: str | None = None
    language: str = "th"
    image_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    collected_at: str = field(default_factory=utc_now)

    @property
    def fingerprint(self) -> str:
        value = "|".join((self.source, self.source_id, self.source_url)).encode("utf-8")
        return sha256(value).hexdigest()

