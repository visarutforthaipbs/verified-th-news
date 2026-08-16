# HANDOFF — Thai Fact-Check Database & Fake-News Detection

Last updated: 2026-08-14. State of the project for anyone (human or agent)
picking this up in a new session.

Architecture diagram (all three machines and every flow):
https://claude.ai/code/artifact/9041637f-9b56-4730-b098-88199cfa3469

Repo: https://github.com/visarutforthaipbs/verified-th-news — code and docs
only. `data/` (DB, exports, index, briefs, logs) and `.env` are NOT in git;
the canonical database lives on **lighthouse-core** (see Machine topology). A
fresh clone needs: `.env` with API keys, then `th-verify init` + `th-verify
sync all --mode backfill`, or rsync `data/` from lighthouse-core.

**Start here (2026-08-14).** The session of 2026-08-13/14 added a **news-feature
edition of the Issue Focus Report** and a **narrative-shift analyser**. Nothing
from that session is committed yet, and two decisions are waiting on the owner —
both are listed under "Open decisions (2026-08-14)" below. Read that section
first; it is where the work stopped, not where it failed.

Everything in that session was built and rendered against **this MacBook's dev
copy, which was 9–11 days stale** (newest record 2026-08-03). Every report
produced is therefore built on that snapshot. Regenerate on lighthouse-core, or
rsync `data/` down first, before any of it goes to a client.

The earlier open item from 2026-07-31 is closed: Thai PBS verdict contamination
was diagnosed, the collector fixed, and `repair_thaipbs_verdicts.py --apply` was
run against production (see that section below for the record).

## What this project is

A unified archive of Thai fact-checking work (**28,442 records** on production
as of 2026-07-31, 2015–present) from 5 sources, plus a semantic claim-search
service ("has this claim been fact-checked before?") and a human-labeling
workflow. End goal: data to train or fine-tune Thai fake-news detection models,
and a usable checking tool.

| source | records | what it is | labels |
|---|---|---|---|
| afnc | ~16.7k | ศูนย์ต่อต้านข่าวปลอม articles | native (ข่าวปลอม/จริง/บิดเบือน) |
| sure_share | ~9.3k | ชัวร์ก่อนแชร์ YouTube metadata | **no native labels** — being human-labeled now |
| cofact | ~1k | Cofact articles | mixed provenance (see Gotchas) |
| afp | ~0.7k | AFP Fact Check via Google API | native, messy raw strings |
| thaipbs | ~0.5k | Thai PBS Verify articles | native, verdict phrased in headline |

## Architecture / key paths

- `data/th_verify.db` — SQLite (WAL). Table `fact_checks` is the core;
  `verdict_origin` + `labeled_at` columns track label provenance.
- `src/th_verify/` — package: collectors, `db.py` (repository + migration),
  `api.py` (FastAPI), `search.py` (embedding index), `cli.py` (typer),
  `classifier.py` (heuristic/Gemini — **fenced, see Gotchas**),
  `static/index.html` (public check page), `static/review.html` (labeling UI).
- `scripts/build_dataset.py` — DB → train-ready exports in `data/exports/`:
  verdict normalization, leak-stripping, dedup, time-based splits, REPORT.md.
- `scripts/backfill_provenance.py` — one-off, already run (idempotent).
- `scripts/repair_thaipbs_verdicts.py` — re-derives thaipbs verdict/date/origin
  from the publisher's ClaimReview. Dry run by default. See the Thai PBS
  contamination section below before running it.
- `scripts/eval_verdict_extraction.py` — scores verdict extraction against the
  Thai PBS ClaimReview answer key, comparing any (model, prompt) pair so model
  choice and prompt wording can be separated. `--sweep` runs the grid,
  `--stratified` samples evenly per class (the archive is ~73% `false`, so a
  proportional sample cannot measure the false/misleading confusion),
  `--max-chars` trims article text — that dominates latency, 6000 chars runs
  ~30s/call against 3500 chars at ~2s/call. Applies the same verbatim-quote
  guard production uses, so scores reflect what would actually be written.
  Needs the GPU node awake and the 11435 tunnel up.
- `scripts/_freshness.py` — `assert_fresh(conn)`, called by every report builder.
  Prints a loud banner when the database snapshot is more than 2 days old, so a
  report can no longer silently claim the current week while summarising a
  two-week-old copy. Pass `strict=True` to make it refuse outright.
- `scripts/daily_sync.sh` — nightly job (see Automation).
- `scripts/build_brief.py` — monthly misinformation brief generator (the
  "Thai Misinfo Brief" product SKU): auto-fills stats, narrative clusters,
  recirculating hoaxes (semantic ≥0.95 vs pre-month index), scam patterns;
  analyst edits the `> ✍️` slots. Output: `data/briefs/brief_YYYY-MM.md`.
  Heuristic-origin labels are excluded from client-facing lists by design.
- `scripts/build_issue_report.py` — Issue Focus Report generator (the
  per-topic deep-dive SKU, added 2026-07-14): topic configs live in
  `scripts/issue_topics/<slug>.json` (keyword filter, category taxonomy,
  analyst-written insight/findings slots); everything quantitative is
  computed from the DB. Output: `data/reports/<slug>_report.html`
  (2-page A4, print-to-PDF button); `--publish PATH` copies it to a
  web-served folder. Heuristic-origin verdicts are demoted to "อื่นๆ"
  (same client-facing rule as briefs). First topic: `migrant`.
  `scripts/build_html_report.py` was the hardcoded prototype it replaces.
- `scripts/build_issue_feature.py` — **news-feature edition of the same SKU**
  (added 2026-08-14). Same topic configs and same database; a story rather than
  a white paper — headline, standfirst, narrative sections, pull quotes, case
  cards with links to the original fact-checks, and a "what to do" close.
  Outputs `data/reports/<slug>_feature.html` (long-scroll on screen, two-column
  A4 when printed) plus a PDF of the same file. Prose lives in
  `scripts/issue_topics/<slug>.story.json`, written by hand — **nothing in this
  script drafts prose**. Story strings carry `${total}`, `${peak_year_be}`,
  `${cat2_name}` … which are substituted at build time so hand-written sentences
  don't go stale; a story can also declare its own `counters` (keyword groups
  counted over title+claim) for lines about one pattern inside the topic. No
  story file → the report still builds, with loudly-marked analyst slots.
  `--init-story` writes a skeleton pre-filled with the topic's real numbers.
  Case cards are restricted to `source`/`human` verdicts — an aggregate can
  carry the `llm` tier's ~21% error rate, a card naming a publisher cannot.
  Stories written: `callcenter_scam`, `political_state`.
- `scripts/narrative_shift.py` — **finds the periods where a topic's narrative
  changed** (added 2026-08-14). Embeds the topic's claims, clusters them, and
  measures when each cluster's mass sits in time, with a permutation test. Does
  not name the clusters — see "Narrative-shift analysis" below.
- `scripts/_pdf.py` — the one Chrome-to-PDF invocation in the repo, shared by
  `build_weekly_fakenews_report.py` and `build_issue_feature.py`. Set `$CHROME`
  on a non-Mac host.
- `scripts/_charts.py` — inline SVG, no JS, no network. Added 2026-08-14:
  `columns()` (named categorical columns — years, months; `timeline()` is the
  daily version and cannot show a decade).
- **Topic configs now accept `match_fields`** (default: title+claim+explanation,
  i.e. unchanged for existing topics). Narrow it to `["title", "claim"]` for any
  topic whose vocabulary overlaps the *machinery* of fact-checking: AFNC
  explanations name the agency that confirmed the story, so `นายกรัฐมนตรี`
  matched 908 records over three fields and 19 over title+claim. The original
  `political_state` config matched 4,131 records of which a random 20-sample was
  mostly weather bulletins and farm subsidies; retuned (title+claim, political
  vocabulary, ครม. moved into a policy combo) it matches 518 with ~18/20
  precision, keeping 247 of the original 254 `false` records.
- `data/exports/` — classification_{train,val,test}.jsonl, rag_corpus.jsonl,
  verdict_mapping.csv, REPORT.md.
- `scripts/llm_assist.py` — local-LLM helpers via Ollama on aipower
  (verdict extraction with verbatim-quote guard; VerifyDesk summaries).
- `scripts/eval_retrieval.py` + `data/eval/retrieval_benchmark.jsonl` —
  frozen 50-query retrieval benchmark (see Quality assurance).
- `tests/test_invariants.py` — regression tests for the protection
  invariants (see Quality assurance).
- `docs/risk-triage-design.md` — full spec for the not-yet-built risk
  triage layer (business plan §4.3); read before implementing it.
- `data/pitch/` — Cofact pitch pack (Thai one-pager + 10-min demo script).
  Kept out of git deliberately (strategy docs; repo is public).
- `data/index/` — semantic search index (embeddings.npy + meta.jsonl).
- `.env` — API keys (GOOGLE_FACTCHECK_API_KEY for afp, YOUTUBE_API_KEY for
  sure_share). Not in git.

## Running things

```bash
# server (check page at /, labeling room at /review)
.venv/bin/uvicorn th_verify.api:app --port 8942

# refresh everything manually (sync → exports → search index)
/bin/zsh scripts/daily_sync.sh

# individual steps
.venv/bin/python -m th_verify.cli sync all --mode delta
.venv/bin/python scripts/build_dataset.py
.venv/bin/python -m th_verify.cli index

# quick claim lookup from terminal
.venv/bin/python -m th_verify.cli check "ข้อความที่สงสัย"

# reports — white paper (2-page A4) and news feature (web + PDF) for one topic
.venv/bin/python scripts/build_issue_report.py callcenter_scam
.venv/bin/python scripts/build_issue_feature.py callcenter_scam
.venv/bin/python scripts/build_issue_feature.py --list          # topics + story status
.venv/bin/python scripts/build_issue_feature.py <topic> --init-story

# find where a topic's narrative changed (prints clusters for a human to name)
.venv/bin/python scripts/narrative_shift.py migrant
.venv/bin/python scripts/narrative_shift.py migrant --k 8

# claim extraction (needs the GPU node; dry run first, always)
export OLLAMA_URL=http://lighthouse-gpu01:11434
.venv/bin/python scripts/extract_claims.py --source thaipbs --limit 40
.venv/bin/python scripts/extract_claims.py --source thaipbs --limit 700 --apply
.venv/bin/python scripts/recheck_extracted_claims.py            # after guard changes
.venv/bin/python scripts/recheck_extracted_claims.py --apply

# conflicts queue for /review?mode=conflicts (needs a current index)
.venv/bin/python scripts/find_cross_source_conflicts.py --threshold 0.94 --qa --limit 0

# tests
.venv/bin/python -m pytest -q
```

## Label provenance system (the most important design decision)

`fact_checks.verdict_origin` values, in trust order:

1. `source` — verdict from the fact-checking organization itself. Gold.
2. `human` — labeled by the project owner in /review. Gold.
   (`human_skipped` = human saw it, couldn't judge from the video.)
3. `heuristic` — keyword/Gemini guesses from `classifier.py`. Low trust.
   Do NOT treat as gold training labels.
4. `''` (empty) — unlabeled, or provenance implied by source at export time.

Protections in place (do not remove):
- `db.py upsert_many` keeps verdict when `verdict_origin='human'` — collector
  re-syncs cannot overwrite human labels (tested).
- `classifier.py` skips human rows and stamps its output `heuristic`.
- `build_dataset.py` exports `label_origin` per record so training can
  filter/weight by tier.

Two more `verdict_origin` values exist, both written only by /review:
`human_skipped` ("a claim, but I can't judge it") and `human_not_claim`
("this was never a claim"). They are deliberately distinct — collapsing them
loses the only signal that can retire an item permanently.

## Claim provenance (added 2026-08-16)

`claim` was a copy of `title` for 27,925 of 28,686 records, and a headline is
not a claim — Thai PBS routinely writes the answer into it
("โพสต์อ้างข่าวปลอม ตำรวจยศสูงไหว้นักการเมือง ชี้เป็นภาพ AI ตรวจสอบพบเป็นภาพจริง ปี 61"
where the claim is "ตำรวจยศสูงไหว้นักการเมือง"). Stored that way it leaks the
verdict into training data and shows a reviewer a summary where a claim belongs.

`fact_checks.claim_origin`, in trust order:

1. `source` — the publisher's own `ClaimReview.claimReviewed` (AFP, and Thai PBS
   where it differs from the headline). Gold.
2. `human` — corrected in /review with `E`. Gold.
3. `llm` — extracted by `scripts/extract_claims.py` and passed its guards.
4. `''` — still a copy of the title; `clean_claim()` handles it at export time.

Protections:
- `db.py upsert_many` keeps `claim` when `claim_origin IN ('human','llm')`.
- `build_dataset.py` keys `claim_text` on **provenance, not source name**. It
  used to read `if source == "afp"`, which silently dropped every extracted
  claim; the index went on embedding headlines. Tested now — do not narrow it
  back to a source check.
- `scripts/recheck_extracted_claims.py` replays the current guards over
  everything marked `llm` and reverts failures to `claim=title, claim_origin=''`.
  Run it after changing any guard; a reverted row is simply a candidate again.

Extraction guard notes (each one cost a bad batch to find):
- Overlap is measured on **character trigrams**, not whitespace tokens. Thai has
  no word spaces, so token overlap made a faithful short claim look unrelated —
  it rejected 85 of 555 Thai PBS extractions before the fix.
- `VERDICT_WORDS` must include Thai PBS's `พบเป็น` construction. It must **not**
  include `เท่านั้น` ("only"), which is ordinary vocabulary.
- A claim equal to the *raw* title is rejected, not just the cleaned one.

Model: `scb10x/typhoon2.5-qwen3-30b-a3b` on lighthouse-gpu01. It beat
qwen2.5:14b 12/12 vs 10/12 on the same Thai PBS sample. Acceptance varies a lot
by source — Thai PBS 82%, Cofact 78%, Sure & Share 83%, **AFNC only 20%**
(its `ข่าวปลอม อย่าแชร์!` titles are already claim-shaped and `clean_claim`
handles them, so AFNC is not worth a run).

## Conflicts review mode (added 2026-08-16)

`/review?mode=conflicts` adjudicates records where **our** machine label
contradicts a **publisher's** ruling on a claim the embeddings put at ≥0.94
similarity. `A` adopts theirs, `K` confirms ours; both write an ordinary
`human` label, because accepting someone else's finding is still the reviewer's
judgement. `1`–`5` are inert in this mode.

The pair list is precomputed by
`scripts/find_cross_source_conflicts.py --qa` (it needs the embedding index)
into `data/reports/label_conflicts.json`, but membership is re-checked against
the live DB per request, so answering a conflict retires it with no second
piece of state. Duplicate pairs collapse to the closest match.

Undo in this mode restores the record's **prior machine label** (the client
sends it back) rather than blanking it — blanking is right in the main queue
where nothing came before, but here it would destroy the guess under review.

## Human labeling (in progress)

Owner is labeling sure_share "จริงหรือ?" episodes at `/review`: embedded
YouTube player, keys 1=ปลอม 2=จริง 3=บิดเบือน 4=ดัดแปลง/AI 5=เตือนภัย S=skip
U=undo, plus N=`human_not_claim` and E=edit the claim. Every keypress saves to
DB immediately. Verdict is stated in the last ~20s of each video.
The queue includes heuristic-labeled episodes for verification; a human
label overwrites the heuristic one.

**524 human-labelled as of 2026-08-16** (was 164 on 2026-07-31; the jump is
mostly the ASR pipeline's 1,332 machine labels being verified, not hand
typing). The queue counter measures the *reviewer's* backlog — records still
needing a human — not the size of the archive; it read "3 / 14781" before that
was fixed, when one record was actually waiting.

Non-claims are filtered out of the queue (`is_factcheck`), which removed
~1,800 keystrokes of Cofact analysis articles, programme announcements and
weekly roundups that nobody can adjudicate.

## Machine topology (since 2026-07-11; names updated 2026-07-31)

Project Lighthouse renamed both server nodes. The **old aliases still resolve**
(`popmacmini` → `lighthouse-core`, `aipower` → `lighthouse-gpu01` in
`~/.ssh/config`), so existing scripts keep working — but prefer the new names in
anything you write.

- **lighthouse-core** (`ssh core`, was `popmacmini`; Intel Mac mini, 24/7) —
  **production home.** Project at `~/th-verify/` under user `visarutsankham`,
  canonical DB lives here. Services now run as **system LaunchDaemons** in
  `/Library/LaunchDaemons/` (not per-user agents), so they start without a GUI
  login — `launchctl list | grep thverify` in a user session shows nothing,
  which is expected and not an outage. Use `sudo launchctl list` or check
  `/Library/LaunchDaemons/com.thverify.*`:
  - `com.thverify.server` — private full instance, 0.0.0.0:8942, KeepAlive.
  - `com.thverify.public` — **read-only public instance**, 127.0.0.1:8943,
    env `TH_VERIFY_READONLY=1` (blocks /review*, /docs; rate-limits /check
    to 20/min/IP). This is what the tunnel exposes — never tunnel 8942.
  - `com.thverify.tunnel` — `~/bin/cloudflared` named tunnel
    `th-verify-public` → localhost:8943; config
    `~/.cloudflared/th-verify-public.yml`; routes **check-before.org** and
    www. Domain registered 2026-07-11 via Cloudflare. **Live and serving as of
    2026-07-31** — `curl https://check-before.org/health` returns 200; the
    delegation/SSL propagation noted earlier has completed.
  - `com.thverify.daily-sync` (03:30: delta sync → exports → index) and
    `com.thverify.monthly-brief` (1st of month 04:30 → data/briefs/).
  Users label at `http://lighthouse-core.local:8942/review` from any device.
  Note: Intel Mac needs pinned `torch==2.2.2` `sentence-transformers==3.4.1`
  `transformers==4.49.0` (newer torch has no Intel-Mac wheels).
- **lighthouse-gpu01** (`ssh gpu`, was `aipower`; Ubuntu, RTX 3090) — local LLM
  host, model `qwen2.5:14b`. **Two things changed here and both break the old
  instructions:** Ollama is now bound to `127.0.0.1:11434` only (Project
  Lighthouse closed its LAN exposure as risk R-05), and the node is **powered
  off by default** to save electricity. So `llm_assist.py` can no longer reach
  it over the LAN at all — the documented `192.168.31.19` was doubly wrong, as
  the node is `.17`. To use it: wake the node (Lighthouse's
  `scripts/wake-gpu.sh`), then tunnel on **port 11435**:

      ssh -N -L 11435:127.0.0.1:11434 gpu &
      export OLLAMA_URL=http://127.0.0.1:11435

  **Do not tunnel 11434 → 11434.** This MacBook runs its own Ollama on 11434
  with no models installed. ssh cannot bind the IPv4 address, quietly settles
  for IPv6 `[::1]`, and every request then resolves to the local empty Ollama —
  which reports `model 'qwen2.5:14b' not found` for a model that is demonstrably
  present on the GPU node. Verified live 2026-07-31; it cost a confusing detour.
  `llm_assist.py preflight()` now checks the model list once at startup and
  prints this exact remedy instead of a 404 per record.
- **MacBook** (this repo path, `~/Documents/antigravity/proud-nobel` — the
  directory name is an Antigravity IDE artifact, not a project name) — dev copy
  only. Its cron job was removed; do not run collectors here or the DBs
  diverge. **They have diverged**: as of 2026-07-31 this copy held 28,204
  records / 80 human labels against production's 28,442 / 164. Anything you
  generate locally (briefs, weekly reports, issue reports) is built on that
  stale snapshot — pull `data/` from production first, or generate on
  production. Deploy code changes with:
  `rsync -a --exclude .venv --exclude __pycache__ --exclude 'data/' ./ core:~/th-verify/`
  then restart: `ssh core 'sudo launchctl kickstart -k system/com.thverify.server'`

## Automation

On popmacmini, `com.thverify.daily-sync` runs `scripts/daily_sync.sh` daily
at 03:30: delta sync all sources → rebuild exports → rebuild search index.
Logs: `~/th-verify/data/logs/daily_sync_YYYYMMDD.log` (14 kept). It sources
`.env` itself. Duplicates are impossible: `UNIQUE(source, source_id)` +
upsert-in-place; delta "records seen" in logs ≠ new rows (usually ~250 seen,
~5–15 new/day).

## LLM labeling (aipower)

`scripts/llm_assist.py extract-verdicts` labeled 465 cofact/thaipbs records
(origin `llm`) on 2026-07-11 by extracting the verdict already stated in the
article, with a verbatim-quote hallucination guard (62 rejected, 60 unclear).
`llm` tier sits between `heuristic` and `source`/`human` in trust; briefs
exclude `heuristic` but include `llm`. `summarize` generates cited Thai
evidence summaries for VerifyDesk (retrieval-grounded, top-k from the index).

## Dataset exports (current numbers, will drift as labeling proceeds)

~15.2k labeled, deduped, leak-stripped claims (train/val/test
9,578/1,691/3,905 as of 2026-07-11 evening). Labels: false / true /
misleading / altered_media / satire / scam_alert. Time-based splits:
train ≤2024-12-31, val 2025H1, test >2025-06-30. `claim_text` has verdict
prefixes stripped ("ข่าวปลอม อย่าแชร์!" etc.) and inline-leak records are
excluded from classification exports (kept in rag_corpus.jsonl).
**Re-run build_dataset.py + index before any training run** — the DB moves.

## Search service

`POST /check {"text": ...}` → top-k similar past fact-checks with
match_level strong (≥0.91) / possible (≥0.88) / none. Model:
intfloat/multilingual-e5-small (env `TH_VERIFY_EMBED_MODEL` to swap; bge-m3
gives wider score margins at ~10× build cost). Brute-force numpy cosine over
~26.6k docs — no ANN needed at this scale. The index is a snapshot: DB
changes appear in search only after `th-verify index` (nightly, or manual).

## Quality assurance (added 2026-07-11/12)

- **Invariant tests** (`tests/test_invariants.py`, 26 tests; suite total 31):
  human labels survive re-syncs; classifier fenced off human rows and stamps
  `heuristic`; claim cleaning strips verdict affixes; inline-leak detection;
  verdict normalization incl. AFP typos and pass-through of normalized
  labels; read-only instance blocks all labeling surfaces and rate-limits;
  briefs demote heuristic labels. **If a refactor fails one of these, the
  refactor is wrong, not the test.** Run: `.venv/bin/python -m pytest -q`.
- **Frozen retrieval benchmark**: 50 hand-written colloquial-Thai queries →
  expected record IDs. Baseline (e5-small, 2026-07-12): **hit@1 76%,
  hit@5 94%, MRR 0.840**; the 3 misses retrieved sibling records of the
  same hoax family. Run `scripts/eval_retrieval.py` after any change to
  embeddings/index/cleaning. Never edit the benchmark to flatter a change —
  add a v2 file and report both.
- **Label audit (2026-07-12)**: 20-sample inspection of `llm` labels found
  0 errors; keyword-flagged "suspicious true" labels were all genuinely
  true scam-warning news; exports contain no empty/malformed claims.
  **Superseded — do not rely on this result.** See below.
- **Ground-truth label audit (2026-07-31)**: the Thai PBS ClaimReview block
  gives a real answer key, so for the first time thaipbs labels could be scored
  rather than eyeballed. All 525 thaipbs rows in the dev copy were checked:

  | tier | checked | wrong | error rate |
  |---|---:|---:|---:|
  | `source` | 136 | 33 | **24.3%** (the collector bug, now fixed) |
  | `llm` | 330 | 70 | **21.2%** |
  | unlabelled | 59 | 0 | — |

  The 2026-07-12 audit reported 0 errors in 20 samples. If the true rate were
  21%, drawing 20 clean samples has probability ~0.9% — so that audit was
  almost certainly judging whether a label looked *plausible* against the
  article, not comparing it to the publisher's stated verdict. Plausibility
  checks confirm; answer keys don't. Score against ground truth where one
  exists.

  **The `llm` tier's errors have a clear shape, and it is not randomness:** of
  the 70, **52 are adjacent-category** (41 `false`→`misleading`, 11
  `false`→`altered_media`), 9 are genuine polarity reversals
  (6 `false`→`true`, 3 `misleading`→`true`), and 9 are cases where the
  publisher declines to rate at all. The model systematically **collapses
  nuanced verdicts into "fake"** — it calls a distorted-context story or a
  doctored image "ข่าวปลอม". That is the single most useful thing to fix in
  the extraction prompt.

  **Unresolved and important:** cofact also carries `llm` labels and has no
  ClaimReview equivalent, so its share of the 465 `llm` records cannot be
  scored this way. Treat cofact `llm` labels as carrying a similar error rate
  until someone demonstrates otherwise. Do not promote the `llm` tier toward
  gold on the strength of the old 20-sample audit.

## Public read-only layer (เช็กก่อนเชื่อ soft launch)

Target URL: **https://check-before.org** → Cloudflare named tunnel →
mini port 8943 (read-only instance). Private instance and DB are never
exposed. Before any wider launch: licensing/ToS conversations per source
(Cofact first — pitch pack in `data/pitch/`), a PDPA note on the page
(queries are not logged — keep it true), and consider rebuilding the index
with bge-m3 for wider score margins.

## Thai PBS verdict contamination (found and fixed 2026-07-31)

**The bug.** `collectors/thaipbs.py` derived each record's verdict *and* its
fallback publication date from a container walked up from the listing link. The
walk stopped only on a 140-character floor, which routinely overshot into a
wrapper holding several article cards. Every record cut from such a wrapper
inherited the **first card's** verdict and date. 198 of 525 thaipbs rows (38%)
shared a blob with at least one other row.

Because thaipbs verdicts carry `verdict_origin='source'`, the bad labels sat in
the **gold tier** and flowed straight into `classification_train.jsonl`. Sampled
proof: record 12432 ("คลิปอ้าง 'นักรบฮิซบอลลาห์'… แท้จริงเป็นคลิปตาลีบัน") was
stored as `ข่าวจริง`/true when the publisher rates it `ข่าวปลอม`/false. Six
records also carried a `2026-09-30` publication date — two months in the future
— scraped out of *claim prose* ("เริ่ม 1 มิ.ย. – 30 ก.ย. 69"), which then
misplaced them across the time-based train/val/test split.

**The fix.** Thai PBS embeds a schema.org **ClaimReview** block per article
carrying `reviewRating.alternateName` (the verdict) and `datePublished`. The
collector now reads that first and only falls back to the listing block, and the
container walk stops at a card boundary (`_spans_multiple_articles`). Guarded by
four tests in `tests/test_invariants.py` (section 7).

**Trap worth remembering:** do *not* map on `ratingValue`. Thai PBS ships
`ratingValue: 5` (the "best" end of a 1–5 scale) together with
`alternateName: ภาพปลอม`. The numeric rating does not track the label; only
`alternateName` is meaningful.

**Two alternateName values are not verdicts:** `ไม่สแตมป์ข่าว` (an explicit
refusal to stamp one) and `ตรวจสอบแล้ว` (only asserts a check happened). Both are
now mapped to `unknown` explicitly in `build_dataset.py` so the choice is
visible. Do not invent a polarity for them.

**Repair tool:** `scripts/repair_thaipbs_verdicts.py` re-derives verdict, date
and provenance from ClaimReview. Dry run by default; `--apply` writes; never
touches `verdict_origin='human'`; writes a JSON report of every change to
`data/repair/`. When it replaces an `llm`-origin verdict with the publisher's
own, it promotes `verdict_origin` to `source` so provenance stays honest. It
skips changes that only alter representation (stored `false` vs published
`ข่าวปลอม` mean the same thing) unless `--rewrite-representation` is passed.

**Scale of the damage, measured over all 525 thaipbs rows in the dev copy on
2026-07-31** (production had 539 rows and the same 38% contamination rate):

| outcome | rows |
|---|---:|
| already correct | 254 |
| **genuinely wrong label** | **103** (33 gold-tier `source`, 70 `llm`) |
| `unknown` filled in with a real label | 57 |
| wrong publication date only | 111 |

Of the 103 wrong labels, 13 were outright polarity reversals (7 `false`→`true`,
6 `true`→`false`); the largest single group was 48 `false`→`misleading`. Wrong
dates matter too — the train/val/test split is time-based, so a misdated record
lands in the wrong split.

**Applied to production 2026-07-31.** A verified point-in-time backup was taken
first at `~/th-verify/data/backups/th_verify_pre_thaipbs_repair_*.db`
(`integrity_check ok`, 28,442 records). Note that reading a `.backup` copy needs
plain `sqlite3`, not `sqlite3 -readonly` — the file is in WAL mode and read-only
mode cannot create the `-shm` sidecar, which fails with a misleading
"unable to open database file (14)".

After any future repair run, re-run `scripts/build_dataset.py` + `th-verify
index` so exports and search pick the corrections up.

## Gotchas / history to know

- **Label leakage**: source titles literally contain the verdict
  ("ข่าวปลอม อย่าแชร์! …"). Never train on raw titles; use `claim_text`
  from the exports. Zero-leak state verified 2026-07-11.
- **cofact provenance is murky**: its ~740 Thai verdicts appeared after both
  a re-backfill and the heuristic classifier ran; conservatively marked
  `heuristic`. A collector-side verdict extractor could upgrade them to
  `source`.
- **`th-verify classify` writes guesses into the DB.** It's fenced now, but
  prefer not running it at all; human labeling supersedes it.
- **sure_share is YouTube metadata**, not articles — descriptions rarely
  contain the verdict (it's spoken in the video). Hence human labeling.
  Whisper transcription on a 3090 was planned then dropped in favor of
  human labeling; revisit if labeling stalls (plan: faster-whisper
  large-v3 → local LLM verdict extraction with verbatim-quote audit).
- **631 duplicate-claim groups** exist across the archive (hoaxes recirculate
  for years) — build_dataset dedups them keeping the earliest, which also
  prevents train/test leakage across the time split.
- afnc verdict field sometimes holds category values; VERDICT_MAP in
  build_dataset.py handles all known raw strings (incl. AFP typos "Flase",
  "Party False"). Unmapped values fall to `unknown` — check
  verdict_mapping.csv after big syncs for new raw values.
- **The export script lives at `scripts/build_dataset.py`.** An untracked
  fossil copy sat at both repo roots (July 11, missing the Thai PBS taxonomy,
  the `ตรวจสอบแล้ว` strip, the conclusion-clause rules and `is_factcheck`), so
  `python build_dataset.py` from the root silently ran month-old logic and
  overwrote good exports. Both copies were deleted 2026-08-16; `daily_sync.sh`
  always called the correct path. If one reappears, delete it rather than
  edit it.
- **Fidelity is not correctness.** The gold tier is verified to copy publisher
  verdicts faithfully (100% against AFNC `status_label` and AFP
  `textualRating`) — that says nothing about whether the publisher was right.
  AFNC stamped an AI-generated photo ข่าวปลอม on 2026-08-03; Thai PBS checked
  the same photo the next day and found it genuine. Both sit in the archive and
  the AFNC one is in `classification_test.jsonl`. This is what the conflicts
  mode exists to surface.

## Product state (vs the TH Verify OS / ClaimRadar business plan)

Maintenance mode by owner's decision (2026-07-12): keep labeling, keep the
crons running, no MVP launch yet. SKU readiness: Monthly Brief ~90% (tool
done, needs analyst ✍️ sections + a pilot customer); VerifyDesk ~70%
(analyst tooling done via /check + llm_assist summarize; missing intake
form + claims log); public search tech-done but gated on licensing + DNS;
ClaimRadar Lite/Monitor and paid API deliberately not started. New SKU
2026-07-14: **Issue Focus Report** (`scripts/build_issue_report.py`) —
per-topic 2-page deep-dive; tooling done, needs analyst ✍️ slots per topic
config; first topic `migrant`. The risk
triage layer is specified in docs/risk-triage-design.md but unbuilt.

**2026-08-14: the Issue Focus SKU now has two editions from one topic config.**
The white paper (`build_issue_report.py`) and the news feature
(`build_issue_feature.py`) — same data, same label policy, different reader. Two
stories are written (`callcenter_scam`, `political_state`), each publishable as
a web article and a PDF. The feature is the more sellable artefact of the two:
it is the one a newsroom or a funder reads end to end.

What is still missing for this SKU to be sold is not tooling. It is (a) an
editorial decision per topic about scope — see "Open decisions" — and (b) the
narrative-shift result being folded into the story, which is what makes the
report say something no one could get by looking at the archive themselves.

## Narrative-shift analysis (added 2026-08-14, `scripts/narrative_shift.py`)

**Why it exists.** The Issue Focus Report answers "how much". The question worth
answering is *what the claims were about, and when that changed* — and until now
a human answered it by eye. The migrant report's "4 ยุค" line
(`insight_html`: โรคระบาด → แย่งงาน → ชาตินิยม) was written by an analyst reading
the per-year category matrix. This derives those eras from the data.

**Why the old way was limited**, and this is the part worth keeping in mind:

1. It can only see narratives someone already named in the topic config. A new
   narrative has no keyword yet, so it is invisible by construction.
2. Nothing tested whether a share change was real or sampling noise.
3. The era boundaries were where the analyst drew the line, not where the data
   turns.
4. The topic filter matched `explanation` text, so the counts included records
   that were not about the topic at all (see `match_fields` above).

**Method.**

    topic records → embed claim text (e5-small, the model already behind /check)
      → k-means on the normalized vectors  (clusters = candidate narratives)
      → per cluster: year histogram, share of the early half vs the late half
      → permutation test: shuffle the dates 2,000× — is the gap beyond chance?
      → Jensen-Shannon divergence between adjacent years → where the mix breaks
      → a human reads the medoid + exemplars and writes the name

Embeddings rather than word frequencies because **Thai has no word spaces** and
no tokenizer is installed (`pythainlp` is absent), and because keyword methods
cannot find a narrative that no config has named. The `passage:` prefix matches
what the search index uses, so the vectors live in the same space.

**It deliberately does not name clusters.** It prints the medoid — the real claim
closest to the cluster centre — plus exemplars, and a human names it. A
machine-invented cluster label is exactly the confidently-wrong artefact this
project fences everywhere else, and here it would propagate into a headline.

**What it found on `migrant`** (316 records, the current all-fields config, k=5):

| narrative (named by hand from exemplars) | early → late share | p | peak |
|---|---:|---:|---:|
| COVID vaccine access for migrants | 41.3% → 2.8% | <0.001 | 2564 |
| work permits / reserved occupations | 28.6% → 10.7% | <0.001 | 2567 |
| citizenship, ID cards, entitlements | 4.8% → 28.8% | <0.001 | 2569 |
| **Cambodia: deportation, re-entry, brokers** | **0.0% → 19.0%** | **<0.001** | **2569** |

It recovered the analyst's eras without being told them, and found one the four
eras missed: the Cambodia cluster has **zero records before 2566** and is now a
fifth of the topic. The turning point is located rather than guessed — the
largest year-to-year move in the whole mix is **2567→2568, JSD 0.186**, exactly
when both new narratives took off.

**Three traps, all hit during the build:**

- **Digest posts.** The first run produced a confident-looking "narrative" made
  entirely of AFNC weekly round-ups (`ข่าวเด่นประจำสัปดาห์`) — not claims, but
  records that cluster on their own boilerplate. `DIGEST_PATTERNS` drops them
  (21 in migrant) and the count is reported.
- **Linkage collapses.** Average-linkage agglomerative on normalized embeddings
  chained 312 of 337 migrant records into one cluster. k-means partitions where
  linkage chains. Do not "fix" this back.
- **Raw coherence is meaningless.** e5 vectors sit in a narrow cone, so every
  cluster scores ~0.93 against its own centroid and looks excellent. The tool
  reports coherence *in excess of the topic baseline*, and flags the loosest
  cluster relative to the others — an absolute threshold flags all or none.

**Known weakness:** silhouette scores are ~0.08 for short-text embeddings, so k
is a weak choice. Re-run with several `--k` values before treating any single
partition as the answer; the tool prints this warning itself.

**Does this need the GPU node?** No. Embedding 240 claims with e5-small takes
about 4 seconds on the MacBook; the whole 28.5k archive would be minutes. The
GPU would buy two specific upgrades, both of which should be *measured* rather
than assumed: (a) **bge-m3 instead of e5-small** — wider score margins should
mean cleaner cluster boundaries, and the silhouette figures above are the
baseline to beat; (b) **whole-archive scale**, finding narratives across topics
rather than inside one.

## Open decisions (2026-08-14) — nothing below is committed

**1. Retune the `migrant` topic config?** It has the same `explanation`-matching
problem the political config had: its largest cluster (114 records) was mostly
AI-viral-clip checks that merely mention ต่างด้าว in the explanation. Depending
on the filter, migrant is:

| config | records | note |
|---|---:|---|
| current (all fields) | 337 | what the published white paper reports |
| title+claim only | 121 | precise but thin for a 7-year analysis |
| title+claim + wider vocabulary + ชายแดน | 372 | **inflated — see below** |
| title+claim + wider vocabulary, no ชายแดน | 240 | the proposed set |

A draft of the last one is parked at
`scripts/issue_topics/migrant.proposed-v2.json.draft` (rename to `.json` to
adopt). **Adopting it changes the published white paper's numbers** (337 → 240),
which is why it was not applied unilaterally.

**2. Where does the Thai–Cambodia border conflict belong?** The 2568 conflict
produced a large wave of misinformation. Letting `ชายแดน` into the migrant
filter takes the topic to 372 records and balloons 2568–69 — but most of that
content is military and diplomatic, not migration. It was **excluded**, on the
judgment that a migrant report should not become a war report by construction;
the Cambodia *labour* narrative (deportation, paying brokers to re-enter, false
claims about Thai benefits for Cambodian workers) stays in. This is an editorial
line, not a statistical result, and the owner may want it drawn differently. A
separate `border_conflict` topic is the obvious alternative.

**3. `political_state` config was retuned and its original overwritten.** The
draft config (untracked, never committed) matched 4,131 records of which a random
20-sample was mostly weather bulletins, cataract surgery and farm subsidies —
because AFNC explanations name the agency that verified the story, so
`นายกรัฐมนตรี` matched 908 records over three fields and 19 over title+claim.
The retuned config matches **518 with ~18/20 precision**, keeping 247 of the
original 254 `false` records. **The original is preserved at
`scripts/issue_topics/political_state.v1.json.bak`** — delete it once you are
happy with the replacement.

**4. Nothing from this session is committed.** Uncommitted work:

    new:      scripts/build_issue_feature.py, scripts/narrative_shift.py,
              scripts/_pdf.py,
              scripts/issue_topics/callcenter_scam.story.json,
              scripts/issue_topics/political_state.json (+ .story.json, .v1.json.bak),
              scripts/issue_topics/migrant.proposed-v2.json.draft
    modified: assets/brand/fnl-design-system.css (section 09 + feat-case label),
              scripts/_charts.py (columns()),
              scripts/build_issue_report.py (match_fields),
              scripts/build_weekly_fakenews_report.py (uses _pdf),
              src/th_verify/static/*.html (stylesheet re-inlined),
              docs/brand-system.md, HANDOFF.md

    Test state: 38 passed. build_issue_report, build_issue_feature and
    build_weekly_fakenews_report all rebuild cleanly.

**5. Unfinished, and the reason it stopped:** the owner asked for the
methodology to be explained before more was built. Still to do — (a) a
narrative-arc figure in the feature generator: small multiples, one panel per
narrative, one hue, shared scale (deliberately *not* a stacked chart, because
the brand has four colours and all of them are status-reserved, so a categorical
palette would have to be invented); (b) the `migrant` story file written around
the 2567→2568 turn, once decisions 1 and 2 are settled.

## Sensible next steps

1. Continue human labeling (biggest data-quality win per hour).
2. When publishing เช็กก่อนเชื่อ: licensing talks first (Cofact → ThaiPBS →
   AFNC), PDPA/no-logging note, bge-m3 index rebuild, then soft-launch to
   the fact-check community before the general public.
3. VerifyDesk intake (form + `inbound_claims`-style log) is the only code
   gap blocking the "Brief + VerifyDesk Lite" first paid offer.
4. When enough labels: fine-tune WangchanBERTa baseline on the exports,
   evaluate on the time-split test set only; collapse to 3 classes
   (false/true/misleading), fold altered_media into false, drop satire (n=4).
5. Gold eval set: human-verify a stratified ~500–800 sample across all
   sources/years (frozen benchmark for classification, complementing the
   retrieval benchmark that already exists).
6. Settle the two topic-config decisions above, then finish the narrative-arc
   figure and the `migrant` story — the narrative-shift finding (a narrative
   that did not exist before 2566 is now a fifth of the topic) is the strongest
   editorial result the archive has produced so far, and it is the argument for
   the Issue Focus SKU being worth paying for.
7. Audit the remaining topic configs for the `explanation`-matching problem.
   Only `political_state` has been retuned; `migrant` has a draft; nobody has
   looked at `callcenter_scam` (843 records, all fields) with this in mind.
