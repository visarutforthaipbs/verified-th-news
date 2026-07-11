from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path("data/th_verify.db")
    google_factcheck_api_key: str | None = None
    youtube_api_key: str | None = None
    user_agent: str = "THVerifyResearchBot/0.1 (+https://example.org/contact)"
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=Path(os.getenv("TH_VERIFY_DATABASE_PATH", "data/th_verify.db")),
            google_factcheck_api_key=os.getenv("GOOGLE_FACTCHECK_API_KEY") or None,
            youtube_api_key=os.getenv("YOUTUBE_API_KEY") or None,
            user_agent=os.getenv("TH_VERIFY_USER_AGENT", cls.user_agent),
            timeout_seconds=float(os.getenv("TH_VERIFY_TIMEOUT_SECONDS", "30")),
        )

