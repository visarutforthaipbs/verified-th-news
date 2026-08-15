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


def test_multi_source_review_queue(monkeypatch, tmp_path):
    db_path = tmp_path / "queue_test.db"
    monkeypatch.delenv("TH_VERIFY_READONLY", raising=False)
    monkeypatch.setenv("TH_VERIFY_DATABASE_PATH", str(db_path))
    import th_verify.api as api
    importlib.reload(api)
    r = Repository(db_path)
    r.initialize()
    r.upsert_many([
        make_record(source="cofact", source_id="c1", title="ข่าว Cofact", verdict="unknown"),
        make_record(source="sure_share", source_id="s1", title="ข่าว SureShare", verdict="unknown"),
    ])
    from fastapi.testclient import TestClient
    with TestClient(api.app) as client:
        res_all = client.get("/review/queue?source=all")
        assert res_all.status_code == 200
        data_all = res_all.json()
        assert data_all["total"] == 2

        res_cofact = client.get("/review/queue?source=cofact")
        assert res_cofact.status_code == 200
        data_cofact = res_cofact.json()
        assert data_cofact["total"] == 1
        assert data_cofact["items"][0]["source"] == "cofact"


def test_review_queue_sorting(monkeypatch, tmp_path):
    db_path = tmp_path / "sort_test.db"
    monkeypatch.delenv("TH_VERIFY_READONLY", raising=False)
    monkeypatch.setenv("TH_VERIFY_DATABASE_PATH", str(db_path))
    import th_verify.api as api
    importlib.reload(api)
    r = Repository(db_path)
    r.initialize()
    r.upsert_many([
        make_record(source="cofact", source_id="c1", title="ข่าวเก่า", published_at="2020-01-01T00:00:00Z"),
        make_record(source="cofact", source_id="c2", title="ข่าวใหม่", published_at="2026-07-01T00:00:00Z"),
    ])
    from fastapi.testclient import TestClient
    with TestClient(api.app) as client:
        res_asc = client.get("/review/queue?order=asc")
        items_asc = res_asc.json()["items"]
        assert items_asc[0]["title"] == "ข่าวเก่า"

        res_desc = client.get("/review/queue?order=desc")
        items_desc = res_desc.json()["items"]
        assert items_desc[0]["title"] == "ข่าวใหม่"


def test_fts5_search_indexing(repo):
    repo.upsert_many([
        make_record(source="afnc", source_id="f1", title="ข่าวลือวัคซีนโควิด", explanation="อย่าเชื่อการแอบอ้าง"),
    ])
    results = repo.search_fts("วัคซีนโควิด")
    assert len(results) >= 1
    assert "วัคซีน" in results[0]["title"]




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


# ── 7. thaipbs verdicts come from the article, never a neighbouring card ───

THAIPBS_LISTING = """
<html><body><div class="wrapper">
  <div class="card">
    <a href="/verify/content/111">ข่าวจริง เรื่องหนึ่งที่เป็นความจริง</a>
    <span>21 พ.ค. 69 | สังคม</span>
  </div>
  <div class="card">
    <a href="/verify/content/222">คลิปอ้างเหตุการณ์หนึ่ง แท้จริงเป็นคลิปเก่า</a>
    <span>20 พ.ค. 69 | รอบโลก</span>
  </div>
</div></body></html>
"""

CLAIM_REVIEW_PAGE = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[{"@type":"ClaimReview",
 "datePublished":"2026-05-20",
 "reviewRating":{"@type":"Rating","ratingValue":"5","bestRating":5,
                 "alternateName":"%s"}}]}
</script></head>
<body><article class="single-content"><p>เนื้อหาการตรวจสอบ</p></article></body></html>
"""


def test_claim_review_prefers_alternate_name_over_rating_value():
    """ratingValue does not track the label - Thai PBS ships ratingValue 5
    alongside 'ภาพปลอม'. Only alternateName may be trusted."""
    from selectolax.parser import HTMLParser
    from th_verify.collectors.thaipbs import parse_claim_review

    verdict, published = parse_claim_review(HTMLParser(CLAIM_REVIEW_PAGE % "ภาพปลอม"))
    assert verdict == "ภาพปลอม"
    assert published == "2026-05-20"


def test_listing_container_never_spans_two_articles():
    """The container walk must stop at the card boundary.

    The original walk only checked a 140-character floor and overshot into the
    multi-card wrapper, so every record cut from it inherited the first card's
    verdict and date. That corrupted gold-tier labels in the training exports.
    """
    from selectolax.parser import HTMLParser
    from th_verify.collectors.thaipbs import _spans_multiple_articles

    tree = HTMLParser(THAIPBS_LISTING)
    wrapper = tree.css_first("div.wrapper")
    assert _spans_multiple_articles(wrapper), "wrapper holds two cards and must be rejected"
    for card in tree.css("div.card"):
        assert not _spans_multiple_articles(card), "a single card must be accepted"


def test_thaipbs_collect_does_not_borrow_neighbour_verdict():
    """End-to-end: the second card must not inherit the first card's verdict."""
    import httpx
    from th_verify.collectors.thaipbs import ThaiPbsCollector

    pages = {
        "https://www.thaipbs.or.th/verify/category/all": THAIPBS_LISTING,
        "https://www.thaipbs.or.th/verify/content/111": CLAIM_REVIEW_PAGE % "ข่าวจริง",
        "https://www.thaipbs.or.th/verify/content/222": CLAIM_REVIEW_PAGE % "ข่าวปลอม",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=pages[str(request.url).split("?")[0]])

    async def run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return [r async for r in ThaiPbsCollector(client).collect(mode="delta")]

    records = {r.source_id: r for r in asyncio.run(run())}
    assert records["111"].verdict == "ข่าวจริง"
    assert records["222"].verdict == "ข่าวปลอม", "second card inherited the first card's verdict"
    assert records["222"].published_at == "2026-05-20"


def test_thaipbs_published_date_is_never_in_the_future():
    """A date scraped out of claim text ('เริ่ม 1 มิ.ย. - 30 ก.ย. 69') is not a
    publication date. ClaimReview datePublished must win."""
    from selectolax.parser import HTMLParser
    from th_verify.collectors.thaipbs import parse_claim_review, parse_thai_date

    # The old fallback would happily read a future date out of claim prose.
    assert parse_thai_date("เริ่ม 1 มิ.ย. – 30 ก.ย. 69") == "2026-09-30"
    # ClaimReview supplies the real one, so the fallback is never reached.
    verdict, published = parse_claim_review(HTMLParser(CLAIM_REVIEW_PAGE % "ข่าวจริง"))
    assert published == "2026-05-20"


# ── 8. non-fact-check content is excluded, the labelling backlog is not ────

def test_is_factcheck_excludes_broadcast_and_sections():
    from th_verify.normalized import is_factcheck
    # roundup formats state no verdict on any single claim
    assert not is_factcheck("sure_share", "🔴ไมโครพลาสติก | ชัวร์ก่อนแชร์ LIVE EP. 265", "unknown")
    assert not is_factcheck("sure_share", "ระวัง AI ล้วงข้อมูล | ชัวร์ก่อนแชร์ PODCAST", "unknown")
    assert not is_factcheck("sure_share", "สมองมนุษย์มีกี่เซลล์ ? | HIGHLIGHT", "unknown")
    # AFNC ships its knowledge base and event notices through the same feed,
    # with the section name landing in the verdict column
    assert not is_factcheck("afnc", "วิธีดูแลสุขภาพหน้าฝน", "คลังความรู้")
    assert not is_factcheck("afnc", "กิจกรรมวันเด็ก", "กิจกรรม")


def test_is_factcheck_keeps_unlabelled_claims():
    """The backlog must survive the filter.

    5,646 Sure & Share records have no verdict yet; they are fact-checks
    awaiting a label, not noise. Excluding rows merely because their verdict
    does not normalise would delete the very queue the ASR pipeline exists to
    work through -- and would silently shrink every count that depends on it.
    """
    from th_verify.normalized import is_factcheck
    assert is_factcheck("sure_share", "ต้องรีบเปลี่ยนบัตรเอทีเอ็ม จริงหรือ?", "unknown")
    assert is_factcheck("sure_share", "กินก๋วยเตี๋ยวต้องเลี่ยงเส้นเล็ก จริงหรือ ?", "")
    assert is_factcheck("thaipbs", "คลิปอ้างเหตุการณ์หนึ่ง", "ข่าวปลอม")
    assert is_factcheck("afnc", "ข่าวปลอม อย่าแชร์! เรื่องหนึ่ง", "ข่าวปลอม")


def test_brief_fetch_drops_non_factcheck_rows(repo):
    """fetch() is the single door every report goes through, so the filter has
    to live there rather than in each generator."""
    repo.upsert_many([
        make_record(source="afnc", source_id="k1", title="บทความคลังความรู้",
                    verdict="คลังความรู้", published_at="2026-06-05T00:00:00"),
        make_record(source="sure_share", source_id="b1",
                    title="เรื่องหนึ่ง | ชัวร์ก่อนแชร์ LIVE EP. 100",
                    verdict="unknown", published_at="2026-06-05T00:00:00"),
        make_record(source="afnc", source_id="a2", verdict="ข่าวปลอม",
                    title="ข่าวปลอม อย่าแชร์! เรื่องจริงจัง",
                    published_at="2026-06-06T00:00:00"),
    ])
    with repo.connect() as conn:
        conn.execute("UPDATE fact_checks SET verdict_origin='source'")
    from build_brief import fetch
    with repo.connect() as conn:
        rows = fetch(conn, "2026-06-01", "2026-07-01")
    ids = {r["source"] for r in rows}
    assert ids == {"afnc"}, "only the real fact-check should survive"
    assert len(rows) == 1


def test_cofact_article_categories_excluded():
    """Cofact is a blog: its WordPress category sits ahead of the title in the
    stored explanation. Commentary, event notices and the weekly roundup are not
    adjudicable claims, and were being served to human reviewers to skip by hand.
    Detected from the publisher's own taxonomy, not guessed from wording."""
    from th_verify.normalized import is_factcheck
    art = "บทความ ปฏิบัติการปล่อยข่าวเท็จ-บิดเบือนเรื่องศาสนา จากเลือกตั้ง"
    assert not is_factcheck("cofact", "ปฏิบัติการปล่อยข่าวเท็จ-บิดเบือนเรื่องศาสนา จากเลือกตั้ง", "unknown", art)
    ev = "กิจกรรม อบรมเชิงปฏิบัติการตรวจสอบข่าว"
    assert not is_factcheck("cofact", "อบรมเชิงปฏิบัติการตรวจสอบข่าว", "unknown", ev)
    wk = "ข่าวลวงประจำสัปดาห์ สรุปข่าวลวงรอบสัปดาห์ที่ผ่านมา"
    assert not is_factcheck("cofact", "สรุปข่าวลวงรอบสัปดาห์ที่ผ่านมา", "unknown", wk)


def test_cofact_real_factchecks_survive():
    """The claim-check categories must not be swept up with the essays."""
    from th_verify.normalized import is_factcheck
    fc = "Top Fact Checks Political กกต. ให้ผู้สมัคร ส.ส. ส่งประวัติเป็น ซีดีรอม ?"
    assert is_factcheck("cofact", "กกต. ให้ผู้สมัคร ส.ส. ส่งประวัติเป็น ซีดีรอม ?", "unknown", fc)
    q = "จริงหรือไม่ ? ภาพจากวิดีโอเกมถูกนำมาอ้างเท็จ"
    assert is_factcheck("cofact", "ภาพจากวิดีโอเกมถูกนำมาอ้างเท็จ", "unknown", q)
    # and a record with no explanation must not be dropped for lack of a category
    assert is_factcheck("cofact", "ข้อความบางอย่าง", "unknown", "")
