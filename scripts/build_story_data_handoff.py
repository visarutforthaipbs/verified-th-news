#!/usr/bin/env python3
"""Build a versioned, non-destructive journalist handoff for stories 1 and 2."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runs/20260908_bertopic_v001"
OUT = ROOT / "deliverables/journalist_handoff_20260914"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(df: pd.DataFrame, name: str) -> Path:
    path = OUT / name
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    assignments = pd.read_csv(SOURCE / "assignments.csv", dtype={"id": str})
    topics = pd.read_csv(SOURCE / "topics.csv")
    editorial_ids = set(pd.read_csv(SOURCE / "residual_editorial_review.csv", dtype={"id": str})["id"])

    topic_fields = topics[[
        "topic_id", "machine_keywords", "records", "unique_texts", "share_pct",
        "first_year", "last_year", "peak_share_year", "representative_id",
        "representative_claim", "representative_url", "review_status",
    ]].rename(columns={
        "records": "topic_records", "unique_texts": "topic_unique_texts",
        "share_pct": "topic_archive_share_pct", "review_status": "topic_review_status",
    })
    story1 = assignments.merge(topic_fields, on="topic_id", how="left", validate="many_to_one")
    story1["partial_calendar_year"] = story1["year"].isin([2015, 2026])
    story1["topic_assignment_status"] = story1["topic_id"].map(
        lambda value: "hdbscan_noise" if value == -1 else "machine_discovered_topic"
    )
    story1["editorial_leakage_review_flag"] = story1["id"].isin(editorial_ids)
    save(story1, "story1_full_records.csv")
    save(topics, "story1_topic_summary.csv")
    save(pd.read_csv(SOURCE / "topic_timeline.csv"), "story1_topic_timeline.csv")
    save(pd.read_csv(SOURCE / "editorial_period_comparisons.csv"), "story1_period_comparisons.csv")
    save(pd.read_csv(SOURCE / "source_balanced_tests.csv"), "story1_source_balanced_tests.csv")
    save(pd.read_csv(SOURCE / "adjacent_year_shifts.csv"), "story1_adjacent_year_shifts.csv")
    save(pd.read_csv(SOURCE / "recurring_text_families.csv"), "story1_recurring_text_families.csv")

    screened = pd.read_csv(SOURCE / "migrant_screened_assignments.csv", dtype={"id": str})
    screened_topics = pd.read_csv(SOURCE / "migrant_screened_topics.csv")
    screened = screened.merge(
        screened_topics.rename(columns={
            "subtopic_id": "screened_subtopic",
            "machine_keywords": "screened_subtopic_machine_keywords",
            "records": "screened_subtopic_records",
            "representative_ids": "screened_subtopic_representative_ids",
            "interpretation_status": "screened_subtopic_interpretation_status",
        }), on="screened_subtopic", how="left", validate="many_to_one",
    )
    screened["dataset_status"] = "assistant_in_scope_human_source_review_pending"
    screened["partial_calendar_year"] = screened["year"].isin([2015, 2026])
    save(screened, "story2_in_scope_records_human_review_pending.csv")

    review = pd.read_csv(SOURCE / "migrant_scope_decisions.csv", dtype={"id": str})
    review["dataset_status"] = review["assistant_scope"].map({
        "resident_refugee_status": "assistant_in_scope_human_source_review_pending",
        "crossborder_people_services": "assistant_in_scope_human_source_review_pending",
        "out_of_scope": "assistant_out_of_scope_human_review_pending",
        "unclear": "assistant_unclear_human_review_pending",
    })
    save(review, "story2_full_review_universe.csv")
    save(screened_topics, "story2_subtopic_summary.csv")
    save(pd.read_csv(SOURCE / "migrant_screened_timeline.csv"), "story2_subtopic_timeline.csv")
    save(pd.read_csv(SOURCE / "migrant_screened_exemplars.csv"), "story2_subtopic_exemplars.csv")
    save(pd.read_csv(SOURCE / "migrant_screened_sensitivity.csv"), "story2_model_sensitivity.csv")

    counts = {
        "source_run": str(SOURCE.relative_to(ROOT)),
        "story1_records": len(story1),
        "story1_unique_ids": int(story1["id"].nunique()),
        "story1_unique_exact_claim_texts": int(story1["claim_text"].nunique()),
        "story1_topics_excluding_noise": int((topics["topic_id"] != -1).sum()),
        "story1_noise_records": int((story1["topic_id"] == -1).sum()),
        "story1_editorial_leakage_review_queue": int(story1["editorial_leakage_review_flag"].sum()),
        "story2_review_universe": len(review),
        "story2_assistant_in_scope_human_pending": len(screened),
        "story2_assistant_out_of_scope_human_pending": int((review["assistant_scope"] == "out_of_scope").sum()),
        "story2_assistant_unclear_human_pending": int((review["assistant_scope"] == "unclear").sum()),
        "story2_human_review_completed": int((review["human_review_status"] != "pending").sum()),
    }
    (OUT / "qa_counts.json").write_text(json.dumps(counts, ensure_ascii=False, indent=2))

    csv_files = sorted(OUT.glob("*.csv"))
    manifest = {
        "source_files": {
            name: sha256(SOURCE / name) for name in [
                "assignments.csv", "topics.csv", "topic_timeline.csv",
                "migrant_scope_decisions.csv", "migrant_screened_assignments.csv",
            ]
        },
        "deliverable_csv_sha256": {path.name: sha256(path) for path in csv_files},
    }
    (OUT / "data_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(counts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
