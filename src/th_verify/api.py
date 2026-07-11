from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .config import Settings
from .db import Repository

# TH_VERIFY_READONLY=1 runs a public-safe instance: labeling/review endpoints
# are disabled and /check is rate-limited. The private full instance runs
# without the flag on the LAN.
READONLY = os.getenv("TH_VERIFY_READONLY") == "1"

app = FastAPI(title="TH Verify Database", version="0.1.0",
              docs_url=None if READONLY else "/docs",
              redoc_url=None if READONLY else "/redoc",
              openapi_url=None if READONLY else "/openapi.json")

_RATE = 20          # /check requests per window per client
_WINDOW = 60.0      # seconds
_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def public_guard(request: Request, call_next):
    if READONLY:
        if request.url.path.startswith("/review"):
            return JSONResponse({"detail": "not available"}, status_code=404)
        if request.url.path == "/check":
            ip = (request.headers.get("cf-connecting-ip")
                  or (request.client.host if request.client else "?"))
            now = time.monotonic()
            q = _hits[ip]
            while q and now - q[0] > _WINDOW:
                q.popleft()
            if len(q) >= _RATE:
                return JSONResponse(
                    {"detail": "ค้นหาถี่เกินไป โปรดรอสักครู่"}, status_code=429)
            q.append(now)
    return await call_next(request)


def _require_private() -> None:
    if READONLY:
        raise HTTPException(status_code=404, detail="not available")

_STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


# ── human labeling (/review) ──────────────────────────────────────────────

HUMAN_LABELS = {"false", "true", "misleading", "altered_media", "scam_alert"}


class LabelRequest(BaseModel):
    id: int
    verdict: str  # one of HUMAN_LABELS, or "skip" / "undo"


@app.get("/review", include_in_schema=False)
def review_page() -> FileResponse:
    return FileResponse(_STATIC_DIR / "review.html")


@app.get("/review/queue")
def review_queue(limit: int = Query(25, ge=1, le=100)) -> dict:
    """Unlabeled sure_share claim-check episodes, oldest first."""
    repo = Repository(Settings.from_env().database_path)
    with repo.connect() as conn:
        total, done = conn.execute(
            "SELECT "
            " SUM(title LIKE '%จริงหรือ%'),"
            " SUM(title LIKE '%จริงหรือ%' AND verdict_origin LIKE 'human%') "
            "FROM fact_checks WHERE source='sure_share'"
        ).fetchone()
        # unlabeled episodes plus heuristic-labeled ones awaiting human
        # verification; anything touched by a human stays out
        rows = conn.execute(
            "SELECT id, title, published_at, source_url,"
            "       json_extract(raw_json, '$.contentDetails.videoId') AS video_id "
            "FROM fact_checks "
            "WHERE source='sure_share' AND title LIKE '%จริงหรือ%' "
            "  AND verdict_origin NOT LIKE 'human%' "
            "  AND (verdict='unknown' OR verdict_origin='heuristic') "
            "ORDER BY published_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"total": total or 0, "labeled": done or 0,
            "items": [dict(r) for r in rows]}


@app.post("/review/label")
def review_label(req: LabelRequest) -> dict:
    _require_private()  # belt-and-braces on top of the middleware
    from .models import utc_now

    repo = Repository(Settings.from_env().database_path)
    with repo.connect() as conn:
        if req.verdict == "undo":
            conn.execute(
                "UPDATE fact_checks SET verdict='unknown', verdict_origin='',"
                " labeled_at=NULL WHERE id=? AND verdict_origin LIKE 'human%'",
                (req.id,),
            )
        elif req.verdict == "skip":
            conn.execute(
                "UPDATE fact_checks SET verdict_origin='human_skipped',"
                " labeled_at=? WHERE id=?",
                (utc_now(), req.id),
            )
        elif req.verdict in HUMAN_LABELS:
            conn.execute(
                "UPDATE fact_checks SET verdict=?, verdict_origin='human',"
                " labeled_at=? WHERE id=?",
                (req.verdict, utc_now(), req.id),
            )
        else:
            raise HTTPException(status_code=422, detail=f"bad verdict: {req.verdict}")
    return {"ok": True}

# cosine-similarity tiers tuned empirically for intfloat/multilingual-e5-small
# on this corpus: same-claim pairs score ~0.91+, paraphrases ~0.88-0.91, and
# unrelated text tops out ~0.88, so the margins are narrow by design of e5-small
STRONG_MATCH = 0.91
POSSIBLE_MATCH = 0.88


class CheckRequest(BaseModel):
    text: str = Field(min_length=5, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


@app.post("/check")
def check(req: CheckRequest) -> dict:
    """Search past fact-checks for a claim ("has this been checked before?")."""
    from .search import DEFAULT_INDEX_DIR, get_searcher

    if not (DEFAULT_INDEX_DIR / "config.json").exists():
        raise HTTPException(status_code=503,
                            detail="Search index not built - run: th-verify index")
    matches = get_searcher().search(req.text, top_k=req.top_k)
    best = matches[0]["score"] if matches else 0.0
    if best >= STRONG_MATCH:
        level = "strong"
    elif best >= POSSIBLE_MATCH:
        level = "possible"
    else:
        level = "none"
    return {
        "query": req.text,
        "match_level": level,
        "best_score": best,
        "matches": matches,
    }


@app.on_event("startup")
def startup() -> None:
    Repository(Settings.from_env().database_path).initialize()


@app.get("/health")
def health() -> dict:
    repo = Repository(Settings.from_env().database_path)
    return {"status": "ok", "records": repo.count()}


@app.get("/fact-checks")
def fact_checks(
    source: str | None = None,
    verdict: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    repo = Repository(Settings.from_env().database_path)
    clauses, params = [], []
    if source:
        clauses.append("source = ?")
        params.append(source)
    if verdict:
        clauses.append("verdict = ?")
        params.append(verdict)
    if q:
        clauses.append("(title LIKE ? OR claim LIKE ? OR explanation LIKE ?)")
        params.extend([f"%{q}%"] * 3)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with repo.connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM fact_checks{where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT id,source,source_id,source_url,title,claim,explanation,verdict,category,published_at,image_url "
            f"FROM fact_checks{where} ORDER BY COALESCE(published_at,collected_at) DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return {"total": total, "items": [dict(row) for row in rows]}


@app.get("/claim-clusters")
def claim_clusters(
    q: str | None = None,
    min_members: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    repo = Repository(Settings.from_env().database_path)
    clauses, params = [], []
    if q:
        clauses.append("c.representative_title LIKE ?")
        params.append(f"%{q}%")
    having = f" HAVING COUNT(m.fact_check_id) >= ?"
    params.append(min_members)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    sql_total = (
        f"SELECT COUNT(*) FROM ("
        f"  SELECT c.id FROM claim_clusters c"
        f"  LEFT JOIN claim_cluster_members m ON c.id = m.cluster_id"
        f"  {where}"
        f"  GROUP BY c.id"
        f"  {having}"
        f")"
    )
    sql_rows = (
        f"SELECT c.id, c.representative_title, c.created_at, COUNT(m.fact_check_id) as member_count "
        f"FROM claim_clusters c "
        f"LEFT JOIN claim_cluster_members m ON c.id = m.cluster_id "
        f"{where} "
        f"GROUP BY c.id "
        f"{having} "
        f"ORDER BY member_count DESC, c.id DESC "
        f"LIMIT ? OFFSET ?"
    )
    with repo.connect() as conn:
        total = conn.execute(sql_total, params).fetchone()[0]
        rows = conn.execute(sql_rows, [*params, limit, offset]).fetchall()
    return {"total": total, "items": [dict(row) for row in rows]}


@app.get("/claim-clusters/{cluster_id}")
def claim_cluster_detail(cluster_id: int) -> dict:
    from fastapi import HTTPException
    repo = Repository(Settings.from_env().database_path)
    with repo.connect() as conn:
        cluster = conn.execute(
            "SELECT id, representative_title, created_at FROM claim_clusters WHERE id = ?",
            (cluster_id,)
        ).fetchone()
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")
        rows = conn.execute(
            "SELECT f.id, f.source, f.source_id, f.source_url, f.title, f.claim, f.explanation, f.verdict, f.category, f.published_at, f.image_url "
            "FROM fact_checks f "
            "JOIN claim_cluster_members m ON f.id = m.fact_check_id "
            "WHERE m.cluster_id = ? "
            "ORDER BY COALESCE(f.published_at, f.collected_at) DESC",
            (cluster_id,)
        ).fetchall()
    return {
        "cluster": dict(cluster),
        "members": [dict(row) for row in rows]
    }


