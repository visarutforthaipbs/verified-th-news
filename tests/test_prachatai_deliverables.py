"""QA for the audited feature pair, not a certification of the legacy WebGL.

Reconcile rendered tables with delivered CSVs, keep other/unknown separate,
and prove the HTML and Markdown rebuild from the same numerical snapshot.
"""
import csv
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from selectolax.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data/reports"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "legacy_story_v1"))
from _audited_features import build_feature

STEMS = ("investigative_11years_feature", "migrant_deepdive_feature")
CSVS = ("article1_11years_claims.csv", "article2_migrant_claims.csv")


@pytest.fixture(scope="module")
def artifacts():
    result = []
    for stem, csv_name in zip(STEMS, CSVS):
        csv_path = REPORTS / "datasets" / csv_name
        if not csv_path.exists():
            pytest.skip("Delivered CSV snapshots are required for feature QA")
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        md = (REPORTS / f"{stem}.md").read_text()
        html = (REPORTS / f"{stem}.html").read_text()
        result.append((rows, md, HTMLParser(html), csv_path))
    return result


def body_rows(table):
    return [[cell.text() for cell in row.css("td")] for row in table.css("tbody tr")]


def share(n, total):
    return f"{n / total * 100:.2f}%"


def test_overview_topics_reconcile_to_csv_including_other(artifacts):
    rows, _, dom, _ = artifacts[0]
    counts = Counter(r["topic_code"] for r in rows)
    actual = body_rows(dom.css("table")[1])
    assert {r[0].split(" — ")[0]: int(r[1].replace(",", "")) for r in actual} == counts
    assert sum(int(r[1].replace(",", "")) for r in actual) == len(rows)
    assert all(r[2] == share(counts[r[0].split(" — ")[0]], len(rows)) for r in actual)
    assert "T99" in counts  # This category was visually suppressed in the old chart.


def test_overview_period_denominators_and_combined_finance(artifacts):
    rows, _, dom, _ = artifacts[0]
    actual = body_rows(dom.css("table")[0])
    periods = [(2015, 2018), (2019, 2021), (2022, 2023), (2024, 2025), (2026, 2026)]
    assert len(actual) == len(periods)
    for cells, (first, last) in zip(actual, periods):
        group = [r for r in rows if first <= int(r["published_year"]) <= last]
        counts = Counter(r["topic_code"] for r in group)
        assert cells[1:] == [f"{len(group):,}", share(counts["T01"], len(group)),
                             share(counts["T02"], len(group)),
                             share(counts["T03"] + counts["T04"], len(group))]
    assert "บางปี" in actual[-1][0]


def test_migrant_other_is_not_added_to_sovereignty(artifacts):
    rows, _, dom, _ = artifacts[1]
    counts = Counter(r["narrative_frame_id"] for r in rows)
    actual = body_rows(dom.css("table")[0])
    order = ["disease", "economic", "sovereignty", "broker", "other"]
    assert len(actual) == 5
    for cells, frame in zip(actual, order):
        assert cells[1:] == [f"{counts[frame]:,}", share(counts[frame], len(rows))]
    assert int(actual[2][1]) != counts["sovereignty"] + counts["other"]


def test_migrant_periods_include_all_frames_in_denominator(artifacts):
    rows, md, dom, _ = artifacts[1]
    actual = body_rows(dom.css("table")[1])
    for cells, (first, last, frame) in zip(actual, [(2020, 2021, "disease"),
                                                    (2022, 2023, "economic"),
                                                    (2024, 2026, "sovereignty")]):
        group = [r for r in rows if first <= int(r["published_year"]) <= last]
        count = sum(r["narrative_frame_id"] == frame for r in group)
        assert cells[2:] == [f"{count:,}/{len(group):,}", share(count, len(group))]
    annual = body_rows(dom.css("table")[2])
    years = Counter(r["published_year"] for r in rows)
    assert {str(int(r[0]) - 543): int(r[1].replace(",", "")) for r in annual} == years
    outside = sum(int(r["published_year"]) < 2020 or int(r["published_year"]) > 2026 for r in rows)
    assert f"อยู่นอกช่วงอีก {outside:,} บันทึก" in md


def test_verdicts_preserve_unknown_and_other_types(artifacts):
    expected = {"false", "true", "misleading", "unknown", "scam_alert", "altered_media", "satire"}
    for rows, md, dom, _ in artifacts:
        counts = Counter(r["verdict"] for r in rows)
        actual = body_rows(dom.css("table")[-1])
        mapped = {re.search(r"\(([^)]+)\)", r[0]).group(1): r for r in actual}
        assert set(mapped) == expected
        for key in expected:
            assert mapped[key][1:] == [f"{counts[key]:,}", share(counts[key], len(rows))]
        nonclaims = sum(r["verdict_origin"] == "human_not_claim" for r in rows)
        assert f"{nonclaims:,} บันทึก" in md


def test_html_and_markdown_have_identical_tables_and_prose(artifacts):
    for _, md, dom, _ in artifacts:
        md_tables = []
        for chunk in md.split("\n\n"):
            if chunk.startswith("| "):
                parsed = [[cell.strip() for cell in line.strip().strip("|").split("|")]
                          for line in chunk.splitlines()]
                md_tables.append([parsed[0], *parsed[2:]])
        html_tables = [[[cell.text() for cell in t.css("thead th")], *body_rows(t)]
                       for t in dom.css("table")]
        assert md_tables == html_tables
        for paragraph in dom.css("main p"):
            assert paragraph.text() in md
        assert dom.css_first("h1").text() in md
        assert len(dom.css("h1")) == 1


def test_stale_visuals_removed_sources_resolve_and_snapshots_identified(artifacts):
    for _, md, dom, csv_path in artifacts:
        assert not dom.css("img")  # Old images contain misleading labels/numbers.
        assert not dom.css("script[src]")
        assert not re.search(r"!\[[^\]]*\]\(", md)
        for anchor in dom.css("a"):
            url = urlsplit(anchor.attributes["href"])
            if not url.scheme and url.path:
                assert (REPORTS / unquote(url.path)).is_file()
            assert "network_graph.html" not in url.path
        assert hashlib.sha256(csv_path.read_bytes()).hexdigest() in md
        assert "ข้อมูลปี 2569 ยังไม่ครบปี" in md
        assert dom.css_first("button").attributes["onclick"] == "window.print()"
        for obsolete in ("2,038%", "+665%", "+501%", "26,894", "0.4161", "Orchestrated"):
            assert obsolete not in md


def test_rebuild_is_identical_and_does_not_modify_datasets(tmp_path, artifacts):
    before = [hashlib.sha256(path.read_bytes()).hexdigest() for *_, path in artifacts]
    for number, stem in enumerate(STEMS, 1):
        paths = build_feature(number, output=tmp_path)
        for path in paths:
            assert path.read_bytes() == (REPORTS / path.name).read_bytes()
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for *_, path in artifacts] == before
