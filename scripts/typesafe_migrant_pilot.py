#!/usr/bin/env python3
"""Prepare or run a TypeSafe pilot over migrant-story review candidates."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from th_verify.typesafe_review import (
    QUESTION_SET_VERSION,
    build_payload,
    call_system_one,
    parse_response,
    question_set_sha256,
    route_for_human_review,
)

DEFAULT_INPUT = ROOT / "runs/20260908_bertopic_v001/migrant_scope_decisions.csv"
DEFAULT_OUTPUT = ROOT / "runs/20260921_typesafe_pilot_v001"
STRATA = ("resident_refugee_status", "crossborder_people_services", "out_of_scope", "unclear")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def stratified_sample(rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    """Deterministic balanced sample, spread across time within each class."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("assistant_scope", "")].append(row)
    for values in grouped.values():
        values.sort(key=lambda row: (row.get("year", ""), row.get("source", ""), row.get("id", "")))
    target = min(limit, len(rows))
    quotas = Counter()
    remaining = {scope: len(grouped[scope]) for scope in STRATA}
    while sum(quotas.values()) < target:
        added = False
        for scope in STRATA:
            if remaining[scope] > quotas[scope] and sum(quotas.values()) < target:
                quotas[scope] += 1
                added = True
        if not added:
            break

    picked: dict[str, list[dict[str, str]]] = {}
    for scope in STRATA:
        values = grouped[scope]
        quota = quotas[scope]
        if quota == 1:
            indices = [len(values) // 2]
        elif quota > 1:
            indices = [int(i * (len(values) - 1) / (quota - 1)) for i in range(quota)]
        else:
            indices = []
        picked[scope] = [values[min(index, len(values) - 1)] for index in indices]

    selected: list[dict[str, str]] = []
    for index in range(max(quotas.values(), default=0)):
        for scope in STRATA:
            if index < len(picked[scope]):
                selected.append(picked[scope][index])
    return selected


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--live", action="store_true", help="Call TypeSafe; requires TYPESAFE_API_KEY")
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be positive")
    rows = read_csv(args.input)
    selected = stratified_sample(rows, args.limit)
    args.output.mkdir(parents=True, exist_ok=True)

    payload_path = args.output / "pilot_request_payloads.jsonl"
    with payload_path.open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(json.dumps({"record_id": row["id"], "payload": build_payload(row)}, ensure_ascii=False) + "\n")

    manifest: dict[str, Any] = {
        "status": "payloads_only",
        "input": str(args.input),
        "candidate_records": len(rows),
        "pilot_records": len(selected),
        "pilot_assistant_scope_counts": dict(Counter(row["assistant_scope"] for row in selected)),
        "pilot_year_counts": dict(sorted(Counter(row["year"] for row in selected).items())),
        "question_set_version": QUESTION_SET_VERSION,
        "question_set_sha256": question_set_sha256(),
        "live_requested": args.live,
        "human_fields_modified": False,
        "language_caveat": (
            "Jev accepts Thai, but TypeSafe documents English as its strongest language; "
            "validate on Thai human-coded records before operational use."
        ),
        "warning": "TypeSafe outputs are screening signals, not verified facts or human narrative labels.",
    }

    if not args.live:
        (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    api_key = os.getenv("TYPESAFE_API_KEY")
    if not api_key:
        parser.error("--live requires TYPESAFE_API_KEY")

    output_rows: list[dict[str, Any]] = []
    raw_path = args.output / "pilot_raw_responses.jsonl"
    with httpx.Client(timeout=60.0) as client, raw_path.open("w", encoding="utf-8") as raw_handle:
        for row in selected:
            response = call_system_one(client, api_key, build_payload(row))
            parsed = parse_response(response)
            priority, reasons = route_for_human_review(row["assistant_scope"], parsed)
            raw_handle.write(json.dumps({"record_id": row["id"], "response": response}, ensure_ascii=False) + "\n")
            flat = {
                "id": row["id"],
                "year": row["year"],
                "source": row["source"],
                "claim_text": row["claim_text"],
                "title": row["title"],
                "url": row["url"],
                "assistant_scope": row["assistant_scope"],
                **parsed,
                "typesafe_frames_applicable": parsed["typesafe_scope"]
                in {"resident_refugee_status", "crossborder_people_services"},
                "typesafe_review_priority": priority,
                "typesafe_review_reasons": ";".join(reasons),
                "human_scope": row.get("human_scope", ""),
                "human_frame": row.get("human_frame", ""),
                "human_review_status": row.get("human_review_status", "pending"),
            }
            for key, value in list(flat.items()):
                if isinstance(value, (dict, list)):
                    flat[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
            output_rows.append(flat)

    write_csv(args.output / "pilot_results.csv", output_rows)
    manifest.update(
        {
            "status": "live_complete",
            "typesafe_model_versions": sorted({row["typesafe_model"] for row in output_rows}),
            "scope_agreements_with_assistant": sum(
                row["typesafe_scope"] == row["assistant_scope"] for row in output_rows
            ),
            "high_priority_reviews": sum(row["typesafe_review_priority"] == "high" for row in output_rows),
            "input_tokens": sum(int(row["typesafe_input_tokens"] or 0) for row in output_rows),
            "output_tokens": sum(int(row["typesafe_output_tokens"] or 0) for row in output_rows),
        }
    )
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
