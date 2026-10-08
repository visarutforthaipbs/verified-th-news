# The two articles — status

Canonical run: `runs/20260908_bertopic_v001` · method: `docs/METHODOLOGY_BERTOPIC_V2.md` · package: `deliverables/journalist_handoff_20260914/`

## Story 1 — 11 years of Thai fake news
- Outline: `runs/20260908_bertopic_v001/story_1_model_outline_th.md` (draft: `story_1_draft_th.md`)
- **Draft v2 (2026-10-04) is reframed: all 11 years, told publisher by publisher, no blended trend line.** Tables: `runs/20261004_story1_by_publisher_v001/` (`scripts/story1_by_publisher.py`). Previous draft kept there as `story_1_draft_th_before_reframe.md`. The "lead finding" below is the pre-audit framing and is superseded: robust = virus topics rise in 2020 and fade by 2023 in Sure&Share, AFNC and AFP separately; agency-impersonation topics are AFNC-only (0% → ~13% of AFNC output from 2023) and are a few templates repeated page by page.
- Lead finding (exploratory): post-COVID, checked items shift from virus cures/outbreaks (7.8%→0.2%, 2020–21 vs 2024–25) toward
  specific services/scams (online driving-licence 0.04%→4.2%, victim-refund claims 0%→3.3%, border/military 0.1%→3.2%).
- Data checks done 2026-10-04 (`runs/20261004_purity_v001`): vaccine 2024 bump is mostly a Sure&Share "LIVE Retrovert" series (30/38) → don't use as trend; Topic 1 drop ≠ fewer investment scams (9-topic investment family ~9–11% 2023–25); named-topic sample reading by assistant found topics 4, 11 pure, 7 mixed (COVID cases + flu/HIV + 1 misfit), 2 has stray rows.
- Open before publication:
  - 82 records with residual verdict/warning wording in claim text (`residual_editorial_review.csv`); topic 54 clusters by correction phrasing.
  - Topics 0 (5,292 records, mixed health/food) and 4/7 (virus/outbreak) are impure → human naming/check of all quoted topics.
  - Cluster counts depend on parameters (161/64/43/33 for min size 15/30/50/80); leak-exclusion rerun gives 56 clusters (ARI 0.848).
  - Source-balanced permutation tests are exploratory only.
  - Unit = fact-check record, not unique hoax or reach; 2015 and 2026 are partial years.

## Story 2 — migrants
- Draft: `runs/20260908_bertopic_v001/story_2_draft_th.md` (written 2026-10-04; numbers re-checked from CSVs) · Outline: `story_2_model_outline_th.md`
- Scope is assistant-screened only: 332 candidates → 118 proposed in-scope, 7 ambiguous, 207 proposed out (`migrant_scope_decisions.csv`).
- Subtopic model finds 6 mixed subtopics + 11 noise; it does **not** confirm the old "three-act" (disease → economic → political) story.
- Findings the data supports: in-scope share of archive ~0.3% (2020–22) → 1.36% (2025) → 3.62% (2026, partial); 76% of in-scope records are AFNC;
  56% of 2025–26 in-scope records mention Cambodia (border-conflict wave) — the recent rise is not evidence of a general narrative shift.
- Coding kit ready: `docs/story2_codebook_th.md`, sheets in `deliverables/story2_coding/` (2 blind coders × 332 rows, 30 calibration), scorer `scripts/score_story2_coding.py`.
- Open before publication:
  - Journalist review of scope decisions against source pages.
  - `human_frame` column is empty — narrative frames (perpetrator/victim/rights/threat) are not yet coded by a person.
  - Recurring 5-occupation-unlock claim falls into noise; subtopic labels are not hate-speech/frame judgments.
  - TypeSafe Jev second-pass screen (`runs/20260921_typesafe_pilot_v001`, disagreements in `pilot_scope_disagreements.csv`) must be checked against journalist-coded data; Thai accuracy is unverified.

## Audit 2026-10-04 (`runs/20261004_audit_v001/AUDIT.md`)
- Story 1: numbers verified; **frame needs revision** — trend claims only for 2020–2025 (publisher switch in 2020), rising topics are AFNC near-duplicate templates, drop the source-balanced sentence, disclose that Sure&Share/Cofact verdicts are project-assigned.
- Story 2: numbers verified; **queue has a recall gap** (≥7 relevant records never screened) — extend queue and reissue coder sheets before human coding.
- **Story 2 queue v2 (2026-10-04):** queue extended 332 → 513 rows (`runs/20261004_story2_queue_v002/`, `scripts/story2_extend_queue.py`); assistant in-scope 118 → 167, unclear 7 → 28. New storylines the first queue never retrieved: Israelis/Jews "settling" in Thailand (19), Chinese residents (7), Myanmar entitlement claims (6), Cambodian children's schooling (12). Coder sheets reissued (513 rows, 30 calibration, new `target_group` column), codebook v1.1. The Story 2 draft carries a banner; its body numbers are still round 1 and must be rewritten after the editor's scope decision.
- **Story 2 draft v2 (2026-10-04):** owner decided scope = foreign residents of any origin in, tourists out. Draft rewritten on the v2 queue with interim (assistant-screened) numbers from `runs/20261004_story2_interim_v002/` (`scripts/story2_interim_analysis.py`): 167 in scope (AFNC 128 = 76.6%), 126 in 2025–26, 9 subtopics + 29 unclustered. Storylines: recurring claims (5 occupations ×4, "smuggled into Phuket" ×4), documents/citizenship, Myanmar entitlement claims, Cambodia wave (56 of 126 late records), schooling (2 → 2 → 17), Israelis "settling" (19, 2025–26). 2020 was outbreak-related (5 of 6 records). Still not publishable until human coding replaces every number.
- **Story 2 coding is solo (2026-10-07):** one editor codes all 513 rows in `deliverables/story2_coding/coding_app.html`; reliability = blind re-code of ≥20% after 48 h (test-retest), scored by `scripts/score_story2_single_coder.py`. Not inter-coder; the article must say so. SOP: `deliverables/story2_coding/SOP_TH.md`.
- **Story 2 AI-coded (2026-10-07):** owner declined to code; the assistant coded all 513 rows (`deliverables/story2_coding/ai_coded/`, `scripts/story2_build_ai_coded.py`, tables via `scripts/story2_ai_analysis.py` → `runs/20261007_story2_aicoded_v001/`): 156 in scope (114 resident + 42 crossborder), 17 unclear, 340 out; AFNC 120 (76.9%); 117 in 2025–26; Cambodia 51 of 117; Israel 17; 2020 = 5 (4 covid-linked). Owner chose **no human validation** (option A). Agreement with owner's 30 hand-coded rows is weak (scope 19/30; in/out 21/30), so the draft (v3) uses record counts and quoted examples only — no frame percentages, no "how society is led to see migrants" claims. Article must say "AI-coded, not human-validated". Supersedes the solo-coding entry above; the v2 draft is kept as `runs/20261004_story2_interim_v002/story_2_draft_th_v2_screened167.md`.
- **Long-form article drafts (2026-10-07/08):** `runs/20260908_bertopic_v001/story_1_article_th.md` (4 embedded figures; purity read applied) and `story_2_article_th.md` (2 embedded figures from `runs/20261008_story2_viz_v001/`, built by `scripts/story2_viz.py`). Both are reader-facing drafts with 【เติม】 interview slots and 【ตรวจ】 source checks still open; Story 2 numbers are AI-coded and unvalidated, so it reports counts and cited examples only.
