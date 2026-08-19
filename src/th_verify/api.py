from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .config import Settings
from .db import Repository
from .normalized import clean_claim_text, is_factcheck, normalize_verdict

# TH_VERIFY_READONLY=1 runs a public-safe instance: labeling/review endpoints
# are disabled and /check is rate-limited. The private full instance runs
# without the flag on the LAN.
READONLY = os.getenv("TH_VERIFY_READONLY") == "1"

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    Repository(Settings.from_env().database_path).initialize()
    yield

app = FastAPI(title="TH Verify Database", version="0.1.0",
              docs_url=None if READONLY else "/docs",
              redoc_url=None if READONLY else "/redoc",
              openapi_url=None if READONLY else "/openapi.json",
              lifespan=lifespan)

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


def _display_claim(row: dict) -> dict:
    """Show the reviewer the claim the DATASET will contain, not the raw title.

    When claim_origin is '' the claim column is a verbatim copy of the headline,
    and cleaning happens downstream in build_dataset -- so the exports and the
    search index get "ประโยชน์ของสับปะรด ลดความเสี่ยงมะเร็ง" while the review room
    was showing "…จริงหรือ ?  #ชัวร์ก่อนแชร์ #shorts #สับปะรด". Two different texts
    for the same record, and the reviewer was reading the worse one.

    Only the '' tier is cleaned. A claim that came from the publisher, a model,
    or a human is final text and must be shown exactly as stored.
    """
    if not row.get("claim_origin"):
        # Fall back to the title when claim is empty: the review room does
        # `item.claim || item.title`, so an empty claim put the RAW headline on
        # screen -- hashtags and all -- which is the exact thing being cleaned.
        source_text = row.get("claim") or row.get("title") or ""
        cleaned = clean_claim_text(source_text, row.get("source", ""))
        if cleaned:
            row["claim"] = cleaned
    return row


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
    verdict: str  # one of HUMAN_LABELS, or "skip" / "not_claim" / "undo"
    # Undo normally clears the record back to unlabelled, which is right in the
    # main queue -- what came before was nothing. In the conflicts queue the
    # record already carried a machine label, and blanking it would discard the
    # very guess the reviewer was asked to check. The client sends that prior
    # state back so undo restores it instead.
    restore_verdict: str | None = None
    restore_origin: str | None = None
    # Who is labelling. Attribution, not authentication -- the server records
    # what the review room tells it. Access control is Tailscale's job.
    by: str = Field("", max_length=40)


@app.get("/review", include_in_schema=False)
def review_page() -> FileResponse:
    return FileResponse(_STATIC_DIR / "review.html")


@app.get("/review/queue")
def review_queue(
    source: str | None = Query(None, description="Source filter (e.g. sure_share, cofact, thaipbs, afnc, afp, all)"),
    order: str = Query("desc", description="Sort order: 'desc' (newest first, the default) or 'asc' (oldest first)"),
    limit: int = Query(25, ge=1, le=100)
) -> dict:
    """Unlabeled/heuristic claim-check records awaiting human review."""
    repo = Repository(Settings.from_env().database_path)
    # Newest first by default. The daily sync adds only 2-4 records that need a
    # human -- the other sources arrive with the publisher's verdict -- and
    # oldest-first buried them behind 6,500 records of 2015 backlog, so nobody
    # saw today's arrivals at all.
    sort_dir = "ASC" if order.lower() == "asc" else "DESC"
    with repo.connect() as conn:
        where_clause = ""
        params_count: list[str] = []
        params_rows: list[str | int] = []

        if source and source != "all":
            where_clause = " WHERE source = ?"
            params_count.append(source)
            params_rows.append(source)

        # Counts must exclude material that is not a claim, or the progress bar
        # measures the wrong denominator: Cofact's 1,017 rows include analysis
        # articles and programme announcements nobody can adjudicate.
        # Only the first ~120 characters of explanation are needed -- is_factcheck
        # reads Cofact's category prefix, which sits ahead of the title. Selecting
        # the whole column pulled ~37 MB per request for no benefit.
        counted = conn.execute(
            "SELECT source, title, verdict, verdict_origin, "
            "       substr(explanation, 1, 120) AS explanation "
            f"FROM fact_checks{where_clause}",
            params_count,
        ).fetchall()
        counted = [r for r in counted
                   if is_factcheck(r["source"], r["title"], r["verdict"], r["explanation"],
                                   r["verdict_origin"])]
        # The denominator is the human's workload, not the size of the archive.
        # Most AFNC and AFP records arrive with the publisher's own verdict and
        # need nobody to look at them, so counting every fact-check made the bar
        # read "3 / 14781" when exactly one record was actually waiting. What a
        # reviewer wants to know is how far through the queue THEY are.
        done = sum(1 for r in counted
                   if (r["verdict_origin"] or "").startswith("human"))
        pending = sum(1 for r in counted
                      if not (r["verdict_origin"] or "").startswith("human")
                      and (normalize_verdict(r["source"], r["verdict"]) == "unknown"
                           or r["verdict_origin"] == "heuristic"))
        total = done + pending

        where_rows = (where_clause + " AND " if where_clause else " WHERE ")
        sql_rows = (
            "SELECT id, source, source_id, source_url, title, claim, claim_origin, explanation, verdict, verdict_origin, published_at,"
            " json_extract(raw_json, '$.contentDetails.videoId') AS video_id,"
            " (SELECT quote FROM asr_evidence e WHERE e.fact_check_id = fact_checks.id) AS asr_quote,"
            " (SELECT transcript FROM asr_evidence e WHERE e.fact_check_id = fact_checks.id) AS asr_transcript,"
            " (SELECT raw_verdict FROM asr_evidence e WHERE e.fact_check_id = fact_checks.id) AS asr_raw_verdict,"
            " (SELECT quote_expert FROM asr_evidence e WHERE e.fact_check_id = fact_checks.id) AS asr_quote_expert,"
            " (SELECT verdict_expert FROM asr_evidence e WHERE e.fact_check_id = fact_checks.id) AS asr_verdict_expert "
            "FROM fact_checks "
            f"{where_rows} verdict_origin NOT LIKE 'human%' "
            f"ORDER BY COALESCE(published_at, collected_at) {sort_dir} LIMIT ?"
        )
        # Over-fetch, then drop non-claims in Python. is_factcheck is a Python
        # predicate (it reads a section list and a title regex), so it cannot be
        # pushed into SQL without duplicating the rule in two places -- and a
        # filter that exists twice is a filter that will disagree with itself.
        # Select on the NORMALISED verdict, not the literal string "unknown".
        # Thai PBS stamps its policy explainers ไม่สแตมป์ข่าว -- a real editorial
        # outcome that still carries no polarity, so a human should see it. Once
        # those records hold the publisher's actual wording, a literal
        # verdict='unknown' test would drop them from the queue entirely, which is
        # the opposite of what storing the truthful value should achieve.
        # Walk forward until `limit` survivors are found, rather than filtering a
        # single fixed window. The old code fetched limit*40 rows once, so a
        # small limit examined only the oldest few hundred records -- and if
        # those all happened to be non-claims, it returned NOTHING while
        # thousands waited. `/review/queue?limit=3` reported an empty queue with
        # 6,518 records in it. The browser always asks for 50 so it never showed
        # there, which is exactly what makes it worth fixing.
        rows: list = []
        offset, SCAN, MAX_SCAN = 0, max(limit * 40, 400), 30000
        while len(rows) < limit and offset < MAX_SCAN:
            batch = conn.execute(sql_rows + " OFFSET ?",
                                 [*params_rows, SCAN, offset]).fetchall()
            if not batch:
                break
            rows.extend(r for r in batch
                        if is_factcheck(r["source"], r["title"], r["verdict"],
                                        r["explanation"], r["verdict_origin"])
                        and (normalize_verdict(r["source"], r["verdict"]) == "unknown"
                             or r["verdict_origin"] == "heuristic"))
            offset += SCAN
        rows = rows[:limit]


    return {"total": total or 0, "labeled": done or 0,
            "items": [_display_claim(dict(r)) for r in rows]}


@app.get("/review/verify")
def review_verify(limit: int = Query(25, ge=1, le=100)) -> dict:
    """Machine-labelled records with the evidence the machine used.

    A different job from the main queue. There the reviewer decides from
    scratch; here the model has already answered and quoted the sentence it
    answered from, so the reviewer is checking homework. That is the difference
    between 2-3 minutes of watching a video and ten seconds of reading a line,
    and it is the only way 6,665 clips is a week's work instead of fifty days.

    Only records that carry evidence are served. A machine label with no quote
    behind it is exactly what a reviewer cannot check, and offering it here
    would invite rubber-stamping.
    """
    _require_private()
    repo = Repository(Settings.from_env().database_path)
    with repo.connect() as conn:
        done = conn.execute(
            "SELECT COUNT(*) FROM fact_checks f JOIN asr_evidence e"
            " ON e.fact_check_id = f.id WHERE f.verdict_origin LIKE 'human%'").fetchone()[0]
        rows = conn.execute(
            "SELECT f.id, f.source, f.source_id, f.source_url, f.title, f.claim,"
            " f.claim_origin, f.explanation, f.verdict, f.verdict_origin, f.published_at,"
            " json_extract(f.raw_json, '$.contentDetails.videoId') AS video_id,"
            " e.quote AS asr_quote, e.transcript AS asr_transcript,"
            " e.raw_verdict AS asr_raw_verdict, e.status AS asr_status,"
            " e.quote_expert AS asr_quote_expert, e.verdict_expert AS asr_verdict_expert"
            " FROM fact_checks f JOIN asr_evidence e ON e.fact_check_id = f.id"
            " WHERE f.verdict_origin = 'llm' AND length(e.quote) > 0"
            "   AND f.verdict NOT IN ('unknown','')"
            " ORDER BY f.published_at DESC LIMIT ?", (limit,)).fetchall()
        pending = conn.execute(
            "SELECT COUNT(*) FROM fact_checks f JOIN asr_evidence e"
            " ON e.fact_check_id = f.id WHERE f.verdict_origin = 'llm'"
            " AND length(e.quote) > 0 AND f.verdict NOT IN ('unknown','')").fetchone()[0]
    return {"total": done + pending, "labeled": done,
            "items": [_display_claim(dict(r)) for r in rows]}


@app.get("/review/collector-health")
def collector_health() -> dict:
    """Last night's collector audit, for the banner in the review room."""
    _require_private()
    path = Path(Settings.from_env().database_path).parent / "reports" / "collector_health.json"
    if not path.exists():
        return {"checked_at": None, "failing": 0, "warning": 0, "findings": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _conflicts_file() -> Path:
    """Beside the database, not beside the process.

    The service runs from a different working directory on lighthouse-core than
    it does in a checkout, so a relative path would resolve to whatever happened
    to be current. The report belongs to the database it describes.
    """
    return Path(Settings.from_env().database_path).parent / "reports" / "label_conflicts.json"


@app.get("/review/conflicts")
def review_conflicts(limit: int = Query(25, ge=1, le=100)) -> dict:
    """Records where our own label contradicts a publisher's ruling.

    This is the cheapest human review in the archive. Everywhere else a reviewer
    reads an article and decides; here another fact-checker has already decided,
    on a claim we are 94%+ confident is the same one, and disagreed with us. The
    only question left is which of the two is right -- and the publisher's side
    arrives with its own explanation attached.

    The pair list is precomputed (it needs the embedding index), but membership
    is re-checked against the live database on every request: once a human has
    touched our side, the disagreement has been adjudicated and the pair drops
    out. That keeps the queue self-draining without a second piece of state to
    keep in sync.
    """
    path = _conflicts_file()
    if not path.exists():
        return {"total": 0, "labeled": 0, "items": [],
                "note": "run scripts/find_cross_source_conflicts.py --qa"}
    pairs = json.loads(path.read_text(encoding="utf-8"))

    repo = Repository(Settings.from_env().database_path)
    ids = {p[side]["id"] for p in pairs for side in ("ours", "theirs")}
    with repo.connect() as conn:
        dismissed = {tuple(sorted(r)) for r in
                     conn.execute("SELECT a_id, b_id FROM conflict_dismissals")}
        live = {
            r["id"]: dict(r)
            for r in conn.execute(
                "SELECT id, source, source_url, title, claim, claim_origin, verdict,"
                " verdict_origin, published_at, substr(explanation, 1, 900) AS explanation"
                f" FROM fact_checks WHERE id IN ({','.join('?' * len(ids))})",
                list(ids)).fetchall()
        } if ids else {}

    items, done, seen = [], 0, set()
    for p in pairs:                       # sorted by similarity, descending
        mine = live.get(p["ours"]["id"])
        theirs = live.get(p["theirs"]["id"])
        if mine is None or theirs is None:
            continue                      # record deleted since the scan
        if tuple(sorted((mine["id"], theirs["id"]))) in dismissed:
            continue                      # judged "not the same claim"
        # One record of ours can be contradicted by several publisher articles --
        # AFNC often runs the same debunk twice. The reviewer answers about our
        # record once, so keep only the closest match; the rest are the same
        # question asked again, and counting them would inflate the progress bar.
        if mine["id"] in seen:
            continue
        seen.add(mine["id"])
        if (mine["verdict_origin"] or "").startswith("human"):
            done += 1                     # already adjudicated
            continue
        if mine["verdict_origin"] not in ("llm", "heuristic"):
            continue                      # our side was re-sourced; no longer ours
        items.append({**_display_claim(mine), "similarity": p["similarity"],
                      "their_verdict_normalized": normalize_verdict(
                          theirs["source"], theirs["verdict"]),
                      "our_verdict_normalized": normalize_verdict(
                          mine["source"], mine["verdict"]),
                      "theirs": _display_claim(theirs)})
    return {"total": done + len(items), "labeled": done,
            "items": items[:limit]}


class DismissRequest(BaseModel):
    ours_id: int
    theirs_id: int
    undo: bool = False
    by: str = Field("", max_length=40)


@app.post("/review/conflict/dismiss")
def review_conflict_dismiss(req: DismissRequest) -> dict:
    """Record that two matched claims are not, in fact, the same claim.

    Deliberately touches no verdict and no provenance. The reviewer is
    correcting the *matcher*, not labelling a record, and conflating the two
    would put unread machine labels into the gold tier.
    """
    _require_private()
    from .models import utc_now

    a, b = sorted((req.ours_id, req.theirs_id))
    repo = Repository(Settings.from_env().database_path)
    with repo.connect() as conn:
        if req.undo:
            conn.execute("DELETE FROM conflict_dismissals WHERE a_id=? AND b_id=?", (a, b))
        else:
            conn.execute("INSERT OR IGNORE INTO conflict_dismissals (a_id, b_id, dismissed_at)"
                         " VALUES (?,?,?)", (a, b, utc_now()))
    return {"ok": True}


class ClaimRequest(BaseModel):
    id: int
    claim: str = Field(min_length=8, max_length=400)
    by: str = Field("", max_length=40)


@app.post("/review/claim")
def review_claim(req: ClaimRequest) -> dict:
    """Correct the claim under review.

    Kept apart from /review/label because the two are different judgements: one
    says what was asserted, the other whether it holds. A reviewer often needs to
    fix the first before the second can be answered honestly -- the stored claim
    is a copy of the headline for 27,925 records, and a headline frequently
    carries the verdict.
    """
    _require_private()
    from .models import utc_now

    repo = Repository(Settings.from_env().database_path)
    with repo.connect() as conn:
        conn.execute(
            "UPDATE fact_checks SET claim=?, claim_origin='human', labeled_at=?,"
            " labeled_by=? WHERE id=?",
            (req.claim.strip(), utc_now(), req.by.strip(), req.id),
        )
    return {"ok": True}


@app.post("/review/label")
def review_label(req: LabelRequest) -> dict:
    _require_private()  # belt-and-braces on top of the middleware
    from .models import utc_now

    repo = Repository(Settings.from_env().database_path)
    with repo.connect() as conn:
        if req.verdict == "undo":
            if req.restore_origin in ("llm", "heuristic") and req.restore_verdict:
                conn.execute(
                    "UPDATE fact_checks SET verdict=?, verdict_origin=?,"
                    " labeled_at=NULL, labeled_by='' WHERE id=? AND verdict_origin LIKE 'human%'",
                    (req.restore_verdict, req.restore_origin, req.id),
                )
            else:
                conn.execute(
                    "UPDATE fact_checks SET verdict='unknown', verdict_origin='',"
                    " labeled_at=NULL, labeled_by='' WHERE id=? AND verdict_origin LIKE 'human%'",
                    (req.id,),
                )
        elif req.verdict == "not_claim":
            # Distinct from "skip". skip means "this is a claim but I cannot
            # judge it"; not_claim means "this was never a claim". Collapsing
            # them loses the only signal that can retire an item permanently.
            conn.execute(
                "UPDATE fact_checks SET verdict_origin='human_not_claim',"
                " labeled_at=?, labeled_by=? WHERE id=?",
                (utc_now(), req.by.strip(), req.id),
            )
        elif req.verdict == "skip":
            conn.execute(
                "UPDATE fact_checks SET verdict_origin='human_skipped',"
                " labeled_at=?, labeled_by=? WHERE id=?",
                (utc_now(), req.by.strip(), req.id),
            )
        elif req.verdict in HUMAN_LABELS:
            conn.execute(
                "UPDATE fact_checks SET verdict=?, verdict_origin='human',"
                " labeled_at=?, labeled_by=? WHERE id=?",
                (req.verdict, utc_now(), req.by.strip(), req.id),
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
    try:
        searcher = get_searcher()
    except (ModuleNotFoundError, ImportError) as exc:
        raise HTTPException(status_code=503,
                            detail=f"Search service dependency missing: {exc}") from exc
    matches = searcher.search(req.text, top_k=req.top_k)
    best = matches[0]["score"] if matches else 0.0
    if best >= STRONG_MATCH:
        level = "strong"
    elif best >= POSSIBLE_MATCH:
        level = "possible"
    elif any(m.get("match_type") == "hybrid" for m in matches):
        # Below the semantic threshold, but records were surfaced independently by
        # BOTH the embedding search and the keyword search. Reporting that as
        # "none" made the page announce "ยังไม่พบการตรวจสอบเรื่องนี้" directly above
        # a list of plainly relevant results.
        #
        # Short queries are the usual cause: the embedding model compares the input
        # against whole claim sentences, so a bare keyword scores low however
        # relevant it is. "ยาพารา" scores 0.856 while the same claim written out in
        # full scores 0.937.
        #
        # Requiring 'hybrid' rather than merely "some matches exist" matters: the
        # dense search always returns its top-k, so `matches` is never empty and a
        # nonsense query would otherwise be reported as related. A stray substring
        # can also produce a lone 'keyword' hit ("zzz" matches something). Only
        # agreement between the two retrieval methods is treated as relevance.
        level = "related"
    else:
        level = "none"
    return {
        "query": req.text,
        "match_level": level,
        "best_score": best,
        "matches": matches,
    }



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


