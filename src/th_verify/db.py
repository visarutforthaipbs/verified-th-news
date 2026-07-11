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

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(fact_checks)")}
        if "verdict_origin" not in cols:
            conn.execute(
                "ALTER TABLE fact_checks ADD COLUMN verdict_origin TEXT NOT NULL DEFAULT ''"
            )
        if "labeled_at" not in cols:
            conn.execute("ALTER TABLE fact_checks ADD COLUMN labeled_at TEXT")

    def upsert_many(self, records: Iterable[FactCheckRecord]) -> int:
        sql = """INSERT INTO fact_checks (
          source, source_id, source_url, title, claim, explanation, verdict, category,
          published_at, updated_at, language, image_url, fingerprint, raw_json,
          collected_at, first_seen_at, last_seen_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(source, source_id) DO UPDATE SET
          source_url=excluded.source_url, title=excluded.title, claim=excluded.claim,
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
