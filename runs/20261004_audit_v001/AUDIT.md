# End-to-end audit — data → method → insights → drafts

Date: 2026-10-04 · Scope: both articles · Auditor: assistant (AI), not a human review
Reproduce: `.venv/bin/python scripts/audit_end_to_end.py` → `audit_metrics.json`. Working logs: `01_`–`07_*.txt` in this folder.

## Verdict by layer

| Layer | Verdict | In one line |
|---|---|---|
| Data pipeline | **Sound** | The 14,429-record corpus rebuilds exactly from the database; cited records match the live publisher pages |
| Labels | **Sound with an undisclosed caveat** | 21.9% of verdicts were assigned by the project's own reviewers, not by the publisher; the drafts say otherwise |
| Computation | **Sound** | Clustering reproduces exactly from the embeddings (ARI 1.000); every table and every number in both drafts recomputes |
| Method as applied | **Partly sound** | The decline of virus claims is robust. The rise of "state-service" claims is one publisher repeating a few templates |
| Insights doc | **Out of date** | `INSIGHTS_TH.md` still recommends a sentence the 4 Oct checks disproved |
| Story 1 draft | **Numbers right, frame overstated** | "11 years" and "biggest shift" claims do not survive the publisher switch in 2020 |
| Story 2 draft | **Numbers right, not publishable** | The draft already says so; new problem: the review queue missed clearly relevant records |

Nothing was fabricated anywhere in the chain. The problems are in what the numbers are said to mean.

## What is solid

1. **Corpus.** Rebuilding membership from `data/th_verify.db` with the documented rules gives the same 14,429 ids (the only 62 extra are the documented short-text exclusions). No verdict has changed since the snapshot.
2. **Clustering.** Re-running UMAP (seed 42) and HDBSCAN from `unique_embeddings.npy` returns the published labels exactly: 64 clusters, ARI 1.000.
3. **Tables.** `topic_timeline.csv` (4,680 rows) and `adjacent_year_shifts.csv` recompute with zero differences.
4. **Drafts.** All figures in both drafts match the data, including the 4 Oct additions (investment family 11.1 / 9.3 / 11.4 / 6.7%; 30 of 38 vaccine records in the "LIVE Retrovert" series). All 36 records cited by ID have the publisher, date and verdict the drafts state.
5. **Live sources.** 7 of 8 spot-checked pages are online with the same headline and publication date as the archive (AFNC ×6, Thai PBS ×1). AFP blocks scripted access, so ID 16862 was not checked.
6. **Virus decline.** Topics 4 and 7 fall in each publisher separately (AFNC 7.06→0.16% and 8.37→0.35%; Sure&Share 9.19→0.48%; AFP 12.95→0%), survive near-duplicate removal, and keep their membership under other random seeds (Jaccard 0.76–0.91).

## Findings that change what can be written

### F1 — "11 years" is two different archives (Story 1, high)
- 2015–2019 holds 1,187 records (8.2%), and 93.4% of them are one TV programme (Sure&Share). From 2020, AFNC is 70–85% of every year.
- Every trend in the draft compares 2020–21 with 2024–25. Nothing in it describes change across 2015–2019.
- The draft's "largest shift, 2562→2563" (JSD 0.490) coincides with AFNC going from 18% to 74% of records. Within Sure&Share alone the same step is 0.323.
- "The big health group shrank about 35 points" is mostly that switch: within Sure&Share it fell 88.7% → 75.6% (13 points).
- **Fix:** keep "11 years" only as the span of the archive. Make trend claims about 2020–2025. Say in section 2 that before 2020 the archive is one programme. Rewrite the first paragraph of section 3.

### F2 — the rising topics are one publisher repeating a few templates (Story 1, high)
- Already disclosed in the draft: 885 of 893 records in the three rising topics are AFNC.
- New: the driving-licence topic is essentially one claim with a different page name each time. Of its 321 distinct texts, 282 fall in one near-duplicate group at cosine ≥ 0.95 (121 at ≥ 0.97).
- Counting each near-duplicate claim once per publisher per year, the licence share for 2024–25 is 0.50% (≥ 0.95) or 2.86% (≥ 0.97), against 4.22% raw. The order of the "risers" changes with the rule; under both, the Cambodia border topic is the largest, not the licence topic.
- The "source-balanced" figures in section 5 (+1.80 / +1.42 / +1.10 points) equal AFNC's own change divided by three, exactly. They are not independent support and should not be presented as a test the finding passed.
- The victim-refund topic's boundary moves with the random seed (Jaccard 0.46 and 0.72; late share 2.65–6.08% against 3.33% published). Licence is stable (0.99).
- **What survives:** from 2022 AFNC published hundreds of debunks of pages impersonating the Land Transport Department, AMLO and the Stock Exchange; before 2022 it published almost none. That is a statement about AFNC's output and about cloned pages, and it is a good story. It is not a measured shift in Thai misinformation.
- **Fix:** present the table as counts of debunks of cloned pages; drop the percentages as headline evidence or give the range; remove the source-balanced sentence; soften the headline.

### F3 — one in five verdicts was not issued by the publisher (both stories, medium)
- Both drafts say the outlets "ตัดสินว่า" false/misleading. True for AFNC, AFP and Thai PBS (11,267 records). Not true for Sure&Share (2,861) and Cofact (284): those 3,162 verdicts (21.9%) were assigned by the project's two reviewers.
- 1,207 of them were machine-proposed from a transcript and confirmed by a person. 877 have no recorded evidence at all (no description, no transcript); about 790 of those are question-form titles ("…จริงหรือ?"). They were decided in a median of 13.6 seconds, 69% in under 20 seconds, while the clips run 37–59 seconds.
- Accuracy proxy: 237 cases where the same claim was labelled once from the title only and once with evidence. Title-only "false/misleading" labels were contradicted 2 times in 166 (1.2%), so the corpus is unlikely to contain many true items. Title-only "true" labels were contradicted 26 times in 71 (37%), so some false or misleading Sure&Share checks are probably missing from the corpus.
- **Fix:** correct the sentence in both drafts and both methodology boxes; state the label source by publisher. Treat Sure&Share counts after 2022 as approximate.

### F4 — Sure&Share after 2022 is mostly re-cut shorts (Story 1, medium)
- Share of Sure&Share corpus records that are `#shorts`: 21% (2022), 77% (2023), 65% (2024), 71% (2025). They carry the re-upload date.
- Section 6 already uses this for the "recurrence" angle. It also means Sure&Share's volume and topic mix in 2023–25 describe a publishing format, not new checking, and those are the same records as F3's title-only labels.
- **Fix:** one sentence in section 2 or 6; do not use Sure&Share 2023–25 as evidence of what was circulating then.

### F5 — Story 2's review queue missed relevant records (Story 2, high for the coding step)
- The 332-row queue was never checked for what it left out. A keyword probe over the 14,429 found 37 unscreened candidates; at least seven are clearly about migrants or refugees in Thailand:
  - 17106 (AFP, 22 Sep 2020) people fleeing the outbreak from Myanmar into Thailand
  - 6389 (AFNC, 5 Sep 2024) a Thai school has pupils sing the Myanmar anthem
  - 27145 (Thai PBS, 24 Oct 2024) Thai taxes pay for benefits Myanmar people receive
  - 5180 (AFNC, 14 Jan 2025) Thai blood reserves given to Myanmar people
  - 4571 (AFNC, 21 Mar 2025) more Myanmar than Thai residents in Samut Sakhon
  - 2802 (AFNC, 22 Sep 2025) officials force foreigners to work for call-centre gangs
  - 1117 (AFNC, 18 Mar 2026) Thailand to receive Jewish refugees
- These are exactly the entitlement, demography, disease and schooling items the story is about, and most use "พม่า". Two draft statements are affected: "no disease cluster" (17106 was never in the pool) and "the school topic starts in 2568" (6389 is from 2567).
- The coder sheets (332 rows, none filled yet) inherit the gap.
- **Fix before coding starts:** extend the queue with the unscreened candidates (full list in `audit_metrics.json` → `story2.never_screened_list`) and rebuild the coder sheets in a new version.

### F6 — the insights file is stale (both, low–medium)
`deliverables/journalist_handoff_20260914/INSIGHTS_TH.md` is what the package tells journalists to read first. It still lists "ข่าวลงทุนเคยพุ่งขึ้นแรง ก่อนลดลง" as a usable sentence (disproved on 4 Oct: the nine-topic investment family stays 9–11%), presents 2562→2563 as the biggest turning point without the publisher switch, and adds licence + refund to "7.55% of the archive". Update it or put a dated warning at the top.

### Minor
- 48 AFNC records are dated before the centre opened (Nov 2019); they are backfilled agency warnings. Harmless, but "AFNC since 2017" should not be written.
- 13.4% of claim texts (1,937) were extracted by an LLM, mostly Sure&Share. Already flagged in the drafts for quotation; it also affects which cluster those records fall in.
- The client brief's "26,000 ข่าวปลอม" is unsupported (29,001 raw; 14,429 in scope).

## What to do, in order
1. Extend the Story 2 queue and reissue the coder sheets (F5) — before anyone starts coding.
2. Edit Story 1: sections 2, 3 (first paragraph), 4 (table framing), 5 (source-balanced sentence), headline (F1, F2, F4).
3. Fix the label-source sentence and methodology boxes in both drafts (F3).
4. Update or flag `INSIGHTS_TH.md` (F6).
5. Human steps already listed in `HANDOFF.md` are unchanged and still required.

## Limits of this audit
It is an assistant's audit, not a human one. Label accuracy was estimated from internal agreement, not from watching clips. The near-duplicate thresholds are a sensitivity range, not a validated definition of "same claim". The recall probe used a handful of keywords, so seven missed records is a floor. The local database is the 2 Sep snapshot, not production.

---

## สรุปสำหรับผู้เขียน (ภาษาไทย)

ตัวเลขทุกตัวในร่างทั้งสองฉบับถูกต้องและคำนวณซ้ำได้ ปัญหาอยู่ที่การตีความ

1. **“11 ปี” เป็นสองคลัง** ก่อนปี 2563 เกือบทั้งหมดคือชัวร์ก่อนแชร์ (93%) หลังจากนั้นคือ AFNC (70–85%) แนวโน้มในร่างเทียบได้เฉพาะ 2563–2568 และ “ปีที่เปลี่ยนแรงที่สุด 2562→2563” ส่วนใหญ่คือการเข้ามาของ AFNC
2. **กลุ่มที่เพิ่มขึ้นคือข้ออ้างแม่แบบเดียวที่ AFNC ตรวจซ้ำทีละเพจ** กลุ่มใบขับขี่ 321 ข้อความ มี 282 ข้อความที่เป็นข้ออ้างเดียวกันต่างกันแค่ชื่อเพจ เมื่อนับข้ออ้างซ้ำครั้งเดียว สัดส่วนเหลือ 0.5–2.9% จาก 4.22% เขียนได้ว่า “AFNC ตรวจเพจแอบอ้างหลายร้อยเพจ” เขียนไม่ได้ว่า “ข่าวลวงไทยเปลี่ยนไปสู่การแอบอ้างบริการรัฐ”
3. **ตัวเลข “ถ่วงน้ำหนักสำนัก” ในส่วน 5 ไม่ใช่หลักฐานอิสระ** มันเท่ากับค่าของ AFNC หารสาม ให้ตัดออก
4. **ป้ายผล 21.9% ไม่ได้มาจากสำนัก** ชัวร์ก่อนแชร์และ Cofact ถูกติดป้ายโดยผู้ตรวจของโครงการเอง ต้องแก้ประโยค “สำนักตัดสินว่า” และกล่องวิธีวิจัย
5. **เรื่องที่ 2: คิวตรวจตกหล่น** มีอย่างน้อย 7 บันทึกเรื่องคนเมียนมา/ผู้ลี้ภัยที่ไม่เคยถูกคัดเลย ต้องเพิ่มเข้าคิวและออกแบบลงรหัสใหม่ก่อนเริ่มลงรหัส
6. **สิ่งที่ใช้ได้มั่นคง:** ข้ออ้างเรื่องไวรัสลดลงจริงในทุกสำนัก
