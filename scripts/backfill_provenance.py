"""One-off provenance backfill for verdict_origin (idempotent).

- afnc / afp / thaipbs verdicts came from the fact-checking source itself.
- cofact's current Thai verdicts are ambiguous: they appeared after a
  re-backfill AND the heuristic classifier both ran, so we conservatively
  mark them 'heuristic' (lower trust tier). A future cofact re-sync with
  collector-side verdict extraction can upgrade them.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from th_verify.db import Repository  # noqa: E402

DB = Path(sys.argv[1] if len(sys.argv) > 1 else "data/th_verify.db")

Repository(DB).initialize()  # runs the column migration
con = sqlite3.connect(DB)
with con:
    n_source = con.execute(
        "UPDATE fact_checks SET verdict_origin='source' "
        "WHERE verdict_origin='' AND verdict!='unknown' "
        "AND source IN ('afnc','afp','thaipbs')"
    ).rowcount
    n_heur = con.execute(
        "UPDATE fact_checks SET verdict_origin='heuristic' "
        "WHERE verdict_origin='' AND verdict!='unknown' AND source='cofact'"
    ).rowcount
print(f"marked source={n_source} heuristic={n_heur}")
for row in con.execute(
    "SELECT source, verdict_origin, COUNT(*) FROM fact_checks "
    "GROUP BY source, verdict_origin ORDER BY source"
):
    print(row)
