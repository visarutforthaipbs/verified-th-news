"""Semantic claim search: "has this claim been fact-checked before?"

Builds a dense-vector index over the deduplicated, leak-stripped corpus
produced by scripts/build_dataset.py (data/exports/rag_corpus.jsonl) and
answers nearest-neighbour queries with cosine similarity.

At ~27k documents a brute-force numpy dot product answers in ~1 ms, so no
ANN library is needed. Vectors are L2-normalized at build time.

Usage:
    th-verify index                 # embed corpus -> data/index/
    POST /check {"text": "..."}    # query via the API
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

DEFAULT_MODEL = os.getenv("TH_VERIFY_EMBED_MODEL", "intfloat/multilingual-e5-small")
DEFAULT_INDEX_DIR = Path(os.getenv("TH_VERIFY_INDEX_DIR", "data/index"))
DEFAULT_CORPUS = Path("data/exports/rag_corpus.jsonl")

# e5 models are trained with these prefixes; retrieval quality drops without them
_QUERY_PREFIX = "query: "
_PASSAGE_PREFIX = "passage: "

_SNIPPET_CHARS = 600


def build_index(
    corpus_path: Path = DEFAULT_CORPUS,
    index_dir: Path = DEFAULT_INDEX_DIR,
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 256,
) -> dict:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    if not corpus_path.exists():
        raise FileNotFoundError(
            f"{corpus_path} not found - run scripts/build_dataset.py first"
        )

    docs: list[dict] = []
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            claim = r["claim_text"].strip()
            if len(claim) < 10:
                continue
            docs.append({
                "id": r["id"],
                "source": r["source"],
                "url": r["url"],
                "claim_text": claim,
                "label": r["label"],
                "published_at": r["published_at"],
                "explanation_snippet": r["explanation"][:_SNIPPET_CHARS],
            })

    model = SentenceTransformer(model_name)
    vectors = model.encode(
        [_PASSAGE_PREFIX + d["claim_text"] for d in docs],
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    ).astype(np.float32)

    index_dir.mkdir(parents=True, exist_ok=True)
    np.save(index_dir / "embeddings.npy", vectors)
    with open(index_dir / "meta.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    (index_dir / "config.json").write_text(json.dumps({
        "model": model_name,
        "documents": len(docs),
        "dimensions": int(vectors.shape[1]),
    }))
    return {"documents": len(docs), "dimensions": int(vectors.shape[1]),
            "model": model_name, "index_dir": str(index_dir)}


class ClaimSearcher:
    """Loads the index once and serves queries; safe for concurrent use."""

    def __init__(self, index_dir: Path = DEFAULT_INDEX_DIR):
        import numpy as np
        from sentence_transformers import SentenceTransformer

        config = json.loads((index_dir / "config.json").read_text())
        self.vectors = np.load(index_dir / "embeddings.npy")
        with open(index_dir / "meta.jsonl", encoding="utf-8") as f:
            self.meta = [json.loads(line) for line in f]
        self.model = SentenceTransformer(config["model"])
        self._np = np

    def search(self, text: str, top_k: int = 5, hybrid: bool = True, db_path: Path | str | None = None) -> list[dict]:
        np = self._np
        q = self.model.encode([_QUERY_PREFIX + text.strip()],
                              normalize_embeddings=True).astype(np.float32)[0]
        scores = self.vectors @ q
        k_dense = min(30, len(scores))
        top_dense_idx = np.argpartition(scores, -k_dense)[-k_dense:]
        top_dense_idx = top_dense_idx[np.argsort(scores[top_dense_idx])[::-1]]

        dense_results = [{**self.meta[i], "score": float(scores[i])} for i in top_dense_idx]

        if not hybrid:
            return [{**d, "score": round(d["score"], 4)} for d in dense_results[:top_k]]

        # FTS BM25 Keyword Search
        from .config import Settings
        from .db import Repository
        target_db = Path(db_path) if db_path else Settings.from_env().database_path
        repo = Repository(target_db)
        fts_results = repo.search_fts(text, limit=30)

        # Reciprocal Rank Fusion (RRF)
        rrf_scores: dict[int, float] = {}
        item_map: dict[int, dict] = {}
        match_types: dict[int, str] = {}

        for rank, d in enumerate(dense_results, start=1):
            doc_id = d["id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (60.0 + rank))
            item_map[doc_id] = d
            match_types[doc_id] = "dense"

        for rank, fts_item in enumerate(fts_results, start=1):
            doc_id = fts_item["id"]
            if doc_id in match_types:
                match_types[doc_id] = "hybrid"
            else:
                match_types[doc_id] = "keyword"
                item_map[doc_id] = {
                    "id": fts_item["id"],
                    "source": fts_item["source"],
                    "url": fts_item["url"],
                    "claim_text": fts_item["claim_text"] or fts_item["title"],
                    "label": fts_item["label"],
                    "published_at": fts_item["published_at"],
                    "explanation_snippet": (fts_item["explanation_snippet"] or "")[:600],
                    "score": 0.85,
                }
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + (1.0 / (60.0 + rank))

        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:top_k]

        final_results = []
        for doc_id in sorted_ids:
            item = dict(item_map[doc_id])
            item["score"] = round(item.get("score", 0.85), 4)
            item["match_type"] = match_types[doc_id]
            final_results.append(item)

        return final_results



_searcher: ClaimSearcher | None = None
_lock = threading.Lock()


def get_searcher(index_dir: Path = DEFAULT_INDEX_DIR) -> ClaimSearcher:
    global _searcher
    if _searcher is None:
        with _lock:
            if _searcher is None:
                _searcher = ClaimSearcher(index_dir)
    return _searcher
