# TH Verify Database

A reproducible starter for archiving Thai fact checks from AFP Thailand, Thai PBS Verify,
Cofact, Sure & Share (MCOT), and the Anti-Fake News Center. It supports historical
backfills and small live-delta runs, normalizes records into one SQLite database, and
serves them through a read API.

## Current source status

| Source | Backfill | Delta | Access |
|---|---:|---:|---|
| Cofact | Yes | Yes | WordPress REST API |
| Thai PBS Verify | Yes | Yes | Server-rendered archive pages |
| AFP Thailand | Yes | Yes | Google Fact Check Tools API key |
| Sure & Share | Yes | Yes | YouTube Data API key |
| AFNC | Guarded | Guarded | Export request still needs verification |

AFNC deliberately fails with a clear message. The catalog is client-driven and the
public page alone does not document the CSV/XLSX request. Guessing that endpoint risks
silently producing an incomplete archive.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
th-verify init
th-verify sync cofact --mode delta --limit 20
th-verify sync thaipbs --mode backfill
uvicorn th_verify.api:app --reload
```

Environment variables are read directly from the process. Export the values in `.env`
or use a process manager that loads it. API documentation is at `/docs`.

## Operations

Run a small hourly delta with cron (change the paths to absolute paths):

```cron
12 * * * * cd /path/to/project && .venv/bin/th-verify sync all --mode delta >> data/sync.log 2>&1
```

Run backfills separately so failures can be resumed source-by-source:

```bash
th-verify sync cofact --mode backfill
th-verify sync thaipbs --mode backfill
th-verify sync afp --mode backfill
th-verify sync sure_share --mode backfill
```

All writes use `(source, source_id)` upserts, so reruns update existing rows rather than
duplicating them. The `raw_json` column retains source payloads for later reprocessing.

## Important scope notes

- Cross-publisher semantic deduplication should create a separate `claim_clusters`
  layer; it should not delete provenance records.
- Respect publisher terms, robots policies, and rate limits before a production backfill.
- Google Fact Check search is an index, not a contractual guarantee of AFP's complete
  history. Filtered results are checked by review publisher/URL in the collector.
- For production volume, migrate the repository to PostgreSQL and add full-text search.

