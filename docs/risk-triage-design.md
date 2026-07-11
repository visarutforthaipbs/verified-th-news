# Design: Risk Triage Layer (business plan §4.3)

Status: **specification only — not yet built.** This document exists so the
layer can be implemented later (by any model or developer) without
re-deriving the reasoning. Read HANDOFF.md first.

## 1. What the score means (and must never mean)

The risk score answers exactly one question:

> **How urgently should a human reviewer look at this claim?**

It is a *review-priority* score, not a truth probability. This is a hard
product and ethics constraint, not a style preference:

- Never render the score as "โอกาสเป็นข่าวปลอม X%".
- Never auto-publish any consequence of a score without human review.
- The UI copy for a high score is "ควรตรวจสอบโดยเร็ว", never "น่าจะปลอม".

Rationale: the archive over-represents debunked claims (fact-checkers
select for suspicious content), so any "truth probability" trained or
calibrated on it is structurally biased toward "fake". A priority score
sidesteps this: sending a true-but-viral claim to a human early is a
success, not a false positive.

## 2. Score composition

Total score in [0, 100], computed as a weighted sum of independent signal
groups. Keep the groups separately inspectable — the UI must be able to show
*why* something scored high ("คล้ายข่าวลวงเดิม 92% + เข้าข่ายสินเชื่อปลอม").

| group | weight | signals |
|---|---|---|
| S1 similarity to known-false | 40 | max cosine vs archive records with label false/misleading/altered_media (use the /check machinery; ≥0.95 → full weight, linear from 0.85) |
| S2 scam pattern match | 25 | the SCAM_PATTERNS regexes from build_brief.py, plus: loan amounts + LINE/TikTok handles, "อนุมัติไว", QR/link solicitation, government-agency name + registration link |
| S3 topic sensitivity | 15 | category lookup: health-treatment, disaster, election, border/military, benefit-registration score high; entertainment/sports low |
| S4 recirculation | 10 | claim matches (≥0.95) a record whose cluster has ≥3 members across years — known recurring hoax families reactivating |
| S5 audience-harm heuristics | 10 | targets elderly (โครงการรัฐ + เงิน), migrant workers, patients (หยุดยา, เลิกรักษา); impersonates police/bank |

Weights are a starting point; recalibrate only against reviewer feedback
(see §5), never against label distribution.

## 3. What NOT to build

- **No LLM verdict guessing.** LLMs in this layer may only extract features
  (claim type, named entities, solicitation presence) — never output a
  truth judgment on a novel claim.
- **No article-level scoring.** Score claims. A responsible news article
  *quoting* a false claim must not inherit the claim's score. Requires the
  claim-extraction step (plan §10 phase 2) before this layer is exposed to
  whole-article input; until then accept only short claim text.
- **No auto-actions.** Score changes queue order. Nothing else.

## 4. Data model

Add table (do not overload fact_checks — these are inbound claims, not
fact-checks):

```sql
CREATE TABLE inbound_claims (
  id INTEGER PRIMARY KEY,
  text TEXT NOT NULL,
  submitted_via TEXT NOT NULL,          -- api|form|line|manual
  submitted_at TEXT NOT NULL,
  risk_score INTEGER,
  risk_breakdown TEXT,                  -- JSON: per-group contributions
  status TEXT NOT NULL DEFAULT 'new',   -- new|watching|needs_verification|
                                        -- resolved_false|resolved_true|
                                        -- resolved_misleading|ignored|escalated
  resolved_by TEXT,                     -- reviewer id when human decides
  resolution_note TEXT,
  matched_fact_check_id INTEGER         -- strongest archive match, if any
);
```

Reviewer decisions here are the proprietary training data the business
plan describes. Provenance discipline applies exactly as in fact_checks.

## 5. Evaluation before exposure

Do not show scores to any client until:

1. Backtest: score all claims from the last 3 months of the archive; verify
   that ≥80% of records that fact-checkers actually chose to debunk would
   have landed in the top-priority queue tier.
2. Reviewer agreement: two humans independently rank 50 scored claims;
   Kendall tau vs the score ranking ≥ 0.5.
3. False-alarm audit: sample 30 high-scoring claims that were NOT known
   hoaxes; a human confirms ≥ 2/3 were still reasonable to prioritize.

Log every score with its breakdown (risk_breakdown JSON) from day one —
this audit trail is both the debugging tool and the editorial defense.

## 6. Implementation order

1. `inbound_claims` table + POST /submit endpoint (private instance only).
2. S1 + S2 scoring (pure reuse of existing search + regex machinery) — this
   alone is ~70% of the value.
3. Review queue UI: extend the /review room pattern (keyboard-first,
   status buttons mapping to the status enum).
4. S3–S5 signals.
5. Backtest + agreement evaluation (§5).
6. Only then: client-visible risk tiers (สูง/กลาง/ต่ำ — tiers, not numbers).
