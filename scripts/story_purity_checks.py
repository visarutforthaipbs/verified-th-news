#!/usr/bin/env python3
"""Data-side checks that decide how far Story 1 / Story 2 claims can be pushed.

Read-only on the canonical run (runs/20260908_bertopic_v001); writes a new versioned
run runs/20261004_purity_v001/ with:

  topic_family_timeline.csv   year x family counts/shares (families = ANALYST grouping of fitted topics, see FAMILIES)
  publisher_series_artifacts.csv   records from re-verification series (e.g. Sure&Share "LIVE Retrovert") by year/topic
  named_topic_samples.csv     seeded 30-row samples per topic named in Story 1, for human purity reading
  story2_cambodia_sensitivity.csv   Story 2 in-scope counts/shares with and without Cambodia-mentioning claims
  manifest.json               input hashes + parameters

Family membership is a keyword-based judgement of the fitted topics' machine keywords,
not a model output; treat family numbers as a robustness check on single-topic claims.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/20260908_bertopic_v001"
OUT = ROOT / "runs/20261004_purity_v001"
SEED = 7
SAMPLE_N = 30
NAMED = {1: "invest_dividend", 2: "driving_licence", 4: "virus_prevent_cure", 7: "infection_outbreak", 11: "victim_refund", 18: "vaccine", 6: "border_military"}
FAMILIES = {
    "invest_stock": [1, 15, 24, 25, 38, 44, 45, 50, 62],
    "bank_loan": [3, 12, 14, 22, 34, 36, 47],
    "victim_refund": [11, 61],
    "covid_related": [4, 7, 18, 48, 58],
}
SERIES = {"sure_share_live_retrovert": r"Retrovert"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    a = pd.read_csv(RUN / "assignments.csv", encoding="utf-8-sig")
    m = pd.read_csv(RUN / "migrant_screened_assignments.csv", encoding="utf-8-sig")
    OUT.mkdir(exist_ok=True)
    tot = a.groupby("year").size()

    rows = []
    for fam, ids in FAMILIES.items():
        cnt = a[a.topic_id.isin(ids)].groupby("year").size().reindex(tot.index, fill_value=0)
        for y in tot.index:
            rows.append(dict(family=fam, topics="|".join(map(str, ids)), year=int(y), records=int(cnt[y]),
                             denominator=int(tot[y]), share_pct=round(cnt[y] / tot[y] * 100, 2)))
    pd.DataFrame(rows).to_csv(OUT / "topic_family_timeline.csv", index=False, encoding="utf-8-sig")

    srows = []
    for name, pat in SERIES.items():
        hit = a[a.title.str.contains(pat, na=False) | a.claim_text.str.contains(pat, na=False)]
        for (y, t), g in hit.groupby(["year", "topic_id"]):
            srows.append(dict(series=name, year=int(y), topic_id=int(t), records=len(g), sources="|".join(sorted(g.source.unique())),
                              topic_year_total=int(((a.year == y) & (a.topic_id == t)).sum())))
    pd.DataFrame(srows).to_csv(OUT / "publisher_series_artifacts.csv", index=False, encoding="utf-8-sig")

    samp = []
    for t, label in NAMED.items():
        s = a[a.topic_id == t].sample(min(SAMPLE_N, (a.topic_id == t).sum()), random_state=SEED).sort_values(["year", "id"])
        for _, r in s.iterrows():
            samp.append(dict(topic_id=t, topic_label_draft=label, id=r.id, year=r.year, source=r.source, title=r.title, url=r.url,
                             human_pure="", human_note=""))
    pd.DataFrame(samp).to_csv(OUT / "named_topic_samples.csv", index=False, encoding="utf-8-sig")

    cam = m.claim_text.str.contains("กัมพูชา|เขมร", na=False) | m.title.str.contains("กัมพูชา|เขมร", na=False)
    crow = []
    for y in sorted(m.year.unique()):
        s = m[m.year == y]
        c = cam[s.index]
        crow.append(dict(year=int(y), in_scope_all=len(s), mention_cambodia=int(c.sum()), without_cambodia=int((~c).sum()),
                         denominator=int(tot[y]), share_all_pct=round(len(s) / tot[y] * 100, 2),
                         share_without_cambodia_pct=round((~c).sum() / tot[y] * 100, 2)))
    pd.DataFrame(crow).to_csv(OUT / "story2_cambodia_sensitivity.csv", index=False, encoding="utf-8-sig")

    (OUT / "manifest.json").write_text(json.dumps({
        "script": "scripts/story_purity_checks.py", "seed": SEED, "sample_n": SAMPLE_N, "families": FAMILIES,
        "inputs": {f"runs/20260908_bertopic_v001/{n}": sha(RUN / n) for n in ("assignments.csv", "migrant_screened_assignments.csv")},
        "note": "families are an analyst keyword grouping; samples are for human purity reading (human_pure empty)"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
