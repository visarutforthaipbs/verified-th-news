"""Score the semantic index against the frozen retrieval benchmark.

The benchmark (data/eval/retrieval_benchmark.jsonl) is 50 hand-written
natural-Thai queries — phrased the way people actually type into LINE or a
search box — each mapped to the fact-check record it should retrieve.

Run after any change to the embedding model, index build, or claim cleaning:

    python scripts/eval_retrieval.py

Metrics:
  hit@1 / hit@5  expected record retrieved at rank 1 / within top 5
  MRR            mean reciprocal rank of the expected record (top 10)

Notes:
- Strict ID matching. Some topics (e.g. loan scams) have many near-duplicate
  records, so a "miss" can still be a useful match for the end user; treat
  hit@5 as the primary product metric and hit@1 as the stretch metric.
- Never edit the benchmark to make a change look better. Add queries with a
  new file version instead (retrieval_benchmark_v2.jsonl) and report both.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from th_verify.search import get_searcher  # noqa: E402

BENCH = Path("data/eval/retrieval_benchmark.jsonl")


def main() -> None:
    cases = [json.loads(line) for line in BENCH.open(encoding="utf-8")]
    searcher = get_searcher()

    hits1 = hits5 = 0
    mrr = 0.0
    by_topic: defaultdict[str, list[int]] = defaultdict(list)
    misses: list[tuple[dict, list[dict]]] = []

    for case in cases:
        results = searcher.search(case["query"], top_k=10)
        rank = next((i + 1 for i, r in enumerate(results)
                     if r["id"] == case["expected_id"]), 0)
        if rank == 1:
            hits1 += 1
        if 1 <= rank <= 5:
            hits5 += 1
        if rank:
            mrr += 1.0 / rank
        by_topic[case["topic"]].append(rank)
        if not (1 <= rank <= 5):
            misses.append((case, results[:2]))

    n = len(cases)
    print(f"benchmark: {n} queries")
    print(f"hit@1 = {hits1}/{n} ({hits1 / n:.0%})")
    print(f"hit@5 = {hits5}/{n} ({hits5 / n:.0%})   <- primary metric")
    print(f"MRR   = {mrr / n:.3f}")
    print("\nby topic (hit@5):")
    for topic, ranks in sorted(by_topic.items()):
        ok = sum(1 for r in ranks if 1 <= r <= 5)
        print(f"  {topic:10} {ok}/{len(ranks)}")
    if misses:
        print("\nmisses (expected not in top 5):")
        for case, top in misses:
            print(f"  Q: {case['query'][:70]}")
            for r in top:
                print(f"     got {r['score']:.3f} id={r['id']} {r['claim_text'][:60]}")


if __name__ == "__main__":
    main()
