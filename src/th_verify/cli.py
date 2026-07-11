from __future__ import annotations

import asyncio
import json
from typing import Annotated

import typer

from .config import Settings
from .collectors.base import CollectorError
from .db import Repository
from .service import collector_names, ingest, ingest_all

app = typer.Typer(help="Build and update the Thai fact-check database.")


@app.command()
def init() -> None:
    settings = Settings.from_env()
    Repository(settings.database_path).initialize()
    typer.echo(f"Initialized {settings.database_path}")


@app.command()
def sync(
    source: Annotated[str, typer.Argument(help="Source name or 'all'")] = "all",
    mode: Annotated[str, typer.Option(help="backfill or delta")] = "delta",
    limit: Annotated[int | None, typer.Option(help="Maximum records per source")] = None,
) -> None:
    settings = Settings.from_env()
    if source != "all" and source not in collector_names():
        raise typer.BadParameter(f"choose one of: all, {', '.join(collector_names())}")
    try:
        result = asyncio.run(ingest_all(mode, settings, limit) if source == "all" else ingest(source, mode, settings, limit))
    except CollectorError as exc:
        raise typer.ClickException(str(exc)) from None
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def stats() -> None:
    settings = Settings.from_env()
    repo = Repository(settings.database_path)
    repo.initialize()
    typer.echo(json.dumps({"database": str(settings.database_path), "records": repo.count(),
                           "coverage": repo.coverage()}, ensure_ascii=False, indent=2))


@app.command()
def classify() -> None:
    """Classify records with 'unknown' verdicts using heuristics or Gemini."""
    from .classifier import run_classification
    settings = Settings.from_env()
    api_key = settings.google_factcheck_api_key
    result = asyncio.run(run_classification(settings.database_path, api_key))
    typer.echo(json.dumps(result, indent=2))


@app.command()
def index() -> None:
    """Build the semantic claim-search index from data/exports/rag_corpus.jsonl."""
    from .search import build_index
    result = build_index()
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def check(
    text: Annotated[str, typer.Argument(help="Claim text to look up")],
    top_k: Annotated[int, typer.Option(help="Number of matches")] = 5,
) -> None:
    """Search past fact-checks for a claim."""
    from .search import get_searcher
    matches = get_searcher().search(text, top_k=top_k)
    typer.echo(json.dumps(matches, ensure_ascii=False, indent=2))


@app.command()
def cluster() -> None:
    """Run semantic clustering to group similar claims in the database."""
    from .clustering import run_clustering
    settings = Settings.from_env()
    result = asyncio.run(asyncio.to_thread(run_clustering, settings.database_path))
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()


