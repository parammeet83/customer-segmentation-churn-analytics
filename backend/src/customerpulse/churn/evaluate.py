"""Evaluation metrics for churn classifiers, including top-fraction targeting."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    fbeta_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)


def rank_order(scores: np.ndarray, keys: np.ndarray | None = None) -> np.ndarray:
    """Indices sorted by descending score; ties broken by ascending key.

    Deterministic tie handling means a top-k cut is always reproducible.
    """
    scores = np.asarray(scores, dtype=float)
    if keys is None:
        keys = np.arange(len(scores))
    return np.lexsort((np.asarray(keys), -scores))


def top_k_count(n: int, fraction: float) -> int:
    """Number selected for a fraction of n: ceil, at least 1 when n > 0."""
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    return 0 if n == 0 else max(1, math.ceil(n * fraction))


def top_fraction_metrics(
    y_true: np.ndarray, scores: np.ndarray, fraction: float = 0.10, keys: np.ndarray | None = None
) -> dict:
    y = np.asarray(y_true).astype(int)
    k = top_k_count(len(y), fraction)
    idx = rank_order(scores, keys)[:k]
    tp = int(y[idx].sum())
    positives = int(y.sum())
    base = positives / len(y) if len(y) else float("nan")
    precision = tp / k if k else float("nan")
    return {
        "fraction": fraction,
        "selected": k,
        "selected_share": k / len(y) if len(y) else float("nan"),
        "precision": precision,
        "capture_rate": tp / positives if positives else float("nan"),
        "lift": precision / base if base else float("nan"),
        "base_rate": base,
    }


def threshold_by_fbeta(y_true: np.ndarray, scores: np.ndarray, beta: float = 2.0) -> float:
    """Threshold maximising F-beta on the given (validation) data."""
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    p, r = precision[:-1], recall[:-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        f = (1 + beta**2) * p * r / (beta**2 * p + r)
    f = np.nan_to_num(f)
    return float(thresholds[int(np.argmax(f))])


def threshold_for_recall(y_true: np.ndarray, scores: np.ndarray, target_recall: float) -> float:
    """Highest threshold whose recall on the given (validation) data >= target."""
    if not 0 < target_recall <= 1:
        raise ValueError("target_recall must be in (0, 1]")
    _, recall, thresholds = precision_recall_curve(y_true, scores)
    ok = np.flatnonzero(recall[:-1] >= target_recall)
    return float(thresholds[ok.max()]) if len(ok) else float(thresholds.min())


def classification_metrics(y_true: np.ndarray, scores: np.ndarray, threshold: float, fraction: float = 0.10) -> dict:
    y = np.asarray(y_true).astype(int)
    pred = (np.asarray(scores) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    top = top_fraction_metrics(y, scores, fraction)
    return {
        "n": int(len(y)),
        "positives": int(y.sum()),
        "positive_rate": float(y.mean()),
        "threshold": float(threshold),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "f2": float(fbeta_score(y, pred, beta=2, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, scores)),
        "pr_auc": float(average_precision_score(y, scores)),
        "brier": float(brier_score_loss(y, scores)),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "top_fraction": top["fraction"],
        "top_selected": top["selected"],
        "top_precision": top["precision"],
        "top_capture_rate": top["capture_rate"],
        "top_lift": top["lift"],
    }


def _downsample(xs: np.ndarray, ys: np.ndarray, max_points: int = 120) -> list[dict]:
    if len(xs) > max_points:
        idx = np.unique(np.linspace(0, len(xs) - 1, max_points).round().astype(int))
        xs, ys = xs[idx], ys[idx]
    return [{"x": round(float(a), 5), "y": round(float(b), 5)} for a, b in zip(xs, ys, strict=True)]


def curves(y_true: np.ndarray, scores: np.ndarray) -> dict[str, list[dict]]:
    fpr, tpr, _ = roc_curve(y_true, scores)
    precision, recall, _ = precision_recall_curve(y_true, scores)
    order = np.argsort(recall)
    prob_true, prob_pred = calibration_curve(y_true, scores, n_bins=10, strategy="quantile")
    return {
        "roc": _downsample(fpr, tpr),
        "pr": _downsample(recall[order], precision[order]),
        "calibration": _downsample(prob_pred, prob_true),
    }


def decile_table(frame: pd.DataFrame, group_col: str = "cutoff") -> list[dict]:
    """Observed churn by predicted-risk decile, ranked within each group."""
    parts = []
    for _, g in frame.groupby(group_col, sort=True):
        order = rank_order(g["score"].to_numpy(), g["customer_id"].to_numpy())
        pos = np.empty(len(g), dtype=int)
        pos[order] = np.arange(len(g))
        parts.append(
            pd.DataFrame(
                {"decile": pos * 10 // len(g) + 1, "churned": g["churned"].to_numpy(), "score": g["score"].to_numpy()}
            )
        )
    d = pd.concat(parts)
    agg = d.groupby("decile").agg(n=("churned", "size"), churners=("churned", "sum"), mean_score=("score", "mean"))
    agg["churn_rate"] = agg["churners"] / agg["n"]
    return [
        {
            "decile": int(k),
            "n": int(r.n),
            "churners": int(r.churners),
            "churn_rate": float(r.churn_rate),
            "mean_score": float(r.mean_score),
        }
        for k, r in agg.iterrows()
    ]


def per_group_metrics(frame: pd.DataFrame, group_col: str, threshold: float, fraction: float = 0.10) -> list[dict]:
    """Metrics per group (e.g. per snapshot) for variability reporting."""
    out = []
    for key, g in frame.groupby(group_col, sort=True):
        if g["churned"].nunique() < 2:
            continue
        m = classification_metrics(g["churned"].to_numpy(), g["score"].to_numpy(), threshold, fraction)
        m[group_col] = str(key.date()) if isinstance(key, pd.Timestamp) else str(key)
        out.append(m)
    return out
