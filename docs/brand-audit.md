# Brand compliance audit — Fake News Lab v1.0

Audit and retrofit performed 2026-08-01 against brand guide v1.0 (พ.ค. 2568).
System documentation: [`docs/brand-system.md`](brand-system.md).

Every claim below about rendering was checked by rendering it: HTML screenshots
via headless Chrome, PDFs printed with `--print-to-pdf` and rasterised with
`qlmanage` (Quartz) before being looked at. Thai shaping — vowel and tone-mark
positions, absence of tofu — was inspected in each.

---

## 1. What complied before this work

Almost nothing, which is unsurprising: the brand guide postdates most of these
files.

* Thai font stacks were mostly sensible (`Sarabun`, `Noto Sans Thai` led several
  stacks) and Thai rendered correctly everywhere. That was the one thing worth
  preserving, and it is preserved.
* `build_issue_report.py` and `build_html_report.py` already set
  `print-color-adjust: exact` and avoided splitting table rows across pages —
  the right instincts, aimed at the wrong palette.
* `build_history_report.py` was already dark-mode. Wrong dark (slate `#0f172a`
  with sky-blue and amber accents), but dark.

## 2. What did not comply

| file | what was wrong |
|---|---|
| `scripts/build_weekly_fakenews_report.py` | inline `CSS` constant: white paper, navy `#0f172a` headings, blue `#1d4ed8` links, slate zebra rows. No brand element of any kind. |
| `scripts/build_issue_report.py` | inline `CSS`: cream `#f0efed` page, brick `#8f3429`, brown `#2b1f1d`, olive/green/blue verdict colours; **Google Fonts CDN** (Sarabun + Outfit). |
| `scripts/build_html_report.py` | same as above, duplicated by hand (it is the prototype `build_issue_report.py` replaced). |
| `scripts/build_history_report.py` | Tailwind-ish slate/sky/amber palette, system-UI font stack with no Thai face named first. |
| `scripts/asr/asr_sample.py` | generic light page with a `prefers-color-scheme` dark block; rainbow verdict colours (`#dc2626 #16a34a #d97706 #7c3aed`). |
| `src/th_verify/static/index.html` | cream "newspaper" theme (`#f6f1e5`), **Google Fonts CDN** (Chonburi + Sarabun), rotated stamp, drop-shadow offsets, green/amber/blue semantics. |
| `src/th_verify/static/review.html` | same theme, same CDN, **plus a real bug**: a second `<style>` block was nested inside the first (line 70), so the CSS parser discarded a run of rules. |
| all of the above | no logo, no mark, no mono metadata layer, no `SYS //` grid language, no halftone, no X, no brackets, no tagline. |

## 3. What was built

* **`assets/brand/fnl-design-system.css`** — the whole system in one
  dependency-free file: palette and derived-neutral tokens, three type tiers,
  spacing/radii/rule scales, all five documented visual-language elements
  (halftone, X bars, UI brackets, grid & scale, yellow signals), components
  (cover, divider, stat tiles, tables, pull quotes, callouts, data bars,
  buttons, fields, meters, footers, A4 sheets), a print/PDF section, and the
  opt-in light variant. No `@import`, no webfont, no CDN, no network request.
* **`assets/brand/fnl-logo*.svg`** — five files: primary mark, horizontal
  lockup with the Thai wordmark, icon-only, and monochrome variants of the mark
  and lockup. Geometry is computed, so the two bars are exactly symmetrical and
  the halftone dissolve steps evenly.
* **`scripts/_brand.py`** — the helper the builders share: `document()`,
  `cover()`, `chip()`, `sys_rule()`, `footer()`, `mark()`, `favicon_data_uri()`,
  and `sync-static`.
* **`docs/brand-system.md`** — usage, incorrect-use rules, clear space, minimum
  sizes, tone of voice.

## 4. What was retrofitted

| file | change | verified by |
|---|---|---|
| `scripts/build_weekly_fakenews_report.py` | inline CSS deleted; renders through `_brand.document()` with a branded cover (mark, kicker, risk chips, mono metadata block), `SYS // WEEKLY` rule, `SEC // n` section labels, brand footer. Added `--print-economy`. | regenerated with `--no-llm --start 2026-07-24 --end 2026-07-31`; HTML screenshot; 6-page PDF rasterised — page 1 and the long claim-table continuation page both inspected |
| `scripts/build_issue_report.py` | inline CSS and Google Fonts deleted; class names kept and styled from tokens; verdict colours re-pointed to palette roles; mark added to the report header; added `--print-economy`. | `migrant` (336 records) and `callcenter_scam` (843 records) regenerated; HTML screenshots; 2-page A4 PDF rasterised in both the black and the `--print-economy` rendering |
| `scripts/build_history_report.py` | inline CSS deleted; brand cover with Thai-numeral title, metric tiles restyled from tokens, brand footer. Markdown output untouched. | regenerated; HTML screenshot |
| `scripts/asr/asr_sample.py` | inline CSS deleted; cover + `SYS //` group rules; rainbow verdict colours replaced by palette roles. | regenerated from a 1,332-label results file; screenshot |
| `scripts/build_html_report.py` | inline CSS and Google Fonts deleted; same treatment as the issue report. | see §6 — verified through a path-patched copy, not in place |
| `src/th_verify/static/index.html` | rebuilt on the system: CDN fonts removed, X-mark favicon, brand lockup, `SYS //` rules, `.fnl-field` search box, palette-role verdict badges. **Plus the `related` match level** (see §5). | screenshots of all four banner states with stubbed API responses |
| `src/th_verify/static/review.html` | rebuilt on the system; **nested `<style>` bug fixed**; every label button, the flash overlay and the progress meter re-coloured to palette roles. All JS, keyboard bindings and DOM ids unchanged. | screenshot with a stubbed queue item (article branch) |

Tests: **38 passed** before and after. No test touches styling; the invariant
suite (`tests/test_invariants.py`) covers label provenance and the read-only
API, none of which was modified.

Database access was read-only throughout. Nothing outside `data/reports/` was
written.

## 5. The `related` match level (coordinator request, folded in)

`/check` now returns a fourth `match_level`, `related`: below the semantic
threshold, but surfaced by both the embedding and the keyword search. Backend
(`api.py`, `db.py`) was already done and was not touched.

In `index.html`:

* an explicit `related` branch was added **before** the `else`, so a real result
  set is no longer stamped "ยังไม่พบ" — the bug where `ยาพารา` scored 0.8558 and
  the banner contradicted five relevant cards directly beneath it;
* copy: stamp **"พบเรื่องที่เกี่ยวข้อง"**, body explains that no whole-text match
  was found, points at the records below, and suggests pasting the full claim as
  a sentence for a more precise comparison. Calm, non-accusatory, no blame on
  the user for a short query;
* `.lv-related` uses **Alert Yellow `#FFD400`**, as instructed and as the guide
  implies: `related` is a pointer, not an alarm. Signal Red stays with `strong`.
* Line 250's `data.match_level !== "none"` guard reads correctly with the new
  level — every level except `none` can carry a top result, and `true-top` should
  apply to all of them. Left as is, with a comment saying why.

Verified by screenshot with stubbed payloads: `related` (yellow), `strong`
(red), `none` (grey). `possible` shares the `related` rule.

## 6. Deliberately left alone

* **`scripts/build_weekly_report.py`** — listed for retrofit, but it emits
  **Markdown only**. There is no CSS and no HTML to rebrand. It does declare
  `WEEKLY_HTML_PATH` and never write it; that dead constant is the only thing
  worth cleaning, and removing it is a behaviour-free change I left for the
  owner rather than bundling into a brand pass.
* **`scripts/build_brief.py`** — Markdown only, same reason. Not listed, not
  touched.
* **`src/th_verify/api.py` and `db.py`** — the coordinator's message said these
  were finished and tested. Not touched. This is why the two static pages carry
  an inlined copy of the stylesheet rather than linking to a served
  `/brand.css`: adding that route would have meant editing `api.py`. If a route
  is ever added, both pages can switch to a `<link>` and `sync-static` can be
  retired.
* **`scripts/build_html_report.py` was not executed in place.** It hardcodes
  `db_path = "/Users/visarutsankham/th-verify/data/th_verify.db"` and writes to
  `/Users/visarutsankham/Desktop/`, neither of which exists on this machine. I
  verified the retrofit by running a copy with only those two paths rewritten,
  against the local DB — it produced a correct branded report (331 records).
  The committed file differs from the verified one **only** in those two path
  literals. `HANDOFF.md` already records that `build_issue_report.py` replaces
  it; my recommendation is to delete it rather than maintain two copies of the
  same report.
* **Existing report *content*** — no editorial text, no Thai copy, no
  calculation, no section was changed anywhere. The cover blocks re-lay-out the
  title/subtitle/metadata that the reports already emitted; nothing was dropped.
* **`data/` outside `data/reports/`** — untouched, as instructed.

## 7. Bugs found while verifying, and what I did about them

1. **Pipe characters in claim titles broke the weekly report's Markdown
   tables.** A real claim — `📍 ภัยสมองเน่าจาก Brain Rot | [REPLAY]` — contains a
   literal `|`, which split its table row into an extra column in both the
   Markdown and the rendered HTML. Pre-existing, visible in the last published
   edition. Fixed with an `md_cell()` escape on the two table cells that carry
   claim text. **This changes the `.md` output** (a `\|` escape), which is why it
   is called out rather than buried.
2. **`review.html` had a `<style>` block nested inside another `<style>`
   block** — the entire file's CSS after that point was being parsed as garbage.
   Fixed by the rewrite.
3. **Chrome does not propagate the root background into the `@page` margin
   area.** The first black PDF came out as a black column in a white frame. The
   fix — painting the page box with `@page { background: #000000 }` — was found
   by testing three candidate techniques and rasterising each; a
   `position: fixed` full-bleed layer, the usual workaround, is clipped to the
   page area and does **not** work.
4. **A Thai display headline at 3.05rem overflows A4 and is clipped.** Thai has
   no inter-word spaces to break at, so it does not wrap politely — it runs off
   the sheet. Print now reduces the display scale and adds `overflow-wrap` as a
   backstop.
5. **The timeline's tallest bar overlapped the section title above it** in the
   `callcenter_scam` report (its 227-record year hit the ceiling). Pre-existing
   geometry, `height: 125px` for ~130px of content; raised to 145px.

## 8. Judgement calls, and where I was guessing

Flagged honestly — these are the places where the spec I was given did not
decide the question for me.

**Guesses about brand intent:**

* **Which bar is red.** The guide says "two crossing bars, red and white". I put
  Field White on the `/` axis and Signal Red on the `\` axis, red painted over
  white at the crossing. If the real mark is the other way round, swap two fills
  in the SVG.
* **The halftone dissolve pattern.** "Density gradients" is all I had. I used six
  rows per bar end, shrinking radius and opacity, dropping columns as they
  travel. It reads as a dot-matrix dissolve; it is not a reconstruction of a
  specific artwork.
* **The heading face.** The guide asks for "geometric, squarish, high-impact".
  No such face can be assumed present offline, and the brief forbids CDNs, so
  the heading tier is the body family at weight 800 with tight tracking, and
  squareness is carried by zero radii, hard rules and mono system labels.
  Adding a licensed display face later is a one-line change to
  `--fnl-font-head`.
* **Yellow on a `บิดเบือน` verdict badge.** The guide says yellow is for
  indicators and never for body text. I read a verdict badge and a highlighted
  table cell as indicators, so yellow is used there. If yellow is meant to be
  reserved strictly for interface markers, those two usages are the ones to
  revisit.
* **Verdict colours generally.** The palette has no green, so the previous
  green-for-true convention had to go. `ข่าวจริง` is now Field White. That is a
  semantic downgrade in visibility, chosen because inventing a sixth colour is
  worse.
* **`SEC // 3.1` section labels.** Extrapolated from the guide's `SYS // 001`
  example. The pattern is right; the exact token may not be.
* **Clear space = "one X-bar width"** interpreted as the bar thickness, 22/120
  of the mark's height (~18% of its size) on all four sides.
* **Thai copy for the `related` banner** is mine, written to the guide's tone
  rules. A Thai editor should read it before it goes public.

**Engineering calls:**

* **Kept the report builders' existing class names** (`.pill`, `.trend-tbl`,
  `.insight`, …) and styled them from tokens in a clearly-marked "report
  component layer", instead of renaming everything to `fnl-`. That markup is
  dense Thai-bearing f-string HTML; a global class rename is the highest-risk,
  lowest-reward edit available here. New markup should use the `fnl-`
  components. The cost is two vocabularies in one stylesheet, documented.
* **Links are Field White, not Signal Red**, so that a table of claim links does
  not become a wall of red and destroy red's meaning. Red on hover.
* **Removed Google Fonts from all four files that used it.** Required by the
  brief (self-contained, no CDN), and on the public check page it is also a
  privacy fix: the page promises queries are not logged, while every visit was
  announcing the visitor's IP to a third party. The cost is that `Sarabun` is
  only used where it happens to be installed; on macOS the stack falls to
  Thonburi and Thai still shapes correctly (verified in every screenshot).
* **Dropped Chonburi** (the decorative display face on the public page). It is a
  high-contrast Thai display serif and reads nothing like "geometric, squarish".
* **The stamp on the public page no longer rotates.** The rotation was a
  rubber-stamp affectation; `ห้ามหมุน` governs the mark specifically, but a
  rotated element next to a mark that must never rotate sends a mixed signal.
  It is now a bracketed mono label.
* **Emoji favicons replaced by the X mark** as a data URI on both static pages
  and every generated report.
* **`--print-economy` is a CLI flag, not a default and not automatic.** Both
  `build_weekly_fakenews_report.py` and `build_issue_report.py` accept it. The
  black rendering is what you get unless you ask otherwise.
* **Introduced `--fnl-signal-ink`**, Alert Yellow in its text role, so the light
  variant can re-point yellow-as-text to a legible ochre without disturbing
  yellow-as-fill. Yellow's hex is untouched in the dark rendering.

## 9. Known gaps

* `build_html_report.py` retrofitted but not run in place (§6). Recommend
  deletion.
* No test asserts brand compliance. A cheap one would be a regression test that
  fails if any file under `scripts/` or `src/th_verify/static/` contains a
  `fonts.googleapis.com` reference or a hex colour outside the palette. Not
  added — the brief asked for the suite to keep passing, not to grow, and I did
  not want to add a test whose failure mode is stylistic.
* The `.md` and `.pdf` products of the weekly report now disagree slightly in
  one respect: the Markdown carries `\|` escapes in two table cells. Correct
  Markdown, mildly ugly in a plain-text reader.
* The horizontal lockup's wordmark is live text, not outlines. Fine for screen
  and for Chrome-printed PDFs; outline it before commercial printing.
* The light variant's highlighted table cells (`td.hl`) sit on a pale yellow
  wash with black text. It is legible and correct, but it is the one place where
  the light rendering reads noticeably softer than the black one, where the same
  cell is a bright yellow figure. Acceptable for a print-economy mode; worth
  knowing before anyone uses `--print-economy` for a client deliverable.
