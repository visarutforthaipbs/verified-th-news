#!/usr/bin/env python3
"""Controlled embedding benchmark for the Thai longitudinal BERTopic corpus.

This experiment is non-destructive: it freezes the audited corpus and clustering
parameters, writes into a new versioned run directory, and does not replace the
published September 8 outputs.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import time
from itertools import combinations
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/thverify-embedding-ab-mpl")

import hdbscan
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import umap
from hdbscan import HDBSCAN
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    adjusted_rand_score,
    average_precision_score,
    balanced_accuracy_score,
    normalized_mutual_info_score,
    roc_auc_score,
    silhouette_score,
)
from sklearn.model_selection import StratifiedGroupKFold


ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN = ROOT / "runs/20260908_bertopic_v001"
INPUT = ROOT / "data/reports/journalist_handoff_2026-09-08/02_false_misleading_altered_records.csv"
OUT = ROOT / "runs/20260914_embedding_ab_v001"
SEEDS = (42, 7, 21)
SIZES = (15, 30, 50, 80)
UMAP_ARGS = dict(n_neighbors=15, n_components=10, min_dist=0.0, metric="cosine")
HDBSCAN_ARGS = dict(min_cluster_size=30, min_samples=5, metric="euclidean", cluster_selection_method="eom")
ARMS = {
    "e5_passage": {
        "model": "intfloat/multilingual-e5-small",
        "revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
        "prefix": "passage: ",
        "reuse": SOURCE_RUN / "unique_embeddings.npy",
    },
    "e5_query": {
        "model": "intfloat/multilingual-e5-small",
        "revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3",
        "prefix": "query: ",
        "reuse": None,
    },
    "paraphrase_minilm": {
        "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
        "prefix": "",
        "reuse": None,
    },
}
STORY_TOPICS = (1, 2, 4, 7, 11, 28, 49)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode_arm(name: str, spec: dict, texts: list[str], device: str) -> tuple[np.ndarray, float, int]:
    path = OUT / f"{name}_embeddings.npy"
    meta_path = OUT / f"{name}_embedding_meta.json"
    if path.exists():
        meta = json.loads(meta_path.read_text())
        return np.load(path), float(meta["elapsed_seconds"]), int(meta["max_seq_length"])
    started = time.perf_counter()
    if spec["reuse"]:
        x = np.load(spec["reuse"]).astype("float32")
        max_length = 512
    else:
        model = SentenceTransformer(spec["model"], revision=spec["revision"], device=device)
        max_length = int(model.max_seq_length)
        payload = [spec["prefix"] + text for text in texts]
        x = model.encode(
            payload,
            batch_size=128 if device == "mps" else 64,
            show_progress_bar=True,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype("float32")
        del model
        if device == "mps":
            torch.mps.empty_cache()
    elapsed = time.perf_counter() - started
    if x.shape != (len(texts), 384) or not np.isfinite(x).all():
        raise RuntimeError(f"Unexpected embedding matrix for {name}: {x.shape}")
    if not np.allclose(np.linalg.norm(x, axis=1), 1, atol=1e-4):
        raise RuntimeError(f"Embeddings are not normalized for {name}")
    np.save(path, x)
    meta_path.write_text(json.dumps({"elapsed_seconds": elapsed, "max_seq_length": max_length}, indent=2))
    return x, elapsed, max_length


def truncation_metrics(model_id: str, revision: str, texts: list[str], max_length: int) -> dict[str, float]:
    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
    lengths = []
    for start in range(0, len(texts), 512):
        encoded = tokenizer(texts[start:start + 512], add_special_tokens=True, truncation=False,
                            return_attention_mask=False, return_token_type_ids=False)
        lengths.extend(map(len, encoded["input_ids"]))
    lengths = np.asarray(lengths)
    return {
        "texts_over_model_limit_pct": float((lengths > max_length).mean() * 100),
        "token_length_p95": float(np.percentile(lengths, 95)),
        "token_length_max": int(lengths.max()),
    }


def cluster(x: np.ndarray, seed: int, cache_name: str) -> tuple[np.ndarray, np.ndarray, float]:
    zpath, lpath = OUT / f"{cache_name}_umap10.npy", OUT / f"{cache_name}_labels.npy"
    if zpath.exists() and lpath.exists():
        return np.load(zpath), np.load(lpath), 0.0
    started = time.perf_counter()
    z = umap.UMAP(**UMAP_ARGS, random_state=seed).fit_transform(x)
    labels = HDBSCAN(**HDBSCAN_ARGS).fit_predict(z)
    elapsed = time.perf_counter() - started
    np.save(zpath, z)
    np.save(lpath, labels)
    return z, labels, elapsed


def centroid_compactness(x: np.ndarray, labels: np.ndarray) -> float:
    sims = []
    for label in sorted(set(labels) - {-1}):
        rows = x[labels == label]
        centre = rows.mean(axis=0)
        centre /= np.linalg.norm(centre)
        sims.extend(rows @ centre)
    return float(np.mean(sims)) if sims else float("nan")


def migrant_cv(x: np.ndarray, text_index: dict[str, int]) -> dict[str, float]:
    review = pd.read_csv(SOURCE_RUN / "migrant_scope_decisions.csv")
    review = review[review["assistant_scope"].notna()].copy()
    review["y"] = (review["assistant_scope"] != "out_of_scope").astype(int)
    # One row per exact text prevents repeated publisher records crossing folds.
    review = review.drop_duplicates("claim_text")
    idx = np.array([text_index[t] for t in review["claim_text"]])
    y = review["y"].to_numpy()
    groups = review["claim_text"].to_numpy()
    splitter = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
    prob = np.zeros(len(y)); pred = np.zeros(len(y), dtype=int)
    for train, test in splitter.split(x[idx], y, groups):
        clf = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)
        clf.fit(x[idx][train], y[train])
        prob[test] = clf.predict_proba(x[idx][test])[:, 1]
        pred[test] = clf.predict(x[idx][test])
    return {
        "migrant_cv_n": int(len(y)),
        "migrant_cv_roc_auc": float(roc_auc_score(y, prob)),
        "migrant_cv_average_precision": float(average_precision_score(y, prob)),
        "migrant_cv_balanced_accuracy": float(balanced_accuracy_score(y, pred)),
    }


def leakage_metrics(record_labels: np.ndarray, records: pd.DataFrame) -> dict[str, float]:
    ids = set(pd.read_csv(SOURCE_RUN / "residual_editorial_review.csv")["id"].astype(str))
    flagged = records["id"].astype(str).isin(ids).to_numpy()
    shares = []
    for label in set(record_labels) - {-1}:
        member = record_labels == label
        shares.append(flagged[member].mean())
    return {
        "editorial_flag_cluster_max_pct": float(max(shares, default=0) * 100),
        "editorial_flag_in_noise_pct": float((record_labels[flagged] == -1).mean() * 100),
    }


def story_continuity(name: str, labels: np.ndarray, published_topics: np.ndarray, record_index: np.ndarray) -> list[dict]:
    rows = []
    a, b = labels[record_index], published_topics
    for topic in STORY_TOPICS:
        truth = b == topic
        candidates = set(a[truth]) - {-1}
        best_label, best_jaccard = -1, 0.0
        for candidate in candidates:
            found = a == candidate
            jaccard = (truth & found).sum() / (truth | found).sum()
            if jaccard > best_jaccard:
                best_label, best_jaccard = int(candidate), float(jaccard)
        rows.append({"model": name, "baseline_topic": topic, "best_matching_topic": best_label,
                     "record_jaccard": best_jaccard})
    return rows


def plot_summary(summary: pd.DataFrame) -> None:
    labels = ["E5 passage\n(current)", "E5 query", "MiniLM"]
    colors = ["#8C96A3", "#235789", "#E09F3E"]
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.2))
    panels = [
        ("mean_seed_ari", "Stability across UMAP seeds", "Adjusted Rand index", (0, 1)),
        ("silhouette_original_embedding", "Separation in original embeddings", "Silhouette score", None),
        ("migrant_cv_roc_auc", "Migrant-scope screening (silver labels)", "5-fold ROC AUC", (0.5, 1)),
    ]
    for ax, (column, title, ylabel, ylim) in zip(axes, panels):
        values = summary[column].to_numpy()
        bars = ax.bar(labels, values, color=colors, width=0.68)
        ax.set_title(title, fontsize=11, pad=12)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.grid(axis="y", color="#D9DEE5", linewidth=.7)
        ax.set_axisbelow(True)
        if ylim: ax.set_ylim(*ylim)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, value, f"{value:.3f}", ha="center", va="bottom", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Thai BERTopic embedding benchmark — fixed corpus and clustering settings", fontsize=14, x=.02, ha="left")
    fig.text(.02, .01, "14,429 records / 13,377 unique texts. Silver labels are assistant-reviewed and are not human ground truth.", fontsize=8, color="#505A66")
    fig.tight_layout(rect=[0, .06, 1, .93])
    fig.savefig(OUT / "model_comparison.png", dpi=180, bbox_inches="tight")
    fig.savefig(OUT / "model_comparison.svg", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    records = pd.read_csv(INPUT, dtype={"id": str})
    texts = list(dict.fromkeys(records["claim_text"].astype(str)))
    text_index = {text: i for i, text in enumerate(texts)}
    record_index = np.array([text_index[text] for text in records["claim_text"].astype(str)])
    published = pd.read_csv(SOURCE_RUN / "assignments.csv", dtype={"id": str})
    if published["id"].tolist() != records["id"].tolist():
        raise RuntimeError("Published assignments no longer align with the frozen input")
    published_topics = published["topic_id"].to_numpy()
    source_config = json.loads((SOURCE_RUN / "config.json").read_text())
    if sha256(INPUT) != source_config["input_sha256"]:
        raise RuntimeError("Audited input changed; refusing to compare unlike corpora")
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    config = {
        "purpose": "controlled embedding-model benchmark; does not overwrite production outputs",
        "input": str(INPUT.relative_to(ROOT)), "input_sha256": sha256(INPUT),
        "records": len(records), "unique_exact_texts": len(texts),
        "arms": ARMS, "seeds": SEEDS, "umap": UMAP_ARGS, "hdbscan": HDBSCAN_ARGS,
        "min_cluster_size_sensitivity": SIZES, "device": device,
        "decision_rule": "prioritize seed stability and editorial usefulness; treat intrinsic scores and assistant-reviewed migrant labels as diagnostics, not ground truth",
        "limitations": ["no independently human-coded topic gold standard", "E5 passage arm reuses audited vectors", "2015 and 2026 are partial years"],
        "packages": {p: importlib.metadata.version(p) for p in ["sentence-transformers", "torch", "umap-learn", "hdbscan", "scikit-learn", "numpy", "pandas"]},
        "python": platform.python_version(),
    }
    # Paths are serialized separately because Path is not JSON serializable.
    config["arms"] = {k: {"model": v["model"], "revision": v["revision"], "prefix": v["prefix"], "reuse": str(v["reuse"].relative_to(ROOT)) if v["reuse"] else None} for k, v in ARMS.items()}
    (OUT / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2))

    summaries, sensitivity, stability, continuity = [], [], [], []
    baseline_labels = None
    all_labels = {}
    for name, spec in ARMS.items():
        print(f"\n=== {name}: embeddings ===", flush=True)
        x, encode_seconds, max_length = encode_arm(name, spec, texts, device)
        seed_labels, seed_times, z42 = {}, {}, None
        for seed in SEEDS:
            print(f"{name}: UMAP/HDBSCAN seed {seed}", flush=True)
            z, labels, elapsed = cluster(x, seed, f"{name}_seed{seed}")
            seed_labels[seed], seed_times[seed] = labels, elapsed
            if seed == 42: z42 = z
        all_labels[name] = seed_labels[42]
        if name == "e5_passage": baseline_labels = seed_labels[42]
        pair_aris = [adjusted_rand_score(seed_labels[a], seed_labels[b]) for a, b in combinations(SEEDS, 2)]
        for (a, b), ari in zip(combinations(SEEDS, 2), pair_aris):
            stability.append({"model": name, "seed_a": a, "seed_b": b, "adjusted_rand_index": ari})
        base = seed_labels[42]
        for size in SIZES:
            labels = HDBSCAN(**dict(HDBSCAN_ARGS, min_cluster_size=size)).fit_predict(z42)
            sensitivity.append({"model": name, "min_cluster_size": size,
                "clusters": len(set(labels) - {-1}), "noise_unique_pct": float((labels == -1).mean() * 100),
                "ari_vs_size30": float(adjusted_rand_score(base, labels))})
        record_labels = base[record_index]
        sample_size = min(3000, int((base != -1).sum()))
        intrinsic_silhouette = silhouette_score(x[base != -1], base[base != -1], metric="cosine", sample_size=sample_size, random_state=42)
        row = {
            "model": name, "model_id": spec["model"], "prefix": spec["prefix"] or "(none)",
            "max_sequence_length": max_length, "embedding_seconds": encode_seconds,
            "mean_cluster_seconds": float(np.mean(list(seed_times.values()))),
            "clusters_seed42": len(set(base) - {-1}), "noise_unique_pct_seed42": float((base == -1).mean() * 100),
            "noise_record_pct_seed42": float((record_labels == -1).mean() * 100),
            "mean_seed_ari": float(np.mean(pair_aris)), "min_seed_ari": float(np.min(pair_aris)),
            "silhouette_original_embedding": float(intrinsic_silhouette),
            "cosine_centroid_compactness": centroid_compactness(x, base),
            "source_topic_nmi": float(normalized_mutual_info_score(records["source"], record_labels)),
            **truncation_metrics(spec["model"], spec["revision"], texts, max_length),
            **migrant_cv(x, text_index), **leakage_metrics(record_labels, records),
        }
        summaries.append(row)

    if baseline_labels is None: raise RuntimeError("Missing baseline")
    for name, labels in all_labels.items():
        continuity.extend(story_continuity(name, labels, published_topics, record_index))
    summary = pd.DataFrame(summaries)
    summary.to_csv(OUT / "model_summary.csv", index=False)
    pd.DataFrame(stability).to_csv(OUT / "seed_stability.csv", index=False)
    pd.DataFrame(sensitivity).to_csv(OUT / "cluster_sensitivity.csv", index=False)
    pd.DataFrame(continuity).to_csv(OUT / "story_topic_continuity.csv", index=False)
    plot_summary(summary)
    print("\n", summary.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
