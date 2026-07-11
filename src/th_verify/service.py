from __future__ import annotations

import httpx

from .collectors import AfncCollector, AfpCollector, CofactCollector, SureShareCollector, ThaiPbsCollector
from .collectors.base import CollectorError
from .config import Settings
from .db import Repository


def collector_names() -> list[str]:
    return ["cofact", "thaipbs", "afp", "sure_share", "afnc"]


async def ingest(source: str, mode: str, settings: Settings, limit: int | None = None) -> int:
    if mode not in {"backfill", "delta"}:
        raise ValueError("mode must be backfill or delta")
    repo = Repository(settings.database_path)
    repo.initialize()
    run_id = repo.start_run(source, mode)
    headers = {"User-Agent": settings.user_agent, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
    async with httpx.AsyncClient(headers=headers, timeout=settings.timeout_seconds, follow_redirects=True) as client:
        collectors = {
            "cofact": CofactCollector(client),
            "thaipbs": ThaiPbsCollector(client),
            "afp": AfpCollector(client, settings.google_factcheck_api_key),
            "sure_share": SureShareCollector(client, settings.youtube_api_key),
            "afnc": AfncCollector(client),
        }
        if source not in collectors:
            raise ValueError(f"unknown source: {source}")
        batch = []
        total = 0
        last_id = None
        try:
            async for record in collectors[source].collect(mode=mode, limit=limit):
                batch.append(record)
                last_id = record.source_id
                if len(batch) >= 100:
                    total += repo.upsert_many(batch)
                    batch.clear()
            total += repo.upsert_many(batch)
            repo.finish_run(run_id, status="success", records=total)
            repo.mark_source(source, mode, total, last_id)
            return total
        except Exception as exc:
            total += repo.upsert_many(batch)
            repo.finish_run(run_id, status="failed", records=total, error=str(exc)[:1000])
            raise


async def ingest_all(mode: str, settings: Settings, limit: int | None = None) -> dict[str, int | str]:
    results: dict[str, int | str] = {}
    for source in collector_names():
        try:
            results[source] = await ingest(source, mode, settings, limit)
        except CollectorError as exc:
            results[source] = f"skipped: {exc}"
    return results
