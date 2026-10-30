"""SHAP explanations for the selected churn model.

The explainer works on the model's own input space (after imputation, log
transform and scaling for the linear model). Contributions of derived
columns such as missing-value indicators are summed back onto the original
feature, so every explanation refers to a business-readable feature.

Output space: log-odds for logistic regression and HistGradientBoosting,
probability for random forest (sklearn forests average leaf probabilities).
SHAP values describe how the model reached a score; they are associations,
not causal effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shap
from sklearn.pipeline import Pipeline

from customerpulse.features.snapshots import FEATURE_DESCRIPTIONS, MODEL_FEATURES

INDICATOR_PREFIX = "missingindicator_"


@dataclass
class ShapOutput:
    values: np.ndarray  # (n_rows, n_original_features)
    base_value: float
    features: list[str]
    explainer_type: str
    output_space: str = "log_odds"  # or "probability"

    def model_output(self, probabilities: np.ndarray) -> np.ndarray:
        """Convert probabilities into this explanation's output space."""
        p = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1 - 1e-12)
        return np.log(p / (1 - p)) if self.output_space == "log_odds" else p


def _split_pipeline(model: Pipeline) -> tuple[Pipeline | None, object]:
    steps = model.steps
    pre = Pipeline(steps[:-1]) if len(steps) > 1 else None
    return pre, steps[-1][1]


def _transformed_names(pre: Pipeline | None, features: list[str]) -> list[str]:
    if pre is None:
        return list(features)
    return [str(n) for n in pre.get_feature_names_out(features)]


def _aggregate_to_original(values: np.ndarray, names: list[str], features: list[str]) -> np.ndarray:
    out = np.zeros((values.shape[0], len(features)))
    index = {f: i for i, f in enumerate(features)}
    for j, name in enumerate(names):
        base = name.removeprefix(INDICATOR_PREFIX)
        if base not in index:
            raise KeyError(f"Cannot map transformed column {name!r} to an input feature")
        out[:, index[base]] += values[:, j]
    return out


def explain(
    model: Pipeline,
    background: pd.DataFrame,
    rows: pd.DataFrame,
    features: list[str] | None = None,
) -> ShapOutput:
    features = list(features or MODEL_FEATURES)
    missing = [f for f in features if f not in rows.columns]
    if missing:
        raise KeyError(f"Rows are missing model features: {missing}")
    pre, est = _split_pipeline(model)
    names = _transformed_names(pre, features)
    Xb = background[features] if pre is None else pre.transform(background[features])
    Xr = rows[features] if pre is None else pre.transform(rows[features])
    Xb, Xr = np.asarray(Xb, dtype=float), np.asarray(Xr, dtype=float)

    kind = type(est).__name__
    if kind == "LogisticRegression":
        explainer = shap.LinearExplainer(est, shap.maskers.Independent(Xb, max_samples=len(Xb)))
        sv = explainer(Xr)
        explainer_type = "LinearExplainer (independent masker)"
        space = "log_odds"
    elif kind in {"RandomForestClassifier", "HistGradientBoostingClassifier"}:
        # Path-dependent mode is exact for sklearn trees; the interventional
        # mode showed additivity errors (~0.2 log-odds) with binned HistGB splits.
        explainer = shap.TreeExplainer(est, feature_perturbation="tree_path_dependent")
        sv = explainer(Xr, check_additivity=False)
        explainer_type = "TreeExplainer (tree_path_dependent)"
        space = "probability" if kind == "RandomForestClassifier" else "log_odds"
    else:
        raise TypeError(f"No SHAP explainer configured for {kind}")

    vals = np.asarray(sv.values, dtype=float)
    base = np.asarray(sv.base_values, dtype=float)
    if vals.ndim == 3:  # (n, features, classes) -> positive class
        vals = vals[:, :, 1]
        base = base[:, 1] if base.ndim == 2 else base
    base_value = float(np.ravel(base)[0])
    return ShapOutput(
        values=_aggregate_to_original(vals, names, features),
        base_value=base_value,
        features=features,
        explainer_type=explainer_type,
        output_space=space,
    )


def global_importance(out: ShapOutput, rows: pd.DataFrame) -> list[dict]:
    """Mean |SHAP| ranking plus the direction of each feature's association."""
    res: list[dict[str, Any]] = []
    for j, f in enumerate(out.features):
        v = out.values[:, j]
        x = rows[f].to_numpy(dtype=float)
        ok = np.isfinite(x)
        corr = (
            float(np.corrcoef(x[ok], v[ok])[0, 1]) if ok.sum() > 2 and np.std(x[ok]) > 0 and np.std(v[ok]) > 0 else 0.0
        )
        res.append(
            {
                "feature": f,
                "description": FEATURE_DESCRIPTIONS.get(f, f),
                "mean_abs_shap": float(np.mean(np.abs(v))),
                "mean_shap": float(np.mean(v)),
                "value_shap_correlation": corr,
                "direction": (
                    "higher values raise risk"
                    if corr > 0.1
                    else "higher values lower risk"
                    if corr < -0.1
                    else "mixed / non-monotonic"
                ),
            }
        )
    res.sort(key=lambda r: r["mean_abs_shap"], reverse=True)
    for i, r in enumerate(res, start=1):
        r["rank"] = i
    return res


def beeswarm_points(
    out: ShapOutput, rows: pd.DataFrame, top_features: list[str], max_points: int, seed: int
) -> list[dict]:
    """Deterministic sample of (shap, feature-value percentile) per feature."""
    rng = np.random.default_rng(seed)
    n = len(rows)
    idx = np.sort(rng.choice(n, size=min(max_points, n), replace=False))
    pts = []
    for f in top_features:
        j = out.features.index(f)
        col = rows[f].astype(float)
        pct = col.rank(pct=True).to_numpy()
        for i in idx:
            pts.append(
                {
                    "feature": f,
                    "shap": round(float(out.values[i, j]), 5),
                    "value_percentile": None if np.isnan(pct[i]) else round(float(pct[i]), 4),
                }
            )
    return pts


def describe_contribution(feature: str, value: float, shap_value: float) -> str:
    """Plain-language sentence for one feature's contribution."""
    desc = FEATURE_DESCRIPTIONS.get(feature, feature).rstrip(".")
    if value is None or (isinstance(value, float) and np.isnan(value)):
        shown = "not available"
    else:
        shown = f"{value:,.2f}".rstrip("0").rstrip(".")
    effect = "raised" if shap_value > 0 else "lowered"
    return f"{desc} = {shown}; this {effect} the predicted inactivity risk."


def local_explanations(out: ShapOutput, rows: pd.DataFrame, keys: list[str], top_n: int = 6) -> list[dict]:
    """Top positive and negative contributions per row."""
    records = []
    for i, key in enumerate(keys):
        v = out.values[i]
        order = np.argsort(-np.abs(v))[:top_n]
        for rank, j in enumerate(order, start=1):
            f = out.features[j]
            x = rows.iloc[i][f]
            xv = None if pd.isna(x) else float(x)
            records.append(
                {
                    "customer_key": key,
                    "feature": f,
                    "feature_value": xv,
                    "shap_value": float(v[j]),
                    "rank": rank,
                    "explanation": describe_contribution(f, xv if xv is not None else float("nan"), float(v[j])),
                }
            )
    return records
