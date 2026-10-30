"""Candidate churn classifiers, validation-based selection and test evaluation.

Protocol (enforced by the code order in :func:`run_churn_experiment`):

1. Fit every candidate configuration on the training partition only. All
   preprocessing lives inside the sklearn Pipeline, so imputers and scalers
   never see validation or test rows.
2. Pick the best configuration per model family, then the final model, using
   validation ROC-AUC only. Choose the operating threshold on validation
   (highest threshold reaching the target recall).
3. Freeze the selection, then score the test partition once.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from customerpulse.churn.evaluate import (
    classification_metrics,
    curves,
    per_group_metrics,
    rank_order,
    threshold_for_recall,
    top_k_count,
)
from customerpulse.churn.splits import TemporalSplit
from customerpulse.features.snapshots import MODEL_FEATURES

logger = logging.getLogger(__name__)

# Families in order of simplicity; used as a tie-breaker.
FAMILY_ORDER = ("logistic_regression", "hist_gradient_boosting", "random_forest")
TIE_TOLERANCE = 0.002


def signed_log1p(x: np.ndarray) -> np.ndarray:
    return np.sign(x) * np.log1p(np.abs(x))


def make_model(family: str, params: dict[str, Any], seed: int) -> Pipeline:
    if family == "logistic_regression":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("log", FunctionTransformer(signed_log1p, feature_names_out="one-to-one")),
                ("scale", StandardScaler()),
                (
                    "model",
                    LogisticRegression(C=params["C"], class_weight="balanced", max_iter=5000, random_state=seed),
                ),
            ]
        )
    if family == "random_forest":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=300,
                        min_samples_leaf=params["min_samples_leaf"],
                        max_features=params["max_features"],
                        class_weight="balanced_subsample",
                        n_jobs=-1,
                        random_state=seed,
                    ),
                ),
            ]
        )
    if family == "hist_gradient_boosting":
        # Native NaN handling; early stopping is disabled because its internal
        # random hold-out would mix snapshots across time.
        return Pipeline(
            [
                (
                    "model",
                    HistGradientBoostingClassifier(
                        learning_rate=params["learning_rate"],
                        max_leaf_nodes=params["max_leaf_nodes"],
                        max_iter=params["max_iter"],
                        l2_regularization=1.0,
                        min_samples_leaf=40,
                        class_weight="balanced",
                        early_stopping=False,
                        random_state=seed,
                    ),
                )
            ]
        )
    raise ValueError(f"Unknown model family {family!r}")


PARAM_GRID: dict[str, dict[str, list]] = {
    "logistic_regression": {"C": [0.01, 0.1, 1.0]},
    "random_forest": {"min_samples_leaf": [10, 40], "max_features": ["sqrt", 0.5]},
    "hist_gradient_boosting": {
        "learning_rate": [0.03, 0.1],
        "max_leaf_nodes": [15, 31],
        "max_iter": [200],
    },
}


def iter_configs(family: str) -> list[dict]:
    grid = PARAM_GRID[family]
    keys = sorted(grid)
    return [dict(zip(keys, vals, strict=True)) for vals in itertools.product(*(grid[k] for k in keys))]


@dataclass
class ChurnExperiment:
    split: TemporalSplit
    validation_results: list[dict]
    best_per_family: dict[str, dict]
    selected_family: str
    selected_params: dict
    threshold: float
    test_results: dict[str, dict]
    test_curves: dict[str, dict]
    test_per_snapshot: list[dict]
    test_top_fraction_by_snapshot: dict
    seen_vs_unseen: list[dict]
    class_balance: list[dict]
    models: dict[str, Pipeline] = field(repr=False, default_factory=dict)
    test_frame: pd.DataFrame | None = field(repr=False, default=None)

    @property
    def selected_model(self) -> Pipeline:
        return self.models[self.selected_family]


def top_fraction_per_snapshot(frame: pd.DataFrame, fraction: float) -> dict:
    """Select the top fraction within each snapshot, then pool the counts.

    This mirrors operational use: each month the business contacts its own
    highest-risk 10%.
    """
    selected = tp = positives = n = 0
    for _, g in frame.groupby("cutoff", sort=True):
        k = top_k_count(len(g), fraction)
        idx = rank_order(g["score"].to_numpy(), g["customer_id"].to_numpy())[:k]
        y = g["churned"].to_numpy()
        selected += k
        tp += int(y[idx].sum())
        positives += int(y.sum())
        n += len(g)
    precision = tp / selected
    base = positives / n
    return {
        "fraction": fraction,
        "selected": selected,
        "population": n,
        "selected_share": selected / n,
        "true_churners_selected": tp,
        "precision": precision,
        "capture_rate": tp / positives,
        "lift": precision / base,
        "base_rate": base,
    }


def run_churn_experiment(
    snapshots: pd.DataFrame,
    split: TemporalSplit,
    seed: int,
    target_recall: float = 0.75,
    fraction: float = 0.10,
) -> ChurnExperiment:
    features = list(MODEL_FEATURES)
    part = snapshots["cutoff"].map(split.partition_of)
    train = snapshots[part == "train"]
    val = snapshots[part == "validation"]
    test = snapshots[part == "test"]
    X_tr, y_tr = train[features], train["churned"].to_numpy()
    X_va, y_va = val[features], val["churned"].to_numpy()

    class_balance = [
        {
            "partition": name,
            "rows": int(len(d)),
            "customers": int(d["customer_id"].nunique()),
            "snapshots": int(d["cutoff"].nunique()),
            "churn_rate": float(d["churned"].mean()),
            "first_cutoff": str(d["cutoff"].min().date()),
            "last_cutoff": str(d["cutoff"].max().date()),
        }
        for name, d in (("train", train), ("validation", val), ("test", test))
    ]

    # --- Steps 1-2: fit on train, select on validation ---------------------
    validation_results: list[dict] = []
    fitted: dict[tuple[str, int], Pipeline] = {}
    for family in FAMILY_ORDER:
        for i, params in enumerate(iter_configs(family)):
            model = make_model(family, params, seed)
            model.fit(X_tr, y_tr)
            scores = model.predict_proba(X_va)[:, 1]
            thr = threshold_for_recall(y_va, scores, target_recall)
            m = classification_metrics(y_va, scores, thr, fraction)
            validation_results.append({"family": family, "config_index": i, "params": params, **m})
            fitted[(family, i)] = model
            logger.info("val %s %s roc_auc=%.4f", family, params, m["roc_auc"])

    best_per_family: dict[str, dict] = {}
    for family in FAMILY_ORDER:
        rows = [r for r in validation_results if r["family"] == family]
        best_per_family[family] = max(rows, key=lambda r: r["roc_auc"])

    top_auc = max(r["roc_auc"] for r in best_per_family.values())
    selected_family = next(f for f in FAMILY_ORDER if best_per_family[f]["roc_auc"] >= top_auc - TIE_TOLERANCE)
    selected = best_per_family[selected_family]
    models = {f: fitted[(f, best_per_family[f]["config_index"])] for f in FAMILY_ORDER}
    thresholds = {f: best_per_family[f]["threshold"] for f in FAMILY_ORDER}
    logger.info("Selected %s on validation (roc_auc=%.4f)", selected_family, selected["roc_auc"])

    # --- Step 3: single evaluation on held-out future snapshots -------------
    X_te, y_te = test[features], test["churned"].to_numpy()
    test_results, test_curves = {}, {}
    test_frame = test[["customer_id", "cutoff", "churned"]].copy()
    for family, model in models.items():
        scores = model.predict_proba(X_te)[:, 1]
        test_results[family] = classification_metrics(y_te, scores, thresholds[family], fraction)
        test_curves[family] = curves(y_te, scores)
        frame = test_frame.assign(score=scores)
        test_results[family]["top_fraction_per_snapshot"] = top_fraction_per_snapshot(frame, fraction)
        if family == selected_family:
            test_frame = frame

    sel_thr = thresholds[selected_family]
    per_snapshot = per_group_metrics(test_frame, "cutoff", sel_thr, fraction)

    seen_customers = set(train["customer_id"]) | set(val["customer_id"])
    seen_mask = test_frame["customer_id"].isin(seen_customers)
    seen_vs_unseen = []
    for name, mask in (("seen_in_train_or_validation", seen_mask), ("unseen_customers", ~seen_mask)):
        g = test_frame[mask]
        if len(g) and g["churned"].nunique() == 2:
            m = classification_metrics(g["churned"].to_numpy(), g["score"].to_numpy(), sel_thr, fraction)
            seen_vs_unseen.append({"group": name, **m})

    return ChurnExperiment(
        split=split,
        validation_results=validation_results,
        best_per_family=best_per_family,
        selected_family=selected_family,
        selected_params=selected["params"],
        threshold=sel_thr,
        test_results=test_results,
        test_curves=test_curves,
        test_per_snapshot=per_snapshot,
        test_top_fraction_by_snapshot=test_results[selected_family]["top_fraction_per_snapshot"],
        seen_vs_unseen=seen_vs_unseen,
        class_balance=class_balance,
        models=models,
        test_frame=test_frame,
    )
