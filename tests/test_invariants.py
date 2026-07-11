"""Regression tests for the invariants that protect gold data.

These encode design decisions that are easy to break silently in a refactor:

1. Human labels survive collector re-syncs (db.py upsert CASE clause).
2. The heuristic classifier never touches human-labeled rows.
3. Verdict-bearing title prefixes/suffixes are stripped from claims and
   inline verdict statements are detected (label-leakage guards).
4. Verdict normalization handles every known raw-string family, including
   source typos, and passes through already-normalized labels.
5. The read-only public instance exposes no labeling surface and
   rate-limits /check.
6. Client-facing brief data never presents heuristic-origin verdicts.

If one of these fails after a refactor, the refactor is wrong - not the test.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from th_verify.db import Repository
from th_verify.models import FactCheckRecord


def make_record(**kw) -> FactCheckRecord:
    base = dict(
        source="sure_share", source_id="vid-1",
        source_url="https://youtube.com/watch?v=x",
        title="ทดสอบ จริงหรือ?", verdict="unknown",
    )
    base.update(kw)
    return FactCheckRecord(**base)


@pytest.fixture
def repo(tmp_path):
    r = Repository(tmp_path / "test.db")
    r.initialize()
    return r


# ── 1. human labels survive re-sync ────────────────────────────────────────

def test_human_label_survives_collector_resync(repo):
    repo.upsert_many([make_record()])
    with repo.connect() as conn:
        conn.execute(
            "UPDATE fact_checks SET verdict='false', verdict_origin='human' "
            "WHERE source_id='vid-1'"
        )
    # collector re-syncs the same record, still claiming verdict=unknown
    repo.upsert_many([make_record(title="ทดสอบ จริงหรือ? (แก้ไขคำ)")])
    with repo.connect() as conn:
        row = conn.execute(
            "SELECT verdict, verdict_origin, title FROM fact_checks "
            "WHERE source_id='vid-1'"
        ).fetchone()
    assert row["verdict"] == "false", "human label was overwritten by re-sync"
    assert row["verdict_origin"] == "human"
    # non-verdict fields still refresh
    assert "แก้ไขคำ" in row["title"]


def test_non_human_verdict_still_updates_on_resync(repo):
    repo.upsert_many([make_record(source="afnc", verdict="ข่าวปลอม")])
    repo.upsert_many([make_record(source="afnc", verdict="ข่าวจริง")])
    with repo.connect() as conn:
        row = conn.execute(
            "SELECT verdict FROM fact_checks WHERE source_id='vid-1'"
        ).fetchone()
    assert row["verdict"] == "ข่าวจริง", "source corrections must flow through"


# ── 2. classifier never touches human rows ─────────────────────────────────

def test_classifier_skips_human_rows(repo):
    repo.upsert_many([make_record(
        title="ข่าวปลอม ห้ามแชร์ ทดสอบ",  # would match FAKE_KEYWORDS
        explanation="อย่าหลงเชื่อ ข้อมูลเท็จ",
    )])
    with repo.connect() as conn:
        conn.execute(
            "UPDATE fact_checks SET verdict_origin='human_skipped' "
            "WHERE source_id='vid-1'"
        )
    from th_verify.classifier import run_classification
    result = asyncio.run(run_classification(repo.path, api_key=None))
    assert result["total"] == 0, "classifier selected a human-touched row"
    with repo.connect() as conn:
        row = conn.execute("SELECT verdict FROM fact_checks").fetchone()
    assert row["verdict"] == "unknown"


def test_classifier_marks_output_heuristic(repo):
    repo.upsert_many([make_record(
        title="เตือน ข่าวปลอม ทดสอบ", explanation="อย่าแชร์ ข้อมูลเท็จ")])
    from th_verify.classifier import run_classification
    asyncio.run(run_classification(repo.path, api_key=None))
    with repo.connect() as conn:
        row = conn.execute(
            "SELECT verdict, verdict_origin FROM fact_checks").fetchone()
    if row["verdict"] != "unknown":
        assert row["verdict_origin"] == "heuristic", \
            "classifier output must carry heuristic provenance"


# ── 3. leakage guards ───────────────────────────────────────────────────────

@pytest.mark.parametrize("title,source,expect", [
    ("ข่าวปลอม อย่าแชร์! ยาพาราเซตามอลมีไวรัส", "afnc", "ยาพาราเซตามอลมีไวรัส"),
    ("ข่าวบิดเบือน อาการท้องผูกทำให้เป็นมะเร็ง", "afnc", "อาการท้องผูกทำให้เป็นมะเร็ง"),
    ("ข่าวจริง? กรมอุตุประกาศพายุ", "afnc", "กรมอุตุประกาศพายุ"),
    ("ชัวร์ก่อนแชร์ : กินหอยแล้วดื่มนมอันตราย จริงหรือ?", "sure_share",
     "กินหอยแล้วดื่มนมอันตราย"),
    ("ภาพปลอม: ภาพระเบิดกลางเมือง", "thaipbs", "ภาพระเบิดกลางเมือง"),
])
def test_clean_claim_strips_verdict_affixes(title, source, expect):
    from build_dataset import clean_claim
    assert clean_claim(title, source) == expect


@pytest.mark.parametrize("claim,leaks", [
    ("เฮลิคอปเตอร์ตก ตรวจสอบแล้วเป็นข่าวปลอม", True),
    ("สธ.เตือนอย่าเชื่อ ข่าวปลอมอ้างมีคนตาย", True),
    ("ธนาคารออมสินปล่อยสินเชื่อผ่านไลน์", False),
])
def test_inline_leak_detection(claim, leaks):
    from build_dataset import has_inline_leak
    assert has_inline_leak(claim) is leaks


# ── 4. verdict normalization ───────────────────────────────────────────────

@pytest.mark.parametrize("source,raw,expect", [
    ("afnc", "ข่าวปลอม", "false"),
    ("afp", "Flase", "false"),           # source typo must stay mapped
    ("afp", "Party False", "misleading"),
    ("afp", "FALSE", "false"),
    ("cofact", "ข่าวบิดเบือน", "misleading"),
    ("thaipbs", "ภาพปลอม", "altered_media"),
    ("sure_share", "false", "false"),     # human labels pass through
    ("sure_share", "unknown", "unknown"),
    ("afnc", "คลังความรู้", "unknown"),     # category values are not verdicts
    ("afnc", "อะไรใหม่ที่ไม่รู้จัก", "unknown"),  # unmapped falls to unknown
])
def test_normalize_verdict(source, raw, expect):
    from build_dataset import normalize_verdict
    assert normalize_verdict(source, raw) == expect


# ── 5. read-only public instance ───────────────────────────────────────────

@pytest.fixture
def readonly_client(monkeypatch, tmp_path):
    monkeypatch.setenv("TH_VERIFY_READONLY", "1")
    monkeypatch.setenv("TH_VERIFY_DATABASE_PATH", str(tmp_path / "ro.db"))
    import th_verify.api as api
    importlib.reload(api)
    from fastapi.testclient import TestClient
    with TestClient(api.app) as client:  # context manager runs startup (DB init)
        yield client
    monkeypatch.delenv("TH_VERIFY_READONLY")
    importlib.reload(api)


def test_readonly_blocks_labeling_surface(readonly_client):
    assert readonly_client.get("/review").status_code == 404
    assert readonly_client.get("/review/queue").status_code == 404
    assert readonly_client.post(
        "/review/label", json={"id": 1, "verdict": "false"}
    ).status_code == 404
    assert readonly_client.get("/docs").status_code == 404
    assert readonly_client.get("/openapi.json").status_code == 404
    assert readonly_client.get("/").status_code == 200
    assert readonly_client.get("/health").status_code == 200


def test_readonly_rate_limits_check(readonly_client):
    codes = [
        readonly_client.post("/check", json={"text": "ทดสอบ rate limit"}).status_code
        for _ in range(25)
    ]
    assert 429 in codes, "rate limiter never engaged"
    assert codes[0] != 429, "rate limiter fired on the first request"


def test_private_instance_keeps_labeling_surface(monkeypatch, tmp_path):
    monkeypatch.delenv("TH_VERIFY_READONLY", raising=False)
    monkeypatch.setenv("TH_VERIFY_DATABASE_PATH", str(tmp_path / "priv.db"))
    import th_verify.api as api
    importlib.reload(api)
    from fastapi.testclient import TestClient
    with TestClient(api.app) as client:
        assert client.get("/review").status_code == 200
        assert client.get("/review/queue").status_code == 200


# ── 6. briefs never present heuristic verdicts ─────────────────────────────

def test_brief_fetch_demotes_heuristic_labels(repo):
    repo.upsert_many([
        make_record(source="cofact", source_id="c1", verdict="ข่าวปลอม",
                    published_at="2026-06-05T00:00:00"),
        make_record(source="afnc", source_id="a1", verdict="ข่าวปลอม",
                    published_at="2026-06-06T00:00:00"),
    ])
    with repo.connect() as conn:
        conn.execute("UPDATE fact_checks SET verdict_origin='heuristic' "
                     "WHERE source_id='c1'")
        conn.execute("UPDATE fact_checks SET verdict_origin='source' "
                     "WHERE source_id='a1'")
    from build_brief import fetch
    with repo.connect() as conn:
        rows = fetch(conn, "2026-06-01", "2026-07-01")
    by_id = {r["source"]: r["label"] for r in rows}
    assert by_id["cofact"] == "unknown", "heuristic verdict leaked into brief"
    assert by_id["afnc"] == "false"
