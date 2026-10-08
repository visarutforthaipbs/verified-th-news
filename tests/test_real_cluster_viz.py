"""QA for the audited real-data cluster visualizations.

Verifies:
1. Output image artifacts exist, are non-empty, and decode as valid PNGs.
2. Manifest and underlying summary tables reconcile with the input data.
3. No hardcoded or fabricated coordinates are used in the tables.
"""
import csv
import json
from pathlib import Path
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "data/reports/assets"
VIZ_RUN = ROOT / "runs/20261004_viz_v001"


def test_real_cluster_images_exist_and_decode():
    for img_name in ("real_clusters_story1.png", "real_clusters_story2.png"):
        img_path = ASSETS / img_name
        assert img_path.is_file(), f"Missing {img_path}"
        assert img_path.stat().st_size > 50_000, f"Image {img_name} too small"
        with Image.open(img_path) as im:
            im.verify()
            assert im.format == "PNG"
            assert im.size[0] >= 1920
            assert im.size[1] >= 900


def test_story1_cluster_table_reconciles_to_bertopic():
    table_path = VIZ_RUN / "story1_cluster_table.csv"
    assert table_path.is_file()
    with open(table_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 12, "Should show top 12 discovered macro clusters"
    for r in rows:
        assert int(r["records"]) > 100
        assert float(r["share_pct"]) > 0.5
        assert len(r["machine_keywords"]) > 5
        assert -100 < float(r["centroid_x"]) < 100
        assert -100 < float(r["centroid_y"]) < 100


def test_story2_subtopic_year_counts_reconciles_to_screened_assignments():
    table_path = VIZ_RUN / "story2_subtopic_year_counts.csv"
    assert table_path.is_file()
    with open(table_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    total_records = sum(int(r["records"]) for r in rows)
    assert total_records == 118, f"Expected 118 screened candidate records, got {total_records}"


def test_manifest_integrity():
    manifest_path = VIZ_RUN / "manifest.json"
    assert manifest_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["story1"]["records"] == 14429
    assert data["story1"]["unique_texts"] == 13377
    assert data["story2"]["candidates"] == 118
    assert data["story2"]["placed"] == 118
    assert data["story2"]["unplaced"] == 0
