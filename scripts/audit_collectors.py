#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_collectors.py — prove each collector still works, without writing anything.

Why "success" in sync_runs is not enough
---------------------------------------
Every source has reported success every night since 2026-07-29, and during that
window the Thai PBS collector was writing the WRONG VERDICT onto hundreds of
records: it walked up the DOM for a card's text and overshot into a wrapper
covering several articles, so each record inherited its neighbour's verdict and
date. 103 labels were wrong and 287 rows needed repair. Nothing in sync_runs
could have shown that — the fetch succeeded, records were produced, the run was
marked success.

A publisher can also break a collector without anyone noticing: change a CSS
class and a field quietly starts arriving empty, forever, while the run still
"succeeds" because 20 records came back.

So this checks the two things sync_runs cannot:

  1. LIVE   — fetch a handful of records from each source right now and inspect
              the fields. Nothing is written; the collectors are driven directly
              rather than through ingest(), so no run is recorded and no upsert
              happens.
  2. STORED — look at what the last week actually deposited, and compare each
              source against its own history. A source that normally yields ten
              records a day and has yielded none for four days is a failure that
              reports success.

Field expectations differ by source and that is legitimate, not a defect:
AFP arrives from the Google Fact Check API as metadata only (no article text,
no image), and AFNC has never carried images. Those are encoded as per-source
expectations so the audit does not cry wolf every run -- an audit that is
noisy is an audit nobody reads.

Exit code is 1 if anything is FAIL, so this can be wired into the nightly job.

Usage:
    python scripts/audit_collectors.py                 # live + stored
    python scripts/audit_collectors.py --stored-only   # no network
    python scripts/audit_collectors.py --source thaipbs --sample 8
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from th_verify.collectors import (  # noqa: E402
    AfncCollector, AfpCollector, CofactCollector, SureShareCollector, ThaiPbsCollector,
)
from th_verify.config import Settings  # noqa: E402
from th_verify.normalized import normalize_verdict  # noqa: E402

# What each source is genuinely expected to provide. Anything listed here that
# arrives empty is a real defect; anything absent from the list is not.
EXPECT: dict[str, dict] = {
    "cofact":     {"text": True,  "image": True,  "verdict": False, "quiet_days": 4},
    "thaipbs":    {"text": True,  "image": True,  "verdict": True,  "quiet_days": 5},
    # Google Fact Check API returns claim + rating + url, never article body.
    "afp":        {"text": False, "image": False, "verdict": True,  "quiet_days": 7},
    # Verdict is spoken in the video, not present in YouTube metadata.
    "sure_share": {"text": False, "image": True,  "verdict": False, "quiet_days": 3},
    "afnc":       {"text": True,  "image": False, "verdict": True,  "quiet_days": 2},
}

OK, WARN, FAIL = "PASS", "WARN", "FAIL"


class Report:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str, str]] = []

    def add(self, level: str, source: str, message: str) -> None:
        self.lines.append((level, source, message))

    @property
    def failed(self) -> bool:
        return any(lv == FAIL for lv, _, _ in self.lines)

    def print(self) -> None:
        icon = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}
        for level, source, message in self.lines:
            print(f"[{icon[level]}] {source:11} {message}")


async def live_check(source: str, sample: int, settings: Settings, rep: Report) -> None:
    """Fetch a few records and inspect them. Writes nothing."""
    headers = {"User-Agent": settings.user_agent,
               "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"}
    async with httpx.AsyncClient(headers=headers, timeout=settings.timeout_seconds,
                                 follow_redirects=True) as client:
        collectors = {
            "cofact": lambda: CofactCollector(client),
            "thaipbs": lambda: ThaiPbsCollector(client),
            "afp": lambda: AfpCollector(client, settings.google_factcheck_api_key),
            "sure_share": lambda: SureShareCollector(client, settings.youtube_api_key),
            "afnc": lambda: AfncCollector(client),
        }
        # Retry before crying wolf. On its first unattended night this reported
        # FAIL because AFNC timed out once -- four minutes after AFNC's real sync
        # had succeeded with 56 records, and with every stored check passing. A
        # red banner for a transient network blip is worse than no banner: it
        # teaches the reader to ignore the one that matters.
        got, last = [], None
        for attempt in range(3):
            try:
                got = []
                async for rec in collectors[source]().collect(mode="delta", limit=sample):
                    got.append(rec)
                last = None
                # Retry an EMPTY result too, not just an exception. On
                # 2026-09-01 AFNC answered 200-with-nothing at 03:34 and the
                # banner went red; the same fetch returned six records on
                # demand later that morning, and every stored check had passed.
                # A publisher's momentary empty response was crying wolf just
                # as loudly as a real outage -- which is the exact thing the
                # retry above was added to stop.
                if got or attempt == 2:
                    break
            except Exception as exc:
                last = exc
            if attempt < 2:
                await asyncio.sleep(5 * (attempt + 1))
        if last is not None:
            rep.add(FAIL, source,
                    f"live fetch failed 3 times, last {type(last).__name__}: {str(last)[:70]}")
            return

    rep.add(OK, source, f"live fetch returned {len(got)} records")
    for level, msg in inspect_records(source, got):
        rep.add(level, source, msg)


def inspect_records(source: str, got: list) -> list[tuple[str, str]]:
    """Judge a batch of freshly fetched records. Pure, so it can be tested.

    Kept apart from the fetching deliberately: a health check nobody has seen
    fail is not a health check. These rules are exercised in the test suite
    against the shapes that actually broke before -- an empty selector, and the
    Thai PBS listing bleed that gave neighbouring records one date.
    """
    if not got:
        return [(FAIL, "live fetch returned no records at all")]
    out: list[tuple[str, str]] = []
    exp = EXPECT[source]

    def share(pred) -> float:
        return sum(1 for r in got if pred(r)) / len(got)

    # A field empty on EVERY sampled record is a parser that stopped matching.
    # One or two blanks are ordinary; all of them is a broken selector, which is
    # exactly how the Thai PBS bug would have looked.
    if share(lambda r: not (r.title or "").strip()) > 0:
        out.append((FAIL, "some records have no title"))
    if share(lambda r: not r.source_url or not r.source_url.startswith("http")) > 0:
        out.append((FAIL, "some records have a missing or malformed url"))
    if share(lambda r: not r.published_at) == 1:
        out.append((FAIL, "no record carried a publication date"))
    elif share(lambda r: not r.published_at) > 0.5:
        out.append((WARN, f"{share(lambda r: not r.published_at):.0%} of records have no date"))

    if exp["text"] and share(lambda r: len(r.explanation or "") < 100) == 1:
        out.append((FAIL, "no record carried article text (selector may have changed)"))
    if exp["image"] and share(lambda r: not r.image_url) == 1:
        out.append((FAIL, "no record carried an image url"))
    if exp["verdict"]:
        # Thai PBS's ตรวจสอบแล้ว / ไม่สแตมป์ข่าว stamps normalize to "unknown" on
        # purpose (see normalized.py) -- they are real editorial output, ~7% of
        # thaipbs historically, not a parser failure. They cluster on the
        # listing page, so a small sample can be dominated by a single run of
        # them; --sample defaults to 20 for exactly this reason (2026-08-24: a
        # 6-record sample hit 4/6 and fired a WARN over ordinary content).
        blank = share(lambda r: normalize_verdict(source, r.verdict) == "unknown")
        if blank == 1:
            out.append((FAIL, "no record carried a usable verdict"))
        elif blank > 0.5:
            out.append((WARN, f"{blank:.0%} of records had no usable verdict"))

    # Cross-contamination: the Thai PBS bug walked up the DOM into a wrapper
    # spanning several cards, so neighbouring records inherited one date AND one
    # verdict. Both together is the fingerprint -- a shared verdict alone is
    # meaningless, since AFNC stamps ข่าวปลอม on nearly everything it publishes
    # and a batch of six identical verdicts there is a normal Tuesday.
    dates = {r.published_at for r in got if r.published_at}
    verdicts = {(r.verdict or "") for r in got}
    if len(got) >= 4 and len(dates) == 1 and len(verdicts) == 1:
        out.append((WARN, f"every sampled record shares one date ({sorted(dates)[0][:10]}) "
                          f"and one verdict ({sorted(verdicts)[0]}) — check for listing-page bleed"))
    return out


def stored_check(db: str, source: str, rep: Report) -> None:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    exp = EXPECT[source]

    row = con.execute(
        "SELECT COUNT(*) n, MAX(first_seen_at) last_new, MAX(published_at) newest "
        "FROM fact_checks WHERE source=?", (source,)).fetchone()
    if not row["n"]:
        rep.add(FAIL, source, "no records stored at all")
        return

    # first_seen_at is the only honest "did we get anything new" column:
    # collected_at is refreshed on every upsert, so for AFP it reads 100 every
    # night regardless -- that is the API page size, not the day's publishing.
    last_new = (row["last_new"] or "")[:10]
    if last_new:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(last_new).replace(tzinfo=timezone.utc)).days
        if age > exp["quiet_days"]:
            rep.add(FAIL, source, f"no new record for {age} days "
                                  f"(quiet limit {exp['quiet_days']}) — last {last_new}")
        else:
            rep.add(OK, source, f"last new record {last_new} ({age}d ago), "
                                f"newest article {(row['newest'] or '')[:10]}")

    # Report what ARRIVED, never records_seen. sync_runs.records_seen is a PAGE
    # SIZE -- cofact reports 20 every night, sure_share 50, afp 100, across 31
    # runs with min == max, whatever the publishers did that day. Quoting it as
    # output implies AFP filed 100 fact-checks and Sure & Share shot 50 videos.
    # first_seen_at is the honest column: the upsert deliberately leaves it alone.
    day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    fresh = con.execute("SELECT COUNT(*) FROM fact_checks WHERE source=? "
                        "AND first_seen_at >= ?", (source, day_ago)).fetchone()[0]
    week = con.execute("SELECT COUNT(*) FROM fact_checks WHERE source=? "
                       "AND first_seen_at >= ?",
                       (source, (datetime.now(timezone.utc) - timedelta(days=7)).isoformat())
                       ).fetchone()[0]
    rep.add(OK, source, f"new records: {fresh} in the last 24h, {week} in 7 days")

    since = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    recent = con.execute(
        "SELECT verdict, published_at, image_url, explanation, title, claim "
        "FROM fact_checks WHERE source=? AND first_seen_at >= ?", (source, since)).fetchall()
    if not recent:
        return
    n = len(recent)
    if exp["verdict"]:
        blank = sum(1 for r in recent
                    if normalize_verdict(source, r["verdict"]) == "unknown") / n
        if blank > 0.5:
            rep.add(FAIL, source, f"{blank:.0%} of the last fortnight's records "
                                  "arrived without a usable verdict")
    if exp["text"]:
        thin = sum(1 for r in recent if len(r["explanation"] or "") < 100) / n
        if thin > 0.5:
            rep.add(FAIL, source, f"{thin:.0%} of the last fortnight's records arrived "
                                  "with no article text")
    rep.add(OK, source, f"{n} records in the last 14 days")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="data/th_verify.db")
    ap.add_argument("--source", help="audit one source instead of all five")
    # 6 was too small: Thai PBS legitimately publishes ตรวจสอบแล้ว/ไม่สแตมป์ข่าว
    # (checked-but-no-polarity) stamps at roughly a 7% historical rate, but they
    # cluster -- several in a row from the same listing page -- so a sample of 6
    # caught 4 of them on 2026-08-24 and fired a WARN at 67% for something that
    # is normal editorial output, not a broken parser. 20 makes that a
    # near-impossible false positive at the real base rate while still catching
    # an actually-broken selector (which shows up at or near 100%, not a burst).
    ap.add_argument("--sample", type=int, default=20, help="records to fetch live per source")
    ap.add_argument("--stored-only", action="store_true", help="skip the network")
    ap.add_argument("--json", type=Path,
                    help="also write the result here for the review room to read")
    args = ap.parse_args()

    sources = [args.source] if args.source else list(EXPECT)
    for s in sources:
        if s not in EXPECT:
            print(f"unknown source: {s}")
            return 2

    settings = Settings.from_env()
    rep = Report()
    for s in sources:
        stored_check(args.db, s, rep)
        if not args.stored_only:
            asyncio.run(live_check(s, args.sample, settings, rep))

    rep.print()
    fails = sum(1 for lv, _, _ in rep.lines if lv == FAIL)
    warns = sum(1 for lv, _, _ in rep.lines if lv == WARN)
    print(f"\n{len(sources)} sources — {fails} failing, {warns} warning")

    if args.json:
        # Written for the review room, which is the only surface anybody looks
        # at daily. A health check whose output lands in a log file nobody opens
        # has the same value as no health check.
        import json as _json
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(_json.dumps({
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "sources": sources,
            "failing": fails,
            "warning": warns,
            "findings": [{"level": lv, "source": src, "message": msg}
                         for lv, src, msg in rep.lines if lv != OK],
            "ok": [{"source": src, "message": msg}
                   for lv, src, msg in rep.lines if lv == OK],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"written: {args.json}")
    return 1 if rep.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
