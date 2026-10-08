# scripts/ index

- **Ops / collection** (run on the lighthouse nodes; paths documented in `HANDOFF.md`): `daily_sync.sh`, `audit_collectors.py`, `daily_monitor.py`,
  `build_dataset.py`, `extract_claims.py`, `recheck_extracted_claims.py`, `repair_thaipbs_verdicts.py`, `backfill_*.py`, `import_asr_evidence.py`, `llm_assist.py`, `asr/`
- **Periodic reports / products** (not for the two articles): `build_brief.py`, `build_weekly_*.py`, `build_daily_trend.py`, `build_issue_*.py`, `narrative_shift.py`, `find_cross_source_conflicts.py`, `issue_topics/`
- **Shared libs**: `_brand.py`, `_charts.py`, `_pdf.py`, `_freshness.py`, `_canonical.py`
- **Current story pipeline** (keep in place — first five are hash-pinned in manifests):
  `build_journalist_handoff.py` → corpus snapshot · `discovered_timeline.py` → BERTopic fit · `migrant_discovered_review.py` → migrant scope/subtopics ·
  `check_discovery_leakage.py` · `render_discovered_timeline.py` · `benchmark_embedding_models.py` · `typesafe_migrant_pilot.py` + `analyze_typesafe_pilot.py` ·
  `generate_real_cluster_viz.py` · `build_story_data_handoff.py` → `deliverables/`
- **Story 2 human coding**: `build_story2_coding_sheet.py` (blind sheets → `deliverables/story2_coding/`) · `build_story2_coding_app.py` (offline one-file web app for the single coder, with a blind test-retest pass, from `assets/story2_coding_app/template.html`; exports the sheet's CSV format) · `score_story2_single_coder.py` (test-retest kappa + self-disagreement list + AI second-look list; replaces the A/B scorer for this project) · `score_story2_coding.py` (kappa + adjudication queue) · codebook `docs/story2_codebook_th.md`
- **`legacy_story_v1/`**: keyword-era builders (3D/2D graphs, infographics, audited features, phase-0 audit). Flagged by the 2026-09-08 audit as hard-coded or non-data-driven; don't use for the articles.
- `launch_agent_team.py` is an SSH helper for another machine, unrelated to the analysis.
- `story2_ai_coding_tools.py` — parser for the assistant's compact AI codings (one line per row); `story2_build_ai_coded.py` — builds `deliverables/story2_coding/ai_coded/ai_coding_v1.csv` + summary; `story2_ai_analysis.py` — Story 2 tables from that CSV into `runs/20261007_story2_aicoded_v001/`. All outputs are AI-coded, never human-coded.
- `story1_viz_publisher_year.py` — Story 1 figure 1 (records per year stacked by publisher); `story1_viz_virus_impersonation.py` — figures 2 (virus share by publisher) and 3 (AFNC agency-impersonation records vs distinct claims). Self-contained HTML (tooltip, table view, light/dark) in `runs/20261007_story1_viz_v001/`; PNGs via headless Chrome with `?theme=light&export=1`.
- `story2_viz.py` — Story 2 figures (records per year by target group; recurring-claims timeline) into `runs/20261008_story2_viz_v001/`; shares chart chrome with `story1_viz_virus_impersonation.py`. `build_cluster_explorer.py` — interactive cluster map; `?export=map&theme=light` renders the static article figure.
