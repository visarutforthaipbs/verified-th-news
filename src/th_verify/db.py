from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import FactCheckRecord, utc_now


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS fact_checks (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  title TEXT NOT NULL,
  claim TEXT NOT NULL DEFAULT '',
  explanation TEXT NOT NULL DEFAULT '',
  verdict TEXT NOT NULL DEFAULT 'unknown',
  category TEXT NOT NULL DEFAULT '',
  published_at TEXT,
  updated_at TEXT,
  language TEXT NOT NULL DEFAULT 'th',
  image_url TEXT,
  fingerprint TEXT NOT NULL UNIQUE,
  raw_json TEXT NOT NULL DEFAULT '{}',
  collected_at TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  verdict_origin TEXT NOT NULL DEFAULT '',
  labeled_at TEXT,
  claim_origin TEXT NOT NULL DEFAULT '',
  UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_fact_checks_published ON fact_checks(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_fact_checks_source ON fact_checks(source);
CREATE INDEX IF NOT EXISTS idx_fact_checks_verdict ON fact_checks(verdict);
CREATE TABLE IF NOT EXISTS sync_runs (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  mode TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  records_seen INTEGER NOT NULL DEFAULT 0,
  error TEXT
);
CREATE TABLE IF NOT EXISTS source_state (
  source TEXT NOT NULL,
  mode TEXT NOT NULL,
  last_success_at TEXT,
  last_record_id TEXT,
  records_seen INTEGER NOT NULL DEFAULT 0,
  complete INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(source, mode)
);
CREATE TABLE IF NOT EXISTS claim_clusters (
  id INTEGER PRIMARY KEY,
  representative_title TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_cluster_members (
  cluster_id INTEGER NOT NULL REFERENCES claim_clusters(id) ON DELETE CASCADE,
  fact_check_id INTEGER NOT NULL REFERENCES fact_checks(id) ON DELETE CASCADE,
  PRIMARY KEY (cluster_id, fact_check_id)
);
CREATE INDEX IF NOT EXISTS idx_claim_cluster_members_fact_check ON claim_cluster_members(fact_check_id);
-- Pairs a reviewer has judged NOT to be the same claim.
--
-- The conflicts queue matches on embedding similarity, and at 0.94 the model
-- still pairs claims that merely share a topic: "4 drinks clean the kidneys"
-- against "5 drinks strengthen the kidneys", farmed tilapia against raw
-- tilapia. Those are not disagreements and there is nothing to adjudicate.
--
-- Recording that as a verdict would be a lie twice over -- it would stamp
-- `human` provenance on a machine label nobody read, and claim a human settled
-- a dispute that never existed. So the dismissal lives on the PAIR, leaving
-- both records' verdicts and provenance exactly as they were.
--
-- It is a table rather than a file because data/reports/label_conflicts.json is
-- regenerated on every index rebuild, and this judgement must outlive it.
-- What the machine heard, kept so a human can check the machine's homework.
--
-- The ASR run labelled 1,332 videos and threw its evidence away: the verdict
-- landed in fact_checks and the transcript and quote stayed in a jsonl file on
-- the GPU node. That left a reviewer with only two options, trust the label
-- blind or watch the video again -- and watching is 2-3 minutes a clip against
-- 6,665 clips, which is fifty days of somebody's life.
--
-- With the quote on screen the same judgement takes ten seconds: read the claim,
-- read the sentence the model based its answer on, agree or correct it. The
-- transcript is kept too, because when the quote is unconvincing the next
-- question is always "what else did they say".
--
-- Separate from fact_checks deliberately: transcripts are bulky, they exist only
-- for one source, and evidence is not a property of the claim -- re-running ASR
-- with a longer window should be able to replace it without touching the record.
CREATE TABLE IF NOT EXISTS asr_evidence (
  fact_check_id INTEGER PRIMARY KEY REFERENCES fact_checks(id) ON DELETE CASCADE,
  transcript TEXT NOT NULL DEFAULT '',
  quote TEXT NOT NULL DEFAULT '',
  raw_verdict TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conflict_dismissals (
  a_id INTEGER NOT NULL REFERENCES fact_checks(id) ON DELETE CASCADE,
  b_id INTEGER NOT NULL REFERENCES fact_checks(id) ON DELETE CASCADE,
  dismissed_at TEXT NOT NULL,
  PRIMARY KEY (a_id, b_id)
);
"""



FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS fact_checks_fts USING fts5(
    title,
    claim,
    explanation
);

-- These three triggers are what keep the index in step with the table. _setup_fts
-- drops them before running this script, so they MUST be recreated here: without
-- them the FTS table is only ever populated by the one-off backfill, and every
-- row inserted afterwards is invisible to keyword search. That is exactly what
-- happened -- 309 records ingested from 2026-07-27 onward were missing from the
-- index while sitting perfectly happily in fact_checks.
CREATE TRIGGER IF NOT EXISTS fact_checks_ai AFTER INSERT ON fact_checks BEGIN
    INSERT INTO fact_checks_fts(rowid, title, claim, explanation)
    VALUES (new.id, new.title, new.claim, new.explanation);
END;

-- Deletion is a plain DELETE, not the INSERT ... VALUES('delete', ...) form.
-- That special command belongs to external-content FTS5 tables; this one stores
-- its own content, and using it there raises "SQL logic error" on every update.
CREATE TRIGGER IF NOT EXISTS fact_checks_ad AFTER DELETE ON fact_checks BEGIN
    DELETE FROM fact_checks_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS fact_checks_au AFTER UPDATE ON fact_checks BEGIN
    DELETE FROM fact_checks_fts WHERE rowid = old.id;
    INSERT INTO fact_checks_fts(rowid, title, claim, explanation)
    VALUES (new.id, new.title, new.claim, new.explanation);
END;
"""


class Repository:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)
            self._setup_fts(conn)

    @staticmethod
    def _setup_fts(conn: sqlite3.Connection) -> None:
        try:
            conn.execute("DROP TRIGGER IF EXISTS fact_checks_ai;")
            conn.execute("DROP TRIGGER IF EXISTS fact_checks_ad;")
            conn.execute("DROP TRIGGER IF EXISTS fact_checks_au;")
            conn.executescript(FTS_SCHEMA)
            # Repair any gap, not just an empty index. The previous condition only
            # backfilled when the FTS table had zero rows, so once the triggers went
            # missing the index silently froze: it looked populated, and nothing
            # would ever notice the arrears. Insert only the rows actually absent,
            # which is a no-op on a healthy database.
            missing = conn.execute(
                "SELECT COUNT(*) FROM fact_checks f WHERE NOT EXISTS "
                "(SELECT 1 FROM fact_checks_fts t WHERE t.rowid = f.id)"
            ).fetchone()[0]
            if missing:
                conn.execute(
                    "INSERT INTO fact_checks_fts(rowid, title, claim, explanation) "
                    "SELECT id, title, claim, explanation FROM fact_checks f "
                    "WHERE NOT EXISTS (SELECT 1 FROM fact_checks_fts t "
                    "                  WHERE t.rowid = f.id)"
                )
        except sqlite3.OperationalError:
            pass


    def search_fts(self, text: str, limit: int = 30) -> list[dict]:
        terms = [t for t in text.replace('"', ' ').replace("'", ' ').replace(':', ' ').split() if len(t) > 1]
        if not terms:
            return []
        fts_query = " OR ".join(f'"{t}"*' for t in terms[:10])
        results: list[dict] = []
        with self.connect() as conn:
            try:
                rows = conn.execute(
                    "SELECT f.id, f.source, f.source_url AS url, f.title, f.claim AS claim_text, "
                    "       f.verdict AS label, f.published_at, f.explanation AS explanation_snippet, "
                    "       fts.rank "
                    "FROM fact_checks_fts fts "
                    "JOIN fact_checks f ON fts.rowid = f.id "
                    "WHERE fact_checks_fts MATCH ? "
                    "ORDER BY fts.rank ASC LIMIT ?",
                    (fts_query, limit),
                ).fetchall()
                results = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                results = []

            # Thai is written without spaces, so FTS5's default tokenizer treats a
            # whole phrase as one token and only matches an exact token boundary.
            # Searching "ยาพารา" returned 1 row while 24 records contain it as a
            # substring. This used to `return` as soon as FTS produced ANY row, so a
            # single thin hit suppressed the substring fallback entirely and the
            # caller saw one result where two dozen existed.
            #
            # Top up from a LIKE scan whenever FTS did not fill the quota, rather
            # than only when it returned nothing. FTS ordering is kept first so
            # BM25 ranking still leads for space-separated text.
            if len(results) < limit:
                seen = {r["id"] for r in results}
                where_like = " OR ".join(
                    ["title LIKE ? OR claim LIKE ? OR explanation LIKE ?"] * len(terms[:5]))
                params_like = []
                for t in terms[:5]:
                    params_like.extend([f"%{t}%"] * 3)
                rows = conn.execute(
                    f"SELECT id, source, source_url AS url, title, claim AS claim_text, "
                    f"       verdict AS label, published_at, explanation AS explanation_snippet, "
                    f"       0.0 AS rank "
                    f"FROM fact_checks WHERE {where_like} LIMIT ?",
                    [*params_like, limit * 2],
                ).fetchall()
                for r in rows:
                    if r["id"] not in seen:
                        results.append(dict(r))
                        seen.add(r["id"])
                        if len(results) >= limit:
                            break
        return results



    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(fact_checks)")}
        if "verdict_origin" not in cols:
            conn.execute(
                "ALTER TABLE fact_checks ADD COLUMN verdict_origin TEXT NOT NULL DEFAULT ''"
            )
        if "labeled_at" not in cols:
            conn.execute("ALTER TABLE fact_checks ADD COLUMN labeled_at TEXT")
        if "claim_origin" not in cols:
            # Where the claim text came from, mirroring verdict_origin:
            #   ''       the collector copied the headline (the common case)
            #   'source' the publisher stated the claim separately (AFP does)
            #   'llm'    extracted from the article by the local model
            #   'human'  written or corrected by a reviewer
            conn.execute("ALTER TABLE fact_checks ADD COLUMN "
                         "claim_origin TEXT NOT NULL DEFAULT ''")
            # AFP is the one collector that already stored a real claim rather
            # than a copy of the headline, so mark those as publisher-supplied.
            conn.execute("UPDATE fact_checks SET claim_origin='source' "
                         "WHERE source='afp' AND claim <> '' AND claim <> title")

    def upsert_many(self, records: Iterable[FactCheckRecord]) -> int:
        sql = """INSERT INTO fact_checks (
          source, source_id, source_url, title, claim, explanation, verdict, category,
          published_at, updated_at, language, image_url, fingerprint, raw_json,
          collected_at, first_seen_at, last_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(source, source_id) DO UPDATE SET
          source_url=excluded.source_url, title=excluded.title,
          -- A claim written by a human or extracted by the model is not
          -- re-derivable from the feed, so a re-sync must not clobber it.
          -- The headline still refreshes; only the curated claim is held.
          claim=CASE WHEN fact_checks.claim_origin IN ('human','llm')
                     THEN fact_checks.claim ELSE excluded.claim END,
          explanation=excluded.explanation,
          verdict=CASE WHEN fact_checks.verdict_origin='human'
                       THEN fact_checks.verdict ELSE excluded.verdict END,
          category=excluded.category, published_at=excluded.published_at,
          updated_at=excluded.updated_at, language=excluded.language,
          image_url=excluded.image_url, raw_json=excluded.raw_json,
          collected_at=excluded.collected_at, last_seen_at=excluded.last_seen_at"""
        now = utc_now()
        rows = []
        for r in records:
            rows.append((r.source, r.source_id, r.source_url, r.title, r.claim,
                         r.explanation, r.verdict, r.category, r.published_at,
                         r.updated_at, r.language, r.image_url, r.fingerprint,
                         json.dumps(r.raw, ensure_ascii=False), r.collected_at, now, now))
        if not rows:
            return 0
        with self.connect() as conn:
            conn.executemany(sql, rows)
        return len(rows)

    def count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM fact_checks").fetchone()[0])

    def start_run(self, source: str, mode: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO sync_runs(source,mode,started_at,status) VALUES(?,?,?,'running')",
                (source, mode, utc_now()),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, *, status: str, records: int, error: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE sync_runs SET finished_at=?,status=?,records_seen=?,error=? WHERE id=?",
                (utc_now(), status, records, error, run_id),
            )

    def mark_source(self, source: str, mode: str, records: int, last_record_id: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO source_state(source,mode,last_success_at,last_record_id,records_seen,complete)
                   VALUES(?,?,?,?,?,1) ON CONFLICT(source,mode) DO UPDATE SET
                   last_success_at=excluded.last_success_at,last_record_id=excluded.last_record_id,
                   records_seen=excluded.records_seen,complete=1""",
                (source, mode, utc_now(), last_record_id, records),
            )

    def coverage(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT source,COUNT(*) records,MIN(published_at) oldest,
                          MAX(published_at) newest,MAX(last_seen_at) last_seen
                   FROM fact_checks GROUP BY source ORDER BY source"""
            ).fetchall()
        return [dict(row) for row in rows]
