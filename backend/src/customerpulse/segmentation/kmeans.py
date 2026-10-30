"""RFM K-Means segmentation with silhouette-based K selection.

Transform: ``log1p`` on recency, frequency and monetary (all heavily right
skewed), then ``StandardScaler``. K is chosen among ``selectable_k`` values by
the highest silhouette score, subject to two guards: every cluster must hold
at least ``min_cluster_share`` of customers, and bootstrap stability (mean
adjusted Rand index) must reach ``min_stability_ari``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from customerpulse.config import SegmentationConfig
from customerpulse.features.rfm import RFM_COLUMNS


def make_transformer() -> Pipeline:
    return Pipeline(
        [
            ("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
            ("scale", StandardScaler()),
        ]
    )


def prepare_matrix(rfm: pd.DataFrame) -> tuple[np.ndarray, Pipeline]:
    X = rfm[list(RFM_COLUMNS)].to_numpy(dtype=float)
    if not np.isfinite(X).all() or (X < 0).any():
        raise ValueError("RFM matrix must be finite and non-negative")
    transformer = make_transformer()
    return transformer.fit_transform(X), transformer


def fit_kmeans(Z: np.ndarray, k: int, seed: int, n_init: int) -> KMeans:
    return KMeans(n_clusters=k, n_init=n_init, random_state=seed).fit(Z)


def canonical_labels(model: KMeans, Z: np.ndarray, rfm: pd.DataFrame) -> np.ndarray:
    """Relabel clusters 0..k-1 by descending median monetary value.

    K-Means label numbers are arbitrary; canonical ordering makes cluster IDs
    stable across runs and readable in reports.
    """
    raw = model.predict(Z)
    med = pd.Series(rfm["monetary"].to_numpy()).groupby(raw).median()
    order = med.sort_values(ascending=False).index.tolist()
    mapping = {old: new for new, old in enumerate(order)}
    return np.vectorize(mapping.get)(raw)


def bootstrap_stability(Z: np.ndarray, k: int, cfg: SegmentationConfig, seed: int) -> float:
    """Mean ARI between the full-data clustering and subsample refits."""
    ref = fit_kmeans(Z, k, seed, cfg.n_init).labels_
    rng = np.random.default_rng(seed)
    scores = []
    m = int(len(Z) * cfg.stability_sample_fraction)
    for _ in range(cfg.stability_bootstrap_rounds):
        idx = rng.choice(len(Z), size=m, replace=False)
        sub = KMeans(n_clusters=k, n_init=5, random_state=int(rng.integers(1_000_000))).fit(Z[idx])
        scores.append(adjusted_rand_score(ref, sub.predict(Z)))
    return float(np.mean(scores))


@dataclass
class SegmentationResult:
    k_table: list[dict]
    selected_k: int
    labels: np.ndarray
    model: KMeans
    transformer: Pipeline
    silhouette: float
    pca_coords: np.ndarray
    pca_explained_variance: list[float]
    silhouette_sample_size: int
    selection_rule: str = field(default="")


def evaluate_k(rfm: pd.DataFrame, cfg: SegmentationConfig, seed: int) -> tuple[list[dict], np.ndarray, Pipeline, int]:
    Z, transformer = prepare_matrix(rfm)
    n = len(Z)
    sample = min(cfg.silhouette_sample_size, n)
    rows = []
    for k in range(cfg.k_min, min(cfg.k_max, n - 1) + 1):
        model = fit_kmeans(Z, k, seed, cfg.n_init)
        labels = model.labels_
        sil = float(silhouette_score(Z, labels, sample_size=sample if sample < n else None, random_state=seed))
        shares = np.bincount(labels, minlength=k) / n
        stab = bootstrap_stability(Z, k, cfg, seed)
        selectable = cfg.selectable_k_min <= k <= cfg.selectable_k_max
        rows.append(
            {
                "k": k,
                "silhouette": round(sil, 5),
                "inertia": round(float(model.inertia_), 3),
                "min_cluster_share": round(float(shares.min()), 5),
                "max_cluster_share": round(float(shares.max()), 5),
                "stability_ari": round(stab, 5),
                "in_selectable_range": selectable,
                "passes_guards": bool(
                    selectable and shares.min() >= cfg.min_cluster_share and stab >= cfg.min_stability_ari
                ),
            }
        )
    return rows, Z, transformer, sample


def select_k(k_table: list[dict]) -> int:
    eligible = [r for r in k_table if r["passes_guards"]]
    if not eligible:
        raise ValueError("No K value satisfies the size and stability guards")
    return max(eligible, key=lambda r: (r["silhouette"], -r["k"]))["k"]


def segment(rfm: pd.DataFrame, cfg: SegmentationConfig, seed: int) -> SegmentationResult:
    k_table, Z, transformer, sample = evaluate_k(rfm, cfg, seed)
    k = select_k(k_table)
    for r in k_table:
        r["selected"] = r["k"] == k
    model = fit_kmeans(Z, k, seed, cfg.n_init)
    labels = canonical_labels(model, Z, rfm)
    pca = PCA(n_components=2, random_state=seed).fit(Z)
    return SegmentationResult(
        k_table=k_table,
        selected_k=k,
        labels=labels,
        model=model,
        transformer=transformer,
        silhouette=next(r["silhouette"] for r in k_table if r["k"] == k),
        pca_coords=pca.transform(Z),
        pca_explained_variance=[float(v) for v in pca.explained_variance_ratio_],
        silhouette_sample_size=sample,
        selection_rule=(
            f"Highest silhouette among K in [{cfg.selectable_k_min}, {cfg.selectable_k_max}] "
            f"with every cluster >= {cfg.min_cluster_share:.0%} of customers and bootstrap "
            f"stability ARI >= {cfg.min_stability_ari}"
        ),
    )
