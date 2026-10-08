#!/usr/bin/env python3
"""Build the offline coding app for Story 2: ONE self-contained HTML file for a single coder.

Written after the owner confirmed (2026-10-07) that nobody else is available to code, so
the two-coder design (inter-coder kappa) is replaced by test-retest: the coder codes every
row, waits, then re-codes a random sample blind, and the agreement between the coder's
own two passes is the reliability figure.

The file embeds the coder_A sheet (rows + order) and a list of RETEST ids. The ids are
drawn here, stratified toward rows the assistant thought were in scope (so frame
agreement has enough rows to be measured); the strata themselves are NOT embedded, so the
coder cannot see any model label. At retest time the app also adds every row the coder
called `unclear` (method doc 9.5: "every unclear row").

It works offline from a double-click, saves in the browser, and exports CSVs with exactly
the sheet's columns (+ coded_at), which scripts/score_story2_single_coder.py reads.

Reads deliverables/story2_coding/{coder_A.csv,master_key.csv}; writes coding_app.html beside them.
"""
import csv, json, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'deliverables/story2_coding'
TEMPLATE = ROOT / 'assets/story2_coding_app/template.html'
KEEP = ['id', 'source', 'date', 'verdict', 'title', 'claim_text', 'url', 'phase']
FORBIDDEN = {'assistant_scope', 'retrieval_route', 'similarity', 'queue_round', 'screened_subtopic', 'scope_interim', 'group_marker'}
SEED = 20261007
N_LIKELY_IN, N_LIKELY_OUT = 62, 42      # 104 rows = 20.3% of 513, the method doc's "at least 20%" before adding the coder's own `unclear` rows
LIKELY_IN = {'resident_refugee_status', 'crossborder_people_services', 'unclear'}


def retest_sample(rows, master):
    ids = [r['id'] for r in rows]
    by = {m['id']: m['assistant_scope'] for m in master}
    assert set(ids) <= set(by), 'master key does not cover the sheet'
    rng = random.Random(SEED)
    likely_in = sorted(i for i in ids if by[i] in LIKELY_IN)
    likely_out = sorted(i for i in ids if by[i] not in LIKELY_IN)
    pick = rng.sample(likely_in, min(N_LIKELY_IN, len(likely_in))) + rng.sample(likely_out, min(N_LIKELY_OUT, len(likely_out)))
    return sorted(pick, key=int)


def main(out_dir: Path = DIR) -> int:
    tpl = TEMPLATE.read_text(encoding='utf-8')
    assert tpl.count('/*__DATA__*/[]') == 1 and tpl.count('/*__RETEST__*/[]') == 1
    src = out_dir / 'coder_A.csv'
    with src.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if FORBIDDEN & set(rows[0]):
        sys.exit(f'{src} contains model columns; refusing to build')
    if any(r.get('scope', '').strip() for r in rows):
        sys.exit(f'{src} already has answers; build the app from an empty sheet')
    with (out_dir / 'master_key.csv').open(encoding='utf-8-sig', newline='') as f:
        master = list(csv.DictReader(f))
    sample = retest_sample(rows, master)
    esc = lambda o: json.dumps(o, ensure_ascii=False).replace('</', '<\\/')
    html = tpl.replace('/*__DATA__*/[]', esc([{k: r[k] for k in KEEP} for r in rows])).replace('/*__RETEST__*/[]', esc(sample))
    (out_dir / 'coding_app.html').write_text(html, encoding='utf-8')
    print(f'coding_app.html: {len(rows)} rows ({sum(r["phase"] == "calibration" for r in rows)} warm-up), retest base {len(sample)} rows '
          f'({len(sample) / len(rows) * 100:.1f}%), {len(html) // 1024} KB')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
