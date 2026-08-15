#!/usr/bin/env python3
"""
repair_thaipbs_verdicts.py — re-derive Thai PBS Verify verdicts and dates from
the publisher's own schema.org ClaimReview block.

Why this exists
---------------
The thaipbs collector used to read the verdict and the fallback publication date
out of a container walked up from each listing link. The walk had only a
140-character floor, so it regularly overshot into a wrapper holding several
article cards. Every record cut from such a wrapper inherited the *first* card's
verdict and date. Those labels carry ``verdict_origin='source'`` — the gold tier
— so the corruption flowed straight into the classification exports.

The collector is fixed (``collectors/thaipbs.py`` now reads ClaimReview and
refuses to walk past a card boundary), but rows already written keep their bad
values until re-derived. This script does that re-derivation.

Safety
------
* Dry run by default. ``--apply`` is required to write.
* Rows with ``verdict_origin='human'`` are never touched, matching the guarantee
  in ``db.py upsert_many``.
* Only ``verdict`` and ``published_at`` are rewritten, and only when the
  publisher's ClaimReview actually disagrees with what is stored.
* Every change is written to a JSON report so a bad run can be reversed.

Usage
-----
    python scripts/repair_thaipbs_verdicts.py                      # dry run, all rows
    python scripts/repair_thaipbs_verdicts.py --suspect-only       # dry run, likely-corrupt rows
    python scripts/repair_thaipbs_verdicts.py --apply              # write
    python scripts/repair_thaipbs_verdicts.py --db /path/to.db     # target another copy
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from th_verify.collectors.thaipbs import parse_claim_review  # noqa: E402
from build_dataset import normalize_verdict  # noqa: E402
from _canonical import assert_canonical  # noqa: E402

DEFAULT_DB = Path("data/th_verify.db")
USER_AGENT = "th-verify-repair/1.0 (+https://github.com/visarutforthaipbs/verified-th-news)"

# Rows sharing an archive_text blob with another row came from an overshot
# container, so their verdict and date are both suspect.
SUSPECT_SQL = """
SELECT source_id, source_url, verdict, published_at, verdict_origin
FROM fact_checks
WHERE source = 'thaipbs'
  AND verdict_origin != 'human'
  AND json_extract(raw_json, '$.archive_text') IN (
        SELECT json_extract(raw_json, '$.archive_text')
        FROM fact_checks WHERE source = 'thaipbs'
        GROUP BY 1 HAVING COUNT(*) > 1
  )
ORDER BY source_id
"""

ALL_SQL = """
SELECT source_id, source_url, verdict, published_at, verdict_origin
FROM fact_checks
WHERE source = 'thaipbs' AND verdict_origin != 'human'
ORDER BY source_id
"""


def fetch_claim_review(client: httpx.Client, url: str) -> tuple[str | None, str | None]:
    response = client.get(url)
    if response.is_error:
        raise RuntimeError(f"HTTP {response.status_code}")
    return parse_claim_review(HTMLParser(response.text))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    parser.add_argument("--suspect-only", action="store_true",
                        help="only rows that shared a listing blob with another row")
    parser.add_argument("--rewrite-representation", action="store_true",
                        help="also rewrite verdicts whose meaning is unchanged "
                             "(e.g. stored 'false' -> published 'ข่าวปลอม')")
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--report-dir", type=Path, default=Path("data/repair"))
    args = parser.parse_args()

    if not args.db.exists():
        print(f"database not found: {args.db}", file=sys.stderr)
        return 1
    # Scanning is read-only and unrestricted; committing corrections is not.
    if args.apply:
        assert_canonical(args.db, action="rewrite verdicts in")

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(SUSPECT_SQL if args.suspect_only else ALL_SQL).fetchall()
    if args.limit:
        rows = rows[: args.limit]

    print(f"database     : {args.db}")
    print(f"scope        : {'suspect rows only' if args.suspect_only else 'all non-human thaipbs rows'}")
    print(f"rows to check: {len(rows)}")
    print(f"mode         : {'APPLY (writes)' if args.apply else 'dry run'}")
    print()

    changes: list[dict] = []
    failures: list[dict] = []
    unchanged = 0

    with httpx.Client(timeout=30, follow_redirects=True, headers={"user-agent": USER_AGENT}) as client:
        for i, row in enumerate(rows, 1):
            try:
                verdict, published = fetch_claim_review(client, row["source_url"])
            except Exception as exc:  # network/parse issues must not abort a long run
                failures.append({"source_id": row["source_id"], "url": row["source_url"], "error": str(exc)})
                print(f"[{i}/{len(rows)}] {row['source_id']:>7}  FAILED: {exc}")
                time.sleep(args.delay)
                continue

            if verdict is None and published is None:
                failures.append({"source_id": row["source_id"], "url": row["source_url"],
                                 "error": "no ClaimReview block found"})
                print(f"[{i}/{len(rows)}] {row['source_id']:>7}  no ClaimReview — left alone")
                time.sleep(args.delay)
                continue

            delta = {}
            if verdict and verdict != row["verdict"]:
                # A stored 'false' and a ClaimReview 'ข่าวปลอม' mean the same thing;
                # only the raw representation differs. Rewriting those churns rows
                # without changing a single label, so by default they are left alone.
                old_norm = normalize_verdict("thaipbs", row["verdict"])
                new_norm = normalize_verdict("thaipbs", verdict)
                if old_norm == new_norm:
                    kind = "representation"
                elif old_norm == "unknown":
                    kind = "fill_unknown"
                else:
                    kind = "label_flip"
                if kind != "representation" or args.rewrite_representation:
                    delta["verdict"] = {
                        "old": row["verdict"], "new": verdict,
                        "old_normalized": old_norm, "new_normalized": new_norm,
                        "kind": kind,
                    }
                    # The value now comes from the publisher's own ClaimReview, so the
                    # provenance tier must say so rather than keeping a stale 'llm'.
                    if row["verdict_origin"] != "source":
                        delta["verdict_origin"] = {"old": row["verdict_origin"], "new": "source"}
            if published and published != row["published_at"]:
                delta["published_at"] = {"old": row["published_at"], "new": published}

            if not delta:
                unchanged += 1
            else:
                changes.append({"source_id": row["source_id"], "url": row["source_url"], **delta})
                parts = [f"{k}: {v['old']!r} -> {v['new']!r}" for k, v in delta.items()
                         if k != "verdict_origin"]
                print(f"[{i}/{len(rows)}] {row['source_id']:>7}  " + "; ".join(parts))

            time.sleep(args.delay)

    print()
    kinds = {"label_flip": 0, "fill_unknown": 0, "representation": 0}
    for change in changes:
        if "verdict" in change:
            kinds[change["verdict"]["kind"]] += 1
    date_only = sum(1 for c in changes if "verdict" not in c and "published_at" in c)

    print(f"already correct : {unchanged}")
    print(f"rows to update  : {len(changes)}")
    print(f"failed to check : {len(failures)}")
    print()
    print(f"  wrong label corrected   : {kinds['label_flip']}   <- these were genuinely mislabelled")
    print(f"  unknown -> real label   : {kinds['fill_unknown']}")
    print(f"  representation rewrite  : {kinds['representation']}   "
          f"({'included' if args.rewrite_representation else 'skipped; --rewrite-representation to include'})")
    print(f"  date-only correction    : {date_only}")

    args.report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = args.report_dir / f"thaipbs_repair_{stamp}{'' if args.apply else '_dryrun'}.json"
    report.write_text(json.dumps(
        {"database": str(args.db), "applied": args.apply, "generated_at": stamp,
         "unchanged": unchanged, "changes": changes, "failures": failures},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report written  : {report}")

    if not args.apply:
        print("\ndry run — nothing written. Re-run with --apply to commit these changes.")
        conn.close()
        return 0

    with conn:
        for change in changes:
            sets, params = [], []
            if "verdict" in change:
                sets.append("verdict = ?")
                params.append(change["verdict"]["new"])
            if "verdict_origin" in change:
                sets.append("verdict_origin = ?")
                params.append(change["verdict_origin"]["new"])
            if "published_at" in change:
                sets.append("published_at = ?")
                params.append(change["published_at"]["new"])
            params.append(change["source_id"])
            conn.execute(
                f"UPDATE fact_checks SET {', '.join(sets)} "
                "WHERE source = 'thaipbs' AND source_id = ? AND verdict_origin != 'human'",
                params,
            )
    conn.close()
    print(f"\napplied {len(changes)} row updates.")
    print("Re-run scripts/build_dataset.py and `th-verify index` so exports pick this up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
