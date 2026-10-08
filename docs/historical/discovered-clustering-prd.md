# PRD: Discovered Topic Clustering (E5 → UMAP → HDBSCAN)

Status: **historical specification; exploratory implementation now available.**

Update 2026-09-08: an exploratory implementation now exists in `scripts/discovered_timeline.py` and `scripts/migrant_discovered_review.py`, with actual fitted outputs under `runs/20260908_bertopic_v001/`. The specification below is retained as historical intent. The audited fixed snapshot, exact-text reuse, noise-inclusive denominators, corrected exploratory source-balanced testing, and assistant-only scope screening differ from this initial spec; see the run's `README_TH.md`. This is not human-validated narrative analysis.
Originally written for implementation in Claude Code against this repo. Read `METHODOLOGY.md` and `EMBEDDING_BENCHMARK.md`
first — this document extends Layer A of the existing pipeline, it does not
replace the verdict taxonomy or Layer B's narrative-drift method.

## 1. Problem

`METHODOLOGY.md` §4's Layer A topics (T01–T10) come from a hand-written
compound-keyword classifier (`clustering_method: "semantic_taxonomy_medoid"`
in `runs/2026-08-14_v001/config.yaml`). Summing the documented shares — 19.4 +
5.7 + 7.4 + 4.4 + 2.2 + 2.8 + 1.6 + 2.6 + 1.9 + 1.9 — accounts for **49.9% of
the corpus**. The other half of 11 years of fact-checks is structurally
invisible to the topic timeline and to the Jensen-Shannon change-point
detection in §5: a theme nobody wrote keywords for cannot appear in either.

Embeddings already exist for the whole corpus (`intfloat/multilingual-e5-small`,
384-dim, L2-normalized — see `EMBEDDING_BENCHMARK.md`) but today they are only
used for (a) picking each keyword-topic's medoid claim, and (b) k-means
clustering *within* the single T06 migrant topic in `scripts/narrative_shift.py`.
Nothing currently discovers topics from the vectors across the full archive.

Two deliverables need this fixed:

- **Story 1** (11-year overview) needs a topic inventory that covers the
  archive, not one gated by which keywords got written in advance.
- **Story 2** (migrant narrative drift) needs cluster-level granularity that
  isn't hand-phased, and a way to check whether the existing three-act framing
  in §7 (disease-vector → economic-threat → political-rights) is something the
  data actually supports unsupervised, or something the keyword filter primed
  us to see.

## 2. Goal

One clustering run answers, with a documented method rather than a judgment
call: **how many distinct claim clusters exist in the corpus, and how does
each cluster's share of the archive change year over year (2015–2026)?**

Two report scopes come out of the same run:

1. Whole-corpus: cluster count, sizes, per-cluster timelines/shares, change
   points, and a reconciliation against T01–T10.
2. Migrant-only slice: the subset of clusters matching T06, given the same
   timeline treatment at finer grain.

## 3. Non-goals

- Not a replacement for the 6-class verdict taxonomy (`false`/`true`/
  `misleading`/…) — clusters describe claim *subject*, verdict stays separate.
- Not automatic label generation. A human names each cluster from its medoid
  + exemplars, exactly as `narrative_shift.py` already does — its own
  docstring is explicit that machine-invented cluster labels are not
  trustworthy, and that holds here too.
- Not a live service. This is a batch run producing dated, versioned
  artifacts under `runs/`, like the existing `2026-08-14_v001`.

## 4. Data inputs

- **Corpus**: rebuild via `scripts/build_dataset.py --db <fresh snapshot>
  --out data/exports_<date>` at run time, not a stale checked-in export.
  (A run against the 2026-09-03 snapshot produced 20,680 docs after excluding
  6,425 non-claim/knowledge-base records — `คลังความรู้`, `ข่าวอื่นๆ`,
  `กิจกรรม`, etc. — and removing 1,896 duplicates.)
- **Embeddings**: generate via `th_verify.search.build_index()` — do not
  hand-roll a second embedding path. Same call the `/check` endpoint uses, so
  the clustering index and retrieval index never drift apart. Frozen config:
  `intfloat/multilingual-e5-small`, 384-dim, L2-normalized, `passage: ` prefix,
  batch size 256. (2026-09-03 run: 20,596 vectors after the <10-char claim
  filter, encoded in ~157s on lighthouse-core's CPU.)
- **Freshness gate**: call `_freshness.assert_fresh(conn, strict=True)` before
  running. This pipeline exists because of a prior incident (`_freshness.py`'s
  own docstring) where a report was built from a 16-day-stale copy; don't
  repeat it here.

## 5. Method

### 5.1 Dimensionality reduction (UMAP)

- `metric="cosine"` — matches E5's native similarity space.
- `n_components=10` for the clustering embedding (preserves structure without
  HDBSCAN's curse-of-dimensionality). Run a **separate** `n_components=2` UMAP
  purely for visualization — never read distances off the 2-D projection as if
  they were real.
- `n_neighbors=15`, `min_dist=0.0`, `random_state=42` — frozen and logged in
  `config.yaml`, per the project's existing reproducibility tenet
  (`METHODOLOGY.md` §1, tenet 4).

### 5.2 Clustering (HDBSCAN)

- `metric="euclidean"` on the UMAP-reduced space (cosine stops being
  meaningful post-UMAP).
- `min_cluster_size`: start at 30 (~0.15% of the corpus), but **run a
  sensitivity sweep at 15 / 30 / 50 / 80** and log cluster-count vs. noise-%
  for each in `metrics.json` before freezing a value. Too low over-splits into
  near-duplicate clusters; too high forces real small themes into noise. This
  sweep is what makes the eventual choice defensible instead of arbitrary —
  the same transparency gap the keyword taxonomy has (nobody can audit why
  T01–T10 are the ten topics).
- `cluster_selection_method="eom"`, `min_samples=5` — both logged.
- **Noise is not a bug.** Cluster `-1` means "doesn't fit an existing theme."
  Report the noise percentage explicitly; never silently drop or force-assign
  it into the nearest cluster.

### 5.3 Cluster labeling

For each non-noise cluster, the medoid is the real claim closest to the
cluster centroid **in the original 384-d cosine space**, not UMAP space (UMAP
distances aren't metric-preserving — don't make closeness claims from it).
Same convention as `METHODOLOGY.md` §4.1. A human reads the medoid plus five
nearest exemplars and writes the name.

### 5.4 Reconciliation against T01–T10

Cross-tab discovered clusters against the existing keyword-taxonomy label
(join on claim id). Output: for each discovered cluster, its taxonomy-label
distribution, and vice versa. **Flag clusters with no dominant taxonomy
label** — these are the previously-invisible themes. That list is the
headline finding for Story 1's methodology section, not an afterthought.

## 6. Time-series analysis

Per cluster, using `published_at` already present in `meta.jsonl` (no DB join
needed):

- **Raw counts per cluster per year** (`cluster_timeline_counts.csv`) — for
  "when did X first appear."
- **Proportional share per year** (`cluster_timeline_share.csv`) — count
  divided by that year's total clustered claims. This is the metric that's
  actually comparable across years; raw counts alone are distorted by
  publisher expansion (`METHODOLOGY.md` §1, tenet 2 — e.g. AFNC launching in
  late 2019).
- **Change-point detection**: reuse the existing JSD method (§5 of
  `METHODOLOGY.md`) on the discovered-cluster share vectors. Check whether the
  documented ranking (2019→2020 pandemic, 2024→2025 sovereignty/AI,
  2022→2023 financialization) survives on the unsupervised topic set, or
  whether new inflection points surface that the keyword taxonomy couldn't
  see by construction.
- **Significance testing**: reuse blocked permutation testing exactly as
  specified in §6 (N=2,000, Benjamini-Hochberg FDR at α=0.05, blocked by
  source publisher), applied per discovered cluster instead of per keyword
  topic.

## 7. Story-specific outputs

### 7.1 Story 1 — 11-year overview

- `clusters_summary.csv` — cluster id, size, share of corpus, year min/max,
  peak year, medoid claim + id, human-assigned name (blank until reviewed).
- `cluster_timeline_share.csv` — pivot, cluster × year.
- `change_points_discovered.csv` — JSD ranking on discovered clusters.
- `reconciliation.csv` — discovered cluster vs. T01–T10 crosstab, with the
  "previously invisible" flag from §5.4.

### 7.2 Story 2 — migrant narrative drift

- Filter to clusters matching T06 by **both** keyword overlap and cosine
  similarity to existing T06 exemplars — report the two methods' disagreement
  explicitly; where they diverge is itself informative, not noise to average
  away.
- Give matched clusters the same timeline/share treatment at finer grain than
  the single T06 bucket. This is what lets "how the narrative changed" be an
  *emergent* finding — separate clusters for pandemic-scapegoat vs.
  economic-competition vs. sovereignty-panic framing, distinguished by the
  data — rather than the three-act structure in `METHODOLOGY.md` §7 being
  written by hand first and confirmed after.
- Explicitly cross-check: does discovered clustering recover the existing
  three phases, refine them, or contradict them? All three outcomes are
  reportable; write down which one happened.

## 8. Reproducibility artifacts

Mirror the existing convention — `runs/<YYYYMMDD>_discovered_v001/` containing:

- `config.yaml` — every hyperparameter in §5, frozen.
- `clusters_summary.csv`, `cluster_timeline_counts.csv`,
  `cluster_timeline_share.csv`, `change_points_discovered.csv`,
  `reconciliation.csv`
- `metrics.json` — permutation test results, FDR-adjusted p-values, the
  min_cluster_size sensitivity sweep.
- `cluster_assignments.jsonl` — every claim id → cluster id, for audit and
  drill-down.

Non-destructive throughout — never writes to `th_verify.db`, per
`METHODOLOGY.md` §1 tenet 4. Clusters are a derived, versioned artifact.

## 9. Environment notes (from a build spike on lighthouse-core, 2026-09-03)

- `~/th-verify/.venv` is `uv`-managed and has **no `pip` binary** — install
  with `uv pip install --python .venv/bin/python <pkg>`, not `pip install`.
- `torch` + `sentence-transformers` are already installed and working there.
- `umap-learn`'s dependency chain (`pynndescent` → `llvmlite`) has **no
  prebuilt wheel** for the version it resolves to by default (`llvmlite`
  0.49) on this Mac (Intel x86_64, cp312), and fails building from source
  (no LLVM toolchain present). **Fix**: `uv pip install llvmlite==0.43.0
  numba==0.60.0` first — these do have prebuilt macOS x86_64 wheels — then
  `umap-learn` installs clean on top.
- `hdbscan` and `pandas` installed with no issues via plain `uv pip install`.
- Confirmed working set: `umap-learn==0.5.12`, `numba==0.60.0`,
  `llvmlite==0.43.0`, current `hdbscan`, current `pandas`. Worth freezing
  these into a `clustering` extras group in `pyproject.toml` so the next
  person doesn't rediscover the llvmlite pin.
- Run the actual UMAP/HDBSCAN compute on **lighthouse-core** (or gpu01), not
  in a disk-constrained sandbox — `torch` + `transformers` alone can exceed
  an 8–10GB disk cap before UMAP or HDBSCAN even get installed.

## 10. Open questions to resolve during implementation (non-blocking)

- Final `min_cluster_size` — pick after eyeballing the §5.2 sensitivity sweep,
  don't freeze 30 in advance.
- Cosine-similarity threshold for "matches T06" in §7.2 — needs a first pass
  over the similarity distribution before a cutoff is defensible.
- Whether discovered clusters **supplement** T01–T10 (recommended — the
  reconciliation table becomes a finding in its own right) or **replace**
  them for the published stories. Full replacement this close to publication
  carries more risk than the reconciliation approach.
