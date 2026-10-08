# Runs index

| Run | What | Status |
|---|---|---|
| `2026-08-14_v001`, `2026-09-03_v001` | keyword-taxonomy (T01–T10) topic/narrative metrics | **historical** — do not cite |
| `20260908_bertopic_v001` | **canonical** discovered-topic run: 14,429 records → 13,377 unique texts → 64 topics (16.1% noise); migrant subtopic screening; story outlines | exploratory, not human-validated |
| `20260914_embedding_ab_v001` | E5 passage vs query embedding A/B + seed sensitivity (`REPORT_TH.md`) | supporting evidence for model choice |
| `20260921_typesafe_pilot_v001` | TypeSafe "Jev" second-pass scope screening of the 332 migrant candidates, compared with assistant labels | pilot only; not truth labels |
| `20261004_viz_v001` | 2D UMAP display data for cluster figures (`display_only`) | visual aid; positions are not evidence |

Frozen corpus input for the canonical run: `data/reports/journalist_handoff_2026-09-08/` (`02_false_misleading_altered_records.csv`).
Journalist package built from it: `deliverables/journalist_handoff_20260914/` (`scripts/build_story_data_handoff.py`).
| `20261004_purity_v001` | purity/robustness checks on the canonical run: topic-family timelines, publisher-series artifacts (Sure&Share "LIVE Retrovert"), 30-row purity samples per named topic, Story 2 Cambodia sensitivity (`scripts/story_purity_checks.py`) | derived; families are an analyst grouping |

| `20261004_audit_v001` | end-to-end audit (data → method → insights → drafts): corpus rebuild, clustering re-run, publisher-switch check, near-duplicate collapse, seed stability, label basis, Story 2 recall probe (`scripts/audit_end_to_end.py`; read `AUDIT.md`) | assistant audit; findings F1–F6 change what the drafts may claim |

| `20261004_story1_by_publisher_v001` | Story 1 tables per publisher (topic groups × year × publisher, records vs distinct near-duplicate claims, Sure&Share shorts, Topic 0 reading sample) for draft v2 (`scripts/story1_by_publisher.py`) | derived; topic groups are an analyst grouping |

| `20261004_story2_queue_v002` | Story 2 review queue v2: 332 round-1 rows + 181 keyword-rule rows = 513; provisional assistant scope for new rows; in-scope by year and group marker (`scripts/story2_extend_queue.py`) | assistant-screened; input to the v2 coder sheets |

| `20261004_story2_interim_v002` | Story 2 interim tables on the v2 queue after the owner's scope decisions (foreign residents in, tourists out): in-scope by year/group/source, subtopic re-fit (9 + noise), record-level file (`scripts/story2_interim_analysis.py`) | assistant-screened; to be replaced by human-coded results |

| `20261007_story2_aicoded_v001` | Story 2 tables from the assistant's AI coding of the 513-row queue (156 in scope; AI-coded, not human-validated; owner chose no validation): by year/group/source/subtopic. Built by `scripts/story2_ai_analysis.py` from `deliverables/story2_coding/ai_coded/ai_coding_v1.csv`. Supersedes the 20261004 interim numbers in the Story 2 draft (v3). |

| `20261008_story2_viz_v001` | Story 2 figures from the AI-coded tables: in-scope records per year stacked by target group (other / Cambodia / Israel) with share of each year's archive, and a timeline of two claims AFNC fact-checked four times each. HTML + light PNG + tidy CSVs; `scripts/story2_viz.py`. AI-coded, not human-validated. |

**Not a run of this pipeline:** a separate gpu01 BERTopic fit (bge-m3, 27,231 rows incl. true/unknown, outliers forced into 30 topics) is kept in `_archive/2026-09-14_gpu01_bgem3_bertopic/`. It breaks the canonical rules — do not cite.
