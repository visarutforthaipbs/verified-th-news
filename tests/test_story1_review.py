import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _blank_sheets(tmp_path, imp):
    """Blank copies of the two sheets (the real ones now hold human answers)."""
    out = {}
    for k, src in imp.SHEETS.items():
        h, rows = imp.rd(src)
        for r in rows:
            r["human_pure"] = r["human_note"] = ""
        p = tmp_path / f"orig_{k}.csv"
        with p.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=h); w.writeheader(); w.writerows(rows)
        out[k] = p
    return out


def _export(tmp_path, mutate=None):
    imp = load("import_story1_purity_review")
    imp.SHEETS = _blank_sheets(tmp_path, imp)
    h, rows = imp.rd(imp.SHEETS["A"])
    for i, r in enumerate(rows[:6]):
        r["human_pure"] = ["1", "0", "?", "1", "", "0"][i]
    r0 = rows[0]; r0["human_note"] = 'มี, "เครื่องหมาย"'
    if mutate:
        mutate(rows)
    p = tmp_path / "ex.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=h); w.writeheader(); w.writerows(rows)
    return imp, p


def test_valid_export_passes(tmp_path):
    imp, p = _export(tmp_path)
    sh, rows, errs = imp.validate(p, imp.SHEETS)
    assert sh == "A" and errs == []
    assert rows[0]["human_note"] == 'มี, "เครื่องหมาย"'


def test_bad_value_and_tampered_column_are_caught(tmp_path):
    def mutate(rows):
        rows[1]["human_pure"] = "yes"
        rows[2]["title"] = "แก้ชื่อ"
    imp, p = _export(tmp_path, mutate)
    _, _, errs = imp.validate(p, imp.SHEETS)
    assert any("human_pure" in e for e in errs) and any("title" in e for e in errs)


def test_wilson_interval_bounds():
    imp = load("import_story1_purity_review")
    lo, hi = imp.wilson(63, 70)
    assert 0.79 < lo < 0.82 and 0.94 < hi < 0.96
    assert imp.wilson(0, 0) is None
