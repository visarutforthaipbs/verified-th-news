# 📑 Phase 0 Data Audit: Longitudinal Fact-Check Archive (2015–2026)
**Document Version:** 1.0 (In Compliance with PRD Section 6 & Phase 0)  
**Date of Audit:** August 14, 2026  
**Target Dataset:** `data/th_verify.db` (28,204 canonical records)  
**Primary Analytical Principle:** Claim-Level Analysis, Source Bias Control & Provenance Integrity  

---

## 1. Executive Summary & Audit Assessment

This Phase 0 audit establishes baseline data quality, temporal coverage, source compositional shifts, boilerplate leakage risks, and duplicate family structures across the 11-year archive (2015–2026).

```
Total Fact-Check Claims:       28,204
Semantic Claim Clusters:       24,942
Duplicate Claim Families:       1,117 recurring claim instances
Overall Data Completeness:     99.99% valid publication dates, 100% titles/claims
Temporal Span:                 May 2015 – August 2026 (11.2 Years)
```

---

## 2. Source-by-Year Composition Matrix (PRD §6.4 Source Bias Control)

> [!IMPORTANT]
> **Source-Composition Confound Warning (PRD Rule 4):**
> Temporal shifts in topic counts must never be interpreted as genuine social shifts without controlling for archive source expansion.
> - **2015–2018:** Dominated almost exclusively by Sure & Share YouTube metadata.
> - **Late 2019:** Launch of Anti-Fake News Center Thailand (AFNC) introduced ~16.7k official state fact-checks.
> - **2020:** AFP Thailand and Cofact added to active collectors.
> - **2024:** Thai PBS Verify added.

| Year | AFNC | Sure & Share | Cofact | AFP | Thai PBS | Total Annual Claims | AFNC Share (%) |
| :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **2015** | 0 | 72 | 0 | 0 | 0 | **72** | 0.0% |
| **2016** | 0 | 251 | 0 | 0 | 0 | **251** | 0.0% |
| **2017** | 3 | 307 | 0 | 0 | 0 | **310** | 1.0% |
| **2018** | 5 | 355 | 0 | 0 | 0 | **360** | 1.4% |
| **2019** | 79 | 449 | 0 | 0 | 0 | **528** | 15.0% |
| **2020** | 1,074 | 599 | 28 | 110 | 0 | **1,811** | 59.3% |
| **2021** | 1,410 | 466 | 12 | 94 | 0 | **1,982** | 71.1% |
| **2022** | 2,641 | 795 | 40 | 87 | 0 | **3,563** | 74.1% |
| **2023** | 2,963 | 1,996 | 152 | 86 | 0 | **5,197** | 57.0% |
| **2024** | 3,198 | 1,875 | 155 | 120 | 73 | **5,421** | 59.0% |
| **2025** | 3,451 | 1,551 | 326 | 141 | 238 | **5,707** | 60.5% |
| **2026** | 2,055 | 630 | 287 | 101 | 231 | **3,304** | 62.2% |

---

## 3. Data Completeness & Missing Value Diagnostics

| Field Name | Missing / Blank Count | Completeness (%) | PRD Status & Handling Rule |
| :--- | ---: | ---: | :--- |
| `claim_id` / `id` | **0** | 100.00% | ✅ **PASS** — Primary entity key |
| `title` | **0** | 100.00% | ✅ **PASS** — Headline metadata |
| `claim` | **0** | 100.00% | ✅ **PASS** — Principal analytical unit (PRD §6.1) |
| `source_url` | **0** | 100.00% | ✅ **PASS** — Full audit trail preserved (PRD §27) |
| `raw_json` | **0** | 100.00% | ✅ **PASS** — Original crawler payload retained |
| `published_at` | **2** | 99.99% | ✅ **PASS** — Missing dates excluded from temporal curves |
| `explanation` | **4,348** | 84.58% | ⚠️ Handled — Video metadata (Sure & Share) lacks full article text |
| `category` | **11,504** | 59.21% | ⚠️ Handled — Unsupervised topic discovery will replace source categories |
| `verdict` (known) | **20,998** | 74.45% | ℹ️ 7,206 records are in pending human/LLM verification queues |

---

## 4. Duplicate Family & Recirculation Diagnostics (PRD §6.3)

Near-duplicates and recirculating hoaxes distort topic volume if not family-clustered.
- **Exact Title Duplications:** **1,115** records
- **Exact Claim Duplications:** **1,117** records
- **Semantic Claim Clusters (`claim_clusters`):** **24,942** clusters across **28,137** member records
- **PRD Compliance Rule:** Maintain both `raw_count` and `duplicate_adjusted_volume` ($unique\_claims$) in all temporal calculations.

---

## 5. Boilerplate Removal & Verdict Leakage Audit (PRD §6.2)

> [!CAUTION]
> **Verdict Leakage Protection:**
> Thai fact-check headlines frequently embed the verdict inside the title (e.g. *"ข่าวปลอม อย่าแชร์! ... "* or *"จริงหรือ ? ... "*).
> If fed uncleaned into embeddings, the model clusters by verdict prefix rather than claim topic!

### Frequency of Verdict Boilerplate in Raw Archive:
- **`'ข่าวปลอม'`:** Found in 7,077 titles (24.8%) and 7,074 claims (24.8%)
- **`'อย่าแชร์'`:** Found in 6,849 titles (24.0%) and 6,849 claims (24.0%)
- **`'เช็กก่อนเชื่อ'`:** Found in 3 titles (0.0%) and 3 claims (0.0%)
- **`'ชัวร์ก่อนแชร์'`:** Found in 6,481 titles (22.7%) and 6,481 claims (22.7%)
- **`'จริงหรือ'`:** Found in 7,165 titles (25.1%) and 7,165 claims (25.1%)
- **`'ไม่จริง'`:** Found in 19 titles (0.1%) and 18 claims (0.1%)
- **`'ข้อมูลเท็จ'`:** Found in 50 titles (0.2%) and 45 claims (0.2%)
- **`'เตือนภัย'`:** Found in 241 titles (0.8%) and 241 claims (0.8%)
- **`'ข่าวจริง'`:** Found in 219 titles (0.8%) and 218 claims (0.8%)
- **`'ข่าวบิดเบือน'`:** Found in 731 titles (2.6%) and 731 claims (2.6%)

**Pipeline Remediation (PRD §6.2):**
The cleaning pipeline `clean_claim_text()` in `build_dataset.py` strips all leading verdict affixes (*"ข่าวปลอม อย่าแชร์"*, *"ศูนย์ต่อต้านข่าวปลอมตรวจสอบพบว่า"*, *"จริงหรือ ?"*) before embedding generation.

---

## 6. Text Length & Distribution Diagnostics

- **Title Length:** Average **70.2** chars (Min: 8, Max: 274)
- **Claim Length:** Average **69.4** chars
- **Analytical Unit Recommendation:** Use `normalized_claim` (cleaned of boilerplate) as the primary embedding input, optionally enriched with minimal context.

---

## 7. Publisher Profiles & Label Trust Tiers

| Source Code | Publisher Name | Total Records | Gold Source | Gold Human | LLM (Guarded) | Heuristic | Pending Queue |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `afnc` | **ศูนย์ต่อต้านข่าวปลอม (AFNC)** | 16,879 | 16,659 | 3 | 0 | 0 | 217 |
| `sure_share` | **ชัวร์ก่อนแชร์ (MCOT YouTube)** | 9,346 | 0 | 125 | 1,332 | 2,207 | 5,681 |
| `cofact` | **Cofact Thailand** | 1,000 | 0 | 47 | 134 | 730 | 81 |
| `afp` | **AFP Fact Check Thailand** | 739 | 694 | 0 | 0 | 0 | 45 |
| `thaipbs` | **Thai PBS Verify** | 542 | 265 | 2 | 257 | 0 | 18 |

---

## 8. Phase 0 Audit Sign-Off & Phase Transition Gate

### PRD Phase 0 Criteria Checklist:
- [x] **Schema Verified:** Minimum required fields (`claim_id`, `claim_text`, `date_published`, `source`, `source_url`) fully populated.
- [x] **Source Composition Documented:** 11-year source-by-year distribution table calculated for confounding controls.
- [x] **Boilerplate Affixes Identified:** Clean stripping rules validated to prevent embedding verdict leakage.
- [x] **Duplicate Tracking Established:** `duplicate_family_id` and cluster mapping verified.
- [x] **Phase 0 Deliverable:** `DATA_AUDIT.md` created and persisted.

**Gate Status:** ✅ **PHASE 0 DATA AUDIT COMPLETE — CLEARED FOR PHASE 1 & 2 PIPELINE IMPLEMENTATION.**
