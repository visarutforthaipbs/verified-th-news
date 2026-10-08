# AGENTS.md — TH Verify (read this first)

Thai fact-check archive (5 publishers → SQLite, `data/th_verify.db`, not in git) plus the analysis behind **two longform news articles**:

1. **Story 1** — how 11 years (2015–2026) of fake news in Thailand changed (topic shares over time).
2. **Story 2** — how fake news / narratives about migrants in Thailand changed.

The human owner writes the articles. **Your job is the data side:** keep numbers correct, keep claims within what the data supports, and unblock the human steps. Current state and next steps: `HANDOFF.md` (top section). Per-story status: `docs/STORIES.md`. Run index: `runs/INDEX.md`. Script map: `scripts/README.md`. Test: `.venv/bin/python -m pytest -q` (119 pass).

## Non-negotiable rules
- **Canonical method = `docs/METHODOLOGY_BERTOPIC_V2.md`** (E5 → UMAP → HDBSCAN → BERTopic; humans code narrative frames). `docs/historical/` and `scripts/legacy_story_v1/` are the superseded keyword-taxonomy (T01–T10) era. Never quote their numbers as current findings.
- **Topic ≠ narrative frame.** Use shares not raw counts (publisher mix changes); keep noise in denominators; show denominators; 2015 and 2026 are partial years. Dates are review-publication dates, not when a hoax started. Unit = fact-check record, not unique hoax or reach.
- **Never fabricate** quotes, interviewees, or scenes in drafts. Field-reporting slots are marked 【นักข่าวเติม】; items needing source-page checks are 【ตรวจก่อนใช้】.
- **Do not present assistant (AI) labels as human-validated.** Story 2's scope (118 in-scope) is assistant-screened; `human_scope` / `human_frame` are empty everywhere. TypeSafe "Jev" agreement with the assistant is agreement, not accuracy.
- **Runs are versioned and immutable.** New analysis → new dir `runs/YYYYMMDD_<name>_vNNN/` with a manifest (input hashes, params). Never edit or overwrite an existing run. The raw DB is never modified by analysis.
- **Five scripts are hash-pinned** in published manifests: `discovered_timeline.py`, `migrant_discovered_review.py`, `check_discovery_leakage.py`, `render_discovered_timeline.py`, `build_journalist_handoff.py` (`tests/test_journalist_handoff.py` checks one). Do not edit/move them without re-running the run and its manifest.
- `data/reports/journalist_handoff_2026-09-08/` is the **frozen corpus input** to the canonical run — not a superseded deliverable. `data/reports/label_conflicts.json` is read by `src/th_verify/api.py` — keep it there.
- Ops scripts (`daily_sync.sh`, collectors, backfills) run on another machine and are documented in `HANDOFF.md`; don't move them.
- Repo is public. `data/`, `deliverables/`, `.env`, `_archive/` and large run artifacts (`runs/**/*.npy|jsonl|ipynb|html`) are gitignored. Never commit LLM payloads or secrets. **Owner decision 2026-10-08:** run CSVs that contain claim text (e.g. `assignments.csv`) and the article drafts under `runs/` ARE committed and public; `deliverables/` (coding sheets, owner's answers, review apps) stays out. **Don't commit/push unless the user asks.**
- Analyst groupings (e.g., "investment family" of topics) are judgement, not model output — label them so.
- **`_archive/` is superseded material** consolidated from other folders on this Mac (keyword-era package, a pre-BERTopic Codex track, a non-canonical gpu01 bge-m3 run, an abandoned fork). Never cite numbers from it; a grep hit there is not a current finding. See `_archive/README.md`.

## Layout
`src/th_verify/` package · `tests/` · `scripts/` (ops, collectors, periodic reports, shared `_*.py`, current story pipeline; `legacy_story_v1/`) · `runs/` analysis runs · `deliverables/` journalist packages + `story2_coding/` (gitignored) · `docs/` · `data/` (gitignored; DB, reports; `data/reports/_legacy/` = stale pre-audit reports). · `_archive/` (gitignored; superseded, see rule above).

## Canonical facts (re-verified from `runs/20260908_bertopic_v001/assignments.csv`)
14,429 records (false 11,899 / misleading 2,465 / altered_media 65), 2015-05-30 → 2026-09-01, snapshot cut 2026-09-02; AFNC 10,356 (71.8%). 13,377 unique texts → 64 topics, noise 2,324 (16.11%); cluster count depends on params (min size 15/30/50/80 → 161/64/43/33). Story 2 queue 332 (128 keyword + 204 semantic) → assistant-in-scope 118 (AFNC 90). Details and caveats in the story docs.

## Conventions
Thai for journalist-facing docs; English for code/ops docs. Match surrounding code style. Prefer small versioned scripts under `scripts/` that read from a run and write a new run; add a test when logic is non-trivial. When you finish a unit of work, update `HANDOFF.md` (top section) and `docs/STORIES.md`.
