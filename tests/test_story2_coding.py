import csv
import json
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_kappa_perfect_and_chance():
    sc = load("score_story2_coding")
    assert sc.kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert sc.kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == 0.0
    assert sc.kappa([], []) is None


def test_sheet_builder_is_blind_and_deterministic(tmp_path, monkeypatch):
    b = load("build_story2_coding_sheet")
    monkeypatch.setattr(b, "OUT", tmp_path / "out")
    assert b.main() == 0
    a = list(csv.DictReader((tmp_path / "out/coder_A.csv").open(encoding="utf-8-sig")))
    bb = list(csv.DictReader((tmp_path / "out/coder_B.csv").open(encoding="utf-8-sig")))
    assert len(a) == len(bb) == 332 and {r["id"] for r in a} == {r["id"] for r in bb}
    leaked = {"assistant_scope", "retrieval_route", "similarity", "screened_subtopic", "typesafe_scope"}
    assert not leaked & set(a[0])
    assert [r["phase"] for r in a[:30]] == ["calibration"] * 30 and a[30]["phase"] == "main"
    assert [r["id"] for r in a] != [r["id"] for r in bb]  # independent order
    assert all(not r["scope"] for r in a)
    # refuses to clobber sheets coders may have started on
    try:
        b.main()
    except SystemExit:
        pass
    else:
        raise AssertionError("expected refusal to overwrite")


def test_scorer_end_to_end(tmp_path):
    sc = load("score_story2_coding")
    cols = ["id", "url", "title", "scope", "note", "dehumanizing_language", "blamed_actor", "victim_actor"] + sc.FRAMES

    def write(name, rows):
        with (tmp_path / name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in cols})

    A = [{"id": "1", "scope": "resident_refugee_status", "frame_job_competition": "1"},
         {"id": "2", "scope": "out_of_scope"}, {"id": "3", "scope": "unclear"}]
    B = [{"id": "1", "scope": "resident_refugee_status", "frame_job_competition": "1"},
         {"id": "2", "scope": "out_of_scope"}, {"id": "3", "scope": "out_of_scope"}]
    write("a.csv", A)
    write("b.csv", B)
    import subprocess

    r = subprocess.run([sys.executable, str(ROOT / "scripts/score_story2_coding.py"), str(tmp_path / "a.csv"), str(tmp_path / "b.csv"),
                        "--master", str(tmp_path / "none.csv")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rows = list(csv.DictReader((tmp_path / "adjudication.csv").open(encoding="utf-8-sig")))
    assert [x["id"] for x in rows] == ["3"] and rows[0]["differs_on"] == "scope"


def test_coding_app_is_blind_and_complete(tmp_path, monkeypatch):
    """The solo app embeds only the coder's own sheet (all rows, no model columns) and a retest sample of ids."""
    import json
    import re
    b = load("build_story2_coding_sheet")
    monkeypatch.setattr(b, "OUT", tmp_path)
    assert b.main() == 0
    app = load("build_story2_coding_app")
    assert app.main(tmp_path) == 0
    html = (tmp_path / "coding_app.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r"const ROWS = (\[.*?\]);\nconst RETEST_BASE", html, re.S).group(1))
    retest = json.loads(re.search(r"const RETEST_BASE = (\[.*?\]);\nconst KEY", html, re.S).group(1))
    sheet = list(csv.DictReader((tmp_path / "coder_A.csv").open(encoding="utf-8-sig")))
    assert [r["id"] for r in data] == [r["id"] for r in sheet]
    assert set(data[0]) == {"id", "source", "date", "verdict", "title", "claim_text", "url", "phase"}
    for leaked in ("assistant_scope", "retrieval_route", "similarity", "queue_round", "screened_subtopic"):
        assert leaked not in html
    assert len(retest) == len(set(retest)) == app.N_LIKELY_IN + app.N_LIKELY_OUT and set(retest) <= {r["id"] for r in sheet}
    assert len(retest) / len(sheet) >= 0.2 or len(sheet) != 513        # method doc 9.5: re-code at least 20%
    assert "__CODER__" not in html and "/*__DATA__*/" not in html and "/*__RETEST__*/" not in html


def _write_export(path, rows, cols):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\r\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def test_single_coder_scorer(tmp_path):
    sc = load("score_story2_coding")
    one = load("score_story2_single_coder")
    cols = ["id", "url", "title", "claim_text", "phase", "scope", "target_group", "note", "dehumanizing_language", "blamed_actor", "victim_actor", "coded_at"] + sc.FRAMES
    IN = "resident_refugee_status"
    main_rows = ([{"id": str(i), "scope": IN, "target_group": "china", "frame_job_competition": "1", "blamed_actor": "migrants", "victim_actor": "none"} for i in range(1, 11)]
                 + [{"id": str(i), "scope": "out_of_scope"} for i in range(11, 21)]
                 + [{"id": "21", "scope": "unclear"}])
    # retest: ids 1-10 and 11-15 and 21; disagree on 3 (scope), 4 (frame), 12 (scope), 21 resolved
    rt = []
    for i in list(range(1, 11)) + list(range(11, 16)) + [21]:
        r = {"id": str(i), "scope": IN, "target_group": "china", "frame_job_competition": "1", "blamed_actor": "migrants", "victim_actor": "none"} if i <= 10 else {"id": str(i), "scope": "out_of_scope"}
        if i == 3: r["scope"] = "out_of_scope"; r["target_group"] = ""; r["frame_job_competition"] = ""; r["blamed_actor"] = ""; r["victim_actor"] = ""
        if i == 4: r["frame_job_competition"] = ""; r["frame_criminality"] = "1"
        if i == 12: r["scope"] = IN; r.update(target_group="generic", frame_none="1", blamed_actor="none", victim_actor="none")
        if i == 21: r["scope"] = "out_of_scope"
        rt.append(r)
    _write_export(tmp_path / "main.csv", main_rows, cols)
    _write_export(tmp_path / "retest.csv", rt, cols)
    _write_export(tmp_path / "master.csv", [{"id": str(i), "assistant_scope": IN if i <= 8 else "out_of_scope"} for i in range(1, 22)],
                  ["id", "assistant_scope"])
    assert one.main([str(tmp_path / "main.csv"), str(tmp_path / "retest.csv"), "--master", str(tmp_path / "master.csv"), "--out", str(tmp_path / "o")]) == 0
    rep = json.loads((tmp_path / "o/self_consistency_report.json").read_text(encoding="utf-8"))
    assert rep["rows_retest"] == 16 and rep["rows_pass1"] == 21
    ids = [r["id"] for r in csv.DictReader((tmp_path / "o/self_disagreements.csv").open(encoding="utf-8-sig"))]
    assert set(ids) == {"3", "4", "12", "21"} and rep["rows_differing_from_self"] == 4   # 21: unclear -> out_of_scope is a scope change too
    # the paradox case: pass 1 used job_competition on every in-scope row, so kappa is uninformative, not "unstable"
    assert "kappa paradox" in rep["frames"]["frame_job_competition"]["verdict"]
    assert rep["frames"]["frame_job_competition"]["agreement"] == 0.889
    look = list(csv.DictReader((tmp_path / "o/ai_second_look.csv").open(encoding="utf-8-sig")))
    dirs = {r["id"]: r["direction"] for r in look}
    assert dirs["9"] == "coder_in_assistant_out" and dirs["10"] == "coder_in_assistant_out" and dirs["21"] == "coder_unclear"
    assert rep["unclear_in_pass1"] == {"rows": 1, "decided_in_retest": 1}
    assert rep["human_vs_assistant_in_out"]["rows"] == 21
