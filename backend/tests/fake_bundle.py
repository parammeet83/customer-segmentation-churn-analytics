"""Builds a small, structurally complete results bundle for DB/API tests.

Values are synthetic test fixtures, never shown as project results.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from customerpulse.features.pseudonymize import customer_key
from customerpulse.features.snapshots import FEATURE_DESCRIPTIONS, MODEL_FEATURES

SECRET = b"test-secret-0123456789"


def _metrics(rng, n=100):
    tp, fp, tn, fn = 30, 10, 50, 10
    return {
        "n": n,
        "positives": 40,
        "positive_rate": 0.4,
        "threshold": 0.5,
        "recall": 0.75,
        "precision": 0.75,
        "f1": 0.75,
        "f2": 0.75,
        "roc_auc": float(rng.uniform(0.6, 0.8)),
        "pr_auc": 0.7,
        "brier": 0.2,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "top_fraction": 0.1,
        "top_selected": 10,
        "top_precision": 0.8,
        "top_capture_rate": 0.2,
        "top_lift": 2.0,
    }


def make_bundle(root: Path, n_customers: int = 40, seed: int = 0, corrupt: bool = False) -> Path:
    rng = np.random.default_rng(seed)
    root.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.UUID(int=int(rng.integers(1, 2**63))))
    keys = sorted(customer_key(str(10000 + i), SECRET) for i in range(n_customers))
    clusters = [i % 3 for i in range(n_customers)]
    cutoff = pd.Timestamp("2011-12-10")

    assign = pd.DataFrame(
        {
            "customer_key": keys,
            "cluster_id": clusters,
            "pca_x": rng.normal(size=n_customers),
            "pca_y": rng.normal(size=n_customers),
            "recency_days": rng.uniform(1, 700, n_customers),
            "frequency": rng.integers(1, 30, n_customers),
            "monetary": rng.uniform(10, 9000, n_customers),
            "tenure_days": rng.uniform(1, 730, n_customers),
        }
    )
    scored = assign.iloc[: n_customers - 5]  # not every segmented customer is scored
    prob = np.sort(rng.uniform(0.05, 0.95, len(scored)))[::-1]
    scores = pd.DataFrame(
        {
            "customer_key": scored["customer_key"].to_numpy(),
            "cutoff": cutoff,
            "cluster_id": scored["cluster_id"].to_numpy(),
        }
    )
    for f in MODEL_FEATURES:
        scores[f] = rng.uniform(0, 10, len(scored))
    scores["frequency"] = rng.integers(1, 10, len(scored))
    scores["churn_probability"] = 1.5 if corrupt else prob
    scores["risk_rank"] = np.arange(1, len(scored) + 1)
    scores["risk_percentile"] = 1 - (scores["risk_rank"] - 1) / len(scored)
    k = int(np.ceil(len(scored) * 0.1))
    scores["in_top_decile"] = scores["risk_rank"] <= k
    scores["above_threshold"] = prob >= 0.5
    scores["risk_band"] = pd.cut(
        scores["risk_rank"] / len(scored),
        [0, 0.1, 0.3, 0.6, 1.0],
        labels=["Very high", "High", "Medium", "Low"],
        include_lowest=True,
    ).astype(str)
    scores["daily_revenue_rate"] = rng.uniform(0, 20, len(scored))
    scores["projected_revenue"] = scores["daily_revenue_rate"] * 90
    scores["projection_capped"] = False
    scores["expected_revenue_at_risk"] = scores["churn_probability"] * scores["projected_revenue"]
    top_keys = scores.loc[scores["in_top_decile"], "customer_key"].tolist()
    local = pd.DataFrame(
        [
            {
                "customer_key": key,
                "feature": f,
                "feature_value": 1.0,
                "shap_value": 0.5 - j * 0.2,
                "rank": j + 1,
                "explanation": f"{f} test",
            }
            for key in top_keys
            for j, f in enumerate(MODEL_FEATURES[:3])
        ]
    )
    assign.to_parquet(root / "segment_assignments.parquet", index=False)
    scores.to_parquet(root / "scores.parquet", index=False)
    local.to_parquet(root / "shap_local.parquet", index=False)

    names = ["Champions", "At Risk", "Hibernating Customers"]
    profiles = [
        {
            "cluster_id": c,
            "segment_name": names[c],
            "recommended_action": "test action",
            "levels": {"recency": "recent"},
            "customers": clusters.count(c),
            "share": clusters.count(c) / n_customers,
            "revenue": 100.0 * (3 - c),
            "revenue_share": (3 - c) / 6,
            "median": {"recency_days": 10.0, "frequency": 2.0, "monetary": 100.0, "tenure_days": 300.0},
            "mean": {"recency_days": 10.0, "frequency": 2.0, "monetary": 100.0, "tenure_days": 300.0},
            "quartiles": {"recency_days": [1.0, 2.0, 3.0]},
            "centroid": {"recency_days": 10.0, "frequency": 2.0, "monetary": 100.0},
        }
        for c in range(3)
    ]
    families = ["logistic_regression", "hist_gradient_boosting", "random_forest"]
    val = [{"family": f, "config_index": 0, "params": {"p": 1}, **_metrics(rng)} for f in families]
    split = {
        "train": ["2010-06-01"],
        "validation": ["2011-02-01", "2011-04-01"],
        "test": ["2011-07-01", "2011-09-01"],
        "purged": [],
        "horizon_days": 90,
    }
    curve = [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 1.0}]
    scen = {
        "assumptions": {
            "target_fraction": 0.1,
            "effectiveness": 0.1,
            "cost_per_contact": 3.0,
            "horizon_days": 90,
            "margin": 1.0,
            "ranking": "risk",
        },
        "targeted_customers": k,
        "expected_revenue_at_risk": 100.0,
        "net_impact": 1.0,
    }
    manifest = {
        "run_id": run_id,
        "created_at": "2026-10-30T10:00:00+00:00",
        "code_version": "test",
        "config": {
            "feature_version": "fv1",
            "churn": {"horizon_days": 90},
            "retention": {"scenarios": {"base": {"effectiveness": 0.1, "cost_per_contact": 3.0}}},
        },
        "dataset": {
            "source_name": "Online Retail II",
            "source_url": "https://archive.ics.uci.edu/x",
            "landing_page": "x",
            "doi": "https://doi.org/10.24432/C5CG6D",
            "licence": "CC BY 4.0",
            "citation": "Chen (2012)",
            "zip_sha256": "a" * 64,
            "xlsx_sha256": "b" * 64,
            "raw_rows": 1000,
            "date_min": "2009-12-01 07:45:00",
            "date_max": "2011-12-09 12:50:00",
            "sheets": {},
            "columns": [],
            "acquired_at": "x",
            "zip_checksum_matches_recorded": True,
        },
        "validation_report": {"status": "passed", "rows": 1000},
        "cleaning_report": {
            "profile": {"raw_rows": 1000},
            "exclusions": [{"reason": "missing_customer_id", "rows": 10, "share_of_raw": 0.01}],
            "output": {"purchase_lines": 900, "purchase_customers": n_customers},
            "monthly_purchase_value": [{"month": "2011-01-01", "value": 1.0}],
        },
        "features_meta": {"horizon_sensitivity": [{"horizon_days": 90, "mean_churn_rate": 0.5}]},
        "segmentation": {
            "customers": n_customers,
            "selected_k": 3,
            "silhouette": 0.4,
            "selection_rule": "test",
            "transform": "log1p",
            "population": "test",
            "pca_explained_variance": [0.6, 0.3],
            "population_quantiles": {},
            "k_table": [
                {
                    "k": kk,
                    "silhouette": 0.3,
                    "inertia": 1.0,
                    "min_cluster_share": 0.2,
                    "max_cluster_share": 0.4,
                    "stability_ari": 0.9,
                    "in_selectable_range": True,
                    "passes_guards": True,
                    "selected": kk == 3,
                }
                for kk in (2, 3, 4)
            ],
            "profiles": profiles,
        },
        "churn_report": {
            "definition": {"rule": "test", "horizon_days": 90},
            "split": split,
            "class_balance": [
                {"partition": p, "rows": 100, "customers": 50, "snapshots": 1, "churn_rate": 0.4}
                for p in ("train", "validation", "test")
            ],
            "selection_metric": "validation ROC-AUC",
            "threshold_rule": "recall",
            "threshold": 0.5,
            "selected_family": "logistic_regression",
            "selected_params": {"p": 1},
            "validation_results": val,
            "best_per_family": {v["family"]: v for v in val},
            "test_results": {
                f: {**_metrics(rng), "top_fraction_per_snapshot": {"capture_rate": 0.2, "lift": 2.0}} for f in families
            },
            "test_curves": {f: {"roc": curve, "pr": curve, "calibration": curve} for f in families},
            "test_per_snapshot": [],
            "test_top_fraction": {"capture_rate": 0.2, "lift": 2.0},
            "test_deciles": [],
            "seen_vs_unseen": [],
            "repeated_customers": {},
        },
        "score_meta": {"scoring_cutoff": "2011-12-10", "scored_customers": len(scored)},
        "shap_report": {
            "explainer": "LinearExplainer",
            "model_family": "logistic_regression",
            "output_space": "log_odds",
            "base_value": 0.0,
            "additivity_max_abs_error": 0.0,
            "background": {},
            "caveat": "associations",
            "global": [
                {
                    "feature": f,
                    "rank": i + 1,
                    "description": FEATURE_DESCRIPTIONS[f],
                    "mean_abs_shap": 1.0 / (i + 1),
                    "mean_shap": 0.0,
                    "value_shap_correlation": 0.5,
                    "direction": "higher values raise risk",
                }
                for i, f in enumerate(MODEL_FEATURES)
            ],
            "beeswarm": [],
        },
        "retention_report": {
            "currency": "GBP",
            "season_factor": {"factor": 1.0, "available": False},
            "projection": {},
            "cohort": {"customers": k, "expected_revenue_at_risk": 100.0, "all_scored_expected_revenue_at_risk": 500.0},
            "scenarios": {"base": scen},
            "value_ranked_base": {**scen, "assumptions": {**scen["assumptions"], "ranking": "value_at_risk"}},
            "disclaimer": "estimates",
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root
