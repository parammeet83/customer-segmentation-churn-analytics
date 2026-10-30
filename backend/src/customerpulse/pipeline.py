"""End-to-end CustomerPulse analysis pipeline.

Acquire -> Validate -> Clean -> Temporal features -> Churn labels ->
Chronological split -> RFM -> K-Means -> Train/select classifiers ->
Evaluate on test -> SHAP -> Score customers -> Retention scenarios ->
Write results bundle (persisted to PostgreSQL by ``customerpulse persist``).

Each stage reads its inputs from disk and writes its outputs to disk, so
stages can be re-run individually. Raw customer IDs exist only in the local
``data/`` directory; the results bundle in ``artifacts/`` uses pseudonymous
keys only.
"""

from __future__ import annotations

import json
import logging
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from customerpulse.analytics import figures
from customerpulse.analytics.retention import (
    ScenarioAssumptions,
    project_revenue,
    seasonal_factor,
    simulate,
)
from customerpulse.churn.evaluate import decile_table, rank_order, top_k_count
from customerpulse.churn.models import FAMILY_ORDER, run_churn_experiment
from customerpulse.churn.splits import temporal_split
from customerpulse.cleaning.clean import clean
from customerpulse.config import (
    ARTIFACTS_DIR,
    DEFAULT_CONFIG,
    INTERIM_DIR,
    PROCESSED_DIR,
    REPORTS_DIR,
    PipelineConfig,
)
from customerpulse.explainability.shap_explain import (
    beeswarm_points,
    explain,
    global_importance,
    local_explanations,
)
from customerpulse.features import snapshots as snap
from customerpulse.features.pseudonymize import add_customer_keys, get_secret
from customerpulse.features.rfm import customer_rfm
from customerpulse.ingestion.acquire import acquire, load_raw
from customerpulse.ingestion.validate import validate_raw
from customerpulse.segmentation.kmeans import segment
from customerpulse.segmentation.naming import name_clusters

logger = logging.getLogger(__name__)
BUNDLE_DIR = ARTIFACTS_DIR / "latest"


def _json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_default))


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    if isinstance(o, np.bool_):
        return bool(o)
    raise TypeError(type(o))


def _read_json(path: Path):
    return json.loads(path.read_text())


def git_sha() -> str | None:
    try:
        return subprocess.run(  # noqa: S603 - fixed argv, metadata only
            ["git", "rev-parse", "HEAD"],  # noqa: S607 - git resolved from PATH by design
            capture_output=True,
            text=True,
            check=True,
            timeout=10,  # noqa: S607
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - metadata only
        return None


# --------------------------------------------------------------------------- stages


def stage_acquire(cfg: PipelineConfig = DEFAULT_CONFIG, local_archive: Path | None = None) -> dict:
    return acquire(cfg.dataset, local_archive=local_archive)


def stage_validate() -> dict:
    report = validate_raw(load_raw())
    _json(PROCESSED_DIR / "validation_report.json", report)
    return report


def stage_clean() -> dict:
    result = clean(load_raw())
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    result.purchases.to_parquet(PROCESSED_DIR / "purchases.parquet", index=False)
    result.returns.to_parquet(PROCESSED_DIR / "returns.parquet", index=False)
    _json(PROCESSED_DIR / "cleaning_report.json", result.report)
    return result.report


def _load_clean() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.read_parquet(PROCESSED_DIR / "purchases.parquet"),
        pd.read_parquet(PROCESSED_DIR / "returns.parquet"),
    )


def stage_features(cfg: PipelineConfig = DEFAULT_CONFIG) -> dict:
    purchases, returns = _load_clean()
    c = cfg.churn
    data_end = snap.data_end_of(purchases)
    cutoffs = snap.snapshot_cutoffs(c.first_snapshot, data_end, c.horizon_days)
    training = snap.build_training_snapshots(purchases, returns, cutoffs, c.lookback_days, c.horizon_days)
    training.to_parquet(PROCESSED_DIR / "training_snapshots.parquet", index=False)

    invoices = snap.invoice_table(purchases)
    scoring = snap.build_features(purchases, returns, data_end, c.lookback_days, invoices)
    scoring.to_parquet(PROCESSED_DIR / "scoring_features.parquet", index=False)
    customer_rfm(invoices, data_end).to_parquet(PROCESSED_DIR / "customer_rfm.parquet", index=False)

    sensitivity = snap.horizon_sensitivity(purchases, returns, c.first_snapshot, c.lookback_days, c.candidate_horizons)
    gaps = training["mean_gap_days"].dropna()
    meta = {
        "data_end_exclusive": str(data_end),
        "scoring_cutoff": str(data_end.date()),
        "training_cutoffs": [str(x.date()) for x in cutoffs],
        "training_rows": int(len(training)),
        "scoring_customers": int(len(scoring)),
        "horizon_sensitivity": sensitivity,
        "interpurchase_gap_quantiles": {str(q): float(gaps.quantile(q)) for q in (0.5, 0.75, 0.9)},
        "single_purchase_day_share": float(training["mean_gap_days"].isna().mean()),
    }
    _json(PROCESSED_DIR / "features_meta.json", meta)
    return meta


def stage_segment(cfg: PipelineConfig = DEFAULT_CONFIG) -> dict:
    secret = get_secret()
    rfm = add_customer_keys(pd.read_parquet(PROCESSED_DIR / "customer_rfm.parquet"), secret)
    res = segment(rfm, cfg.segmentation, cfg.random_seed)
    rfm["cluster_id"] = res.labels
    rfm["pca_x"], rfm["pca_y"] = res.pca_coords[:, 0], res.pca_coords[:, 1]

    cols = ["recency_days", "frequency", "monetary", "tenure_days"]
    med = rfm.groupby("cluster_id")[cols].median()
    named = name_clusters(med, rfm)
    total_rev = rfm["monetary"].sum()
    profiles = []
    centroids_scaled = res.model.cluster_centers_
    # Map KMeans internal labels to canonical ids via predicted assignment.
    raw_labels = res.model.predict(
        res.transformer.transform(rfm[["recency_days", "frequency", "monetary"]].to_numpy(dtype=float))
    )
    canon_of_raw = pd.Series(res.labels).groupby(raw_labels).agg(lambda s: s.mode().iat[0]).to_dict()
    for cid, g in rfm.groupby("cluster_id"):
        raw = next(r for r, c in canon_of_raw.items() if c == cid)
        centroid_orig = np.expm1(res.transformer.named_steps["scale"].inverse_transform(centroids_scaled[[raw]]))[0]
        profiles.append(
            {
                "cluster_id": int(cid),
                "segment_name": named.loc[cid, "segment_name"],
                "recommended_action": named.loc[cid, "recommended_action"],
                "levels": {
                    "recency": named.loc[cid, "recency_level"],
                    "frequency": named.loc[cid, "frequency_level"],
                    "monetary": named.loc[cid, "monetary_level"],
                    "is_new": bool(named.loc[cid, "is_new"]),
                },
                "customers": int(len(g)),
                "share": float(len(g) / len(rfm)),
                "revenue": float(g["monetary"].sum()),
                "revenue_share": float(g["monetary"].sum() / total_rev),
                "median": {c: float(g[c].median()) for c in cols},
                "mean": {c: float(g[c].mean()) for c in cols},
                "quartiles": {
                    c: [float(g[c].quantile(q)) for q in (0.25, 0.5, 0.75)]
                    for c in ["recency_days", "frequency", "monetary"]
                },
                "centroid": {
                    "recency_days": float(centroid_orig[0]),
                    "frequency": float(centroid_orig[1]),
                    "monetary": float(centroid_orig[2]),
                },
            }
        )
    seg = {
        "population": "All customers with at least one qualifying purchase before the scoring cutoff",
        "customers": int(len(rfm)),
        "features": ["recency_days", "frequency", "monetary"],
        "transform": "log1p then StandardScaler (fit on this population only)",
        "k_table": res.k_table,
        "selected_k": res.selected_k,
        "silhouette": res.silhouette,
        "silhouette_sample_size": res.silhouette_sample_size,
        "selection_rule": res.selection_rule,
        "pca_explained_variance": res.pca_explained_variance,
        "profiles": profiles,
        "population_quantiles": {
            c: {str(q): float(rfm[c].quantile(q)) for q in (0.25, 1 / 3, 0.5, 2 / 3, 0.75)} for c in cols
        },
    }
    out = rfm[["customer_key", "cluster_id", "pca_x", "pca_y", "recency_days", "frequency", "monetary", "tenure_days"]]
    out.to_parquet(PROCESSED_DIR / "segment_assignments.parquet", index=False)
    _json(PROCESSED_DIR / "segmentation.json", seg)
    names = {p["cluster_id"]: p["segment_name"] for p in profiles}
    figures.silhouette_plot(res.k_table, REPORTS_DIR / "figures" / "silhouette_by_k.png")
    figures.segment_scatter(
        res.pca_coords,
        res.labels,
        names,
        res.pca_explained_variance,
        REPORTS_DIR / "figures" / "segments_pca.png",
        cfg.random_seed,
    )
    return seg


def stage_churn(cfg: PipelineConfig = DEFAULT_CONFIG) -> dict:
    c = cfg.churn
    training = pd.read_parquet(PROCESSED_DIR / "training_snapshots.parquet")
    cutoffs = sorted(training["cutoff"].unique())
    split = temporal_split([pd.Timestamp(x) for x in cutoffs], c.n_test_snapshots, c.n_val_snapshots, c.horizon_days)
    exp = run_churn_experiment(training, split, cfg.random_seed, c.target_recall, c.top_fraction)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(exp.selected_model, ARTIFACTS_DIR / "churn_model.joblib")
    exp.test_frame.to_parquet(PROCESSED_DIR / "test_scores.parquet", index=False)
    deciles = decile_table(exp.test_frame)
    report = {
        "definition": {
            "rule": (
                f"A customer active in the {c.lookback_days} days before the cutoff is labelled "
                f"inactive (churned=1) if they make no qualifying purchase in the {c.horizon_days} "
                "days starting at the cutoff."
            ),
            "lookback_days": c.lookback_days,
            "horizon_days": c.horizon_days,
            "snapshot_frequency": "monthly (first day of month, 00:00)",
            "disclaimer": (
                "This predicts future purchase inactivity under a defined historical behavioural "
                "rule. It does not establish that a customer has contractually or permanently churned."
            ),
        },
        "split": split.to_dict(),
        "class_balance": exp.class_balance,
        "selection_metric": "validation ROC-AUC (simpler family preferred within 0.002)",
        "threshold_rule": f"highest validation threshold reaching recall >= {c.target_recall}",
        "validation_results": exp.validation_results,
        "best_per_family": exp.best_per_family,
        "selected_family": exp.selected_family,
        "selected_params": exp.selected_params,
        "threshold": exp.threshold,
        "test_results": exp.test_results,
        "test_curves": exp.test_curves,
        "test_per_snapshot": exp.test_per_snapshot,
        "test_top_fraction": exp.test_top_fraction_by_snapshot,
        "test_deciles": deciles,
        "seen_vs_unseen": exp.seen_vs_unseen,
        "repeated_customers": {
            "train_rows_per_customer": float(exp.class_balance[0]["rows"] / exp.class_balance[0]["customers"]),
            "note": "Customers appear in several monthly snapshots; test rows for customers never seen in train/validation are reported separately.",
        },
    }
    _json(PROCESSED_DIR / "churn_report.json", report)
    figures.roc_pr_plot(exp.test_curves, exp.selected_family, REPORTS_DIR / "figures" / "roc_pr_test.png")
    figures.decile_plot(deciles, REPORTS_DIR / "figures" / "risk_deciles_test.png")
    return report


def _scored_frame(cfg: PipelineConfig) -> pd.DataFrame:
    model = joblib.load(ARTIFACTS_DIR / "churn_model.joblib")
    scoring = add_customer_keys(pd.read_parquet(PROCESSED_DIR / "scoring_features.parquet"), get_secret())
    scoring["churn_probability"] = model.predict_proba(scoring[list(snap.MODEL_FEATURES)])[:, 1]
    return scoring


def stage_score(cfg: PipelineConfig = DEFAULT_CONFIG) -> dict:
    c, r = cfg.churn, cfg.retention
    scoring = _scored_frame(cfg)
    churn_report = _read_json(PROCESSED_DIR / "churn_report.json")
    order = rank_order(scoring["churn_probability"].to_numpy(), scoring["customer_key"].to_numpy())
    rank = np.empty(len(scoring), dtype=int)
    rank[order] = np.arange(1, len(scoring) + 1)
    scoring["risk_rank"] = rank
    scoring["risk_percentile"] = 1 - (rank - 1) / len(scoring)
    k = top_k_count(len(scoring), c.top_fraction)
    scoring["in_top_decile"] = scoring["risk_rank"] <= k
    scoring["above_threshold"] = scoring["churn_probability"] >= churn_report["threshold"]
    scoring["risk_band"] = pd.cut(
        scoring["risk_rank"] / len(scoring),
        bins=[0, 0.10, 0.30, 0.60, 1.0],
        labels=["Very high", "High", "Medium", "Low"],
        include_lowest=True,
    ).astype(str)

    purchases, _ = _load_clean()
    invoices = snap.invoice_table(purchases)
    cutoff = pd.Timestamp(scoring["cutoff"].iloc[0])
    season = seasonal_factor(invoices, cutoff, c.lookback_days, r.projection_horizon_days)
    proj = project_revenue(
        scoring, c.lookback_days, r.projection_horizon_days, season["factor"], r.projection_cap_quantile
    )
    scoring = scoring.merge(
        proj[["customer_key", "daily_revenue_rate", "projected_revenue", "projection_capped"]], on="customer_key"
    )
    scoring["expected_revenue_at_risk"] = scoring["churn_probability"] * scoring["projected_revenue"]

    seg = pd.read_parquet(PROCESSED_DIR / "segment_assignments.parquet")[["customer_key", "cluster_id"]]
    scoring = scoring.merge(seg, on="customer_key", how="left")
    if scoring["cluster_id"].isna().any():
        raise AssertionError("Every scored customer must have a segment")

    keep = [
        "customer_key",
        "cutoff",
        "cluster_id",
        *snap.MODEL_FEATURES,
        "churn_probability",
        "risk_rank",
        "risk_percentile",
        "risk_band",
        "in_top_decile",
        "above_threshold",
        "daily_revenue_rate",
        "projected_revenue",
        "projection_capped",
        "expected_revenue_at_risk",
    ]
    scoring[keep].to_parquet(PROCESSED_DIR / "scores.parquet", index=False)
    meta = {
        "scoring_cutoff": str(cutoff.date()),
        "scored_customers": int(len(scoring)),
        "top_decile_size": k,
        "seasonal_factor": season,
        "daily_rate_cap": proj.attrs["daily_rate_cap"],
        "capped_customers": int(proj["projection_capped"].sum()),
        "above_threshold_customers": int(scoring["above_threshold"].sum()),
    }
    _json(PROCESSED_DIR / "score_meta.json", meta)
    return meta


def stage_explain(cfg: PipelineConfig = DEFAULT_CONFIG) -> dict:
    model = joblib.load(ARTIFACTS_DIR / "churn_model.joblib")
    training = pd.read_parquet(PROCESSED_DIR / "training_snapshots.parquet")
    churn_report = _read_json(PROCESSED_DIR / "churn_report.json")
    train_cutoffs = set(pd.to_datetime(churn_report["split"]["train"]))
    background = training[training["cutoff"].isin(train_cutoffs)].sample(n=500, random_state=cfg.random_seed)
    scores = pd.read_parquet(PROCESSED_DIR / "scores.parquet")

    out = explain(model, background, scores)
    glob = global_importance(out, scores)
    top_feats = [g["feature"] for g in glob[:10]]
    bees = beeswarm_points(out, scores, top_feats, 300, cfg.random_seed)
    top = scores[scores["in_top_decile"]]
    pos = scores.index.get_indexer(top.index)
    local = local_explanations(
        type(out)(
            values=out.values[pos],
            base_value=out.base_value,
            features=out.features,
            explainer_type=out.explainer_type,
            output_space=out.output_space,
        ),
        top.reset_index(drop=True),
        top["customer_key"].tolist(),
        top_n=8,
    )
    # Additivity check: base + sum(contributions) must reproduce the model output.
    target = out.model_output(scores["churn_probability"].to_numpy())
    recon = out.base_value + out.values.sum(axis=1)
    max_err = float(np.max(np.abs(recon - target)))
    report = {
        "explainer": out.explainer_type,
        "model_family": churn_report["selected_family"],
        "output_space": out.output_space,
        "base_value": out.base_value,
        "background": {
            "rows": len(background),
            "source": "random sample of training-partition snapshots",
            "seed": cfg.random_seed,
        },
        "explained_rows": int(len(scores)),
        "additivity_max_abs_error": max_err,
        "global": glob,
        "beeswarm": bees,
        "caveat": "SHAP values describe how the model reached its score. They are associations, not causal effects of changing a feature.",
    }
    _json(PROCESSED_DIR / "shap_report.json", report)
    pd.DataFrame(local).to_parquet(PROCESSED_DIR / "shap_local.parquet", index=False)
    figures.shap_bar(glob, REPORTS_DIR / "figures" / "shap_global.png")
    return report


def stage_simulate(cfg: PipelineConfig = DEFAULT_CONFIG) -> dict:
    r, c = cfg.retention, cfg.churn
    scores = pd.read_parquet(PROCESSED_DIR / "scores.parquet")
    meta = _read_json(PROCESSED_DIR / "score_meta.json")
    season = meta["seasonal_factor"]["factor"]
    scenarios = {
        name: simulate(
            scores,
            ScenarioAssumptions(target_fraction=c.top_fraction, horizon_days=r.projection_horizon_days, **params),
            c.horizon_days,
            season,
        )
        for name, params in r.scenarios.items()
    }
    # Same base assumptions, but the 10% cohort chosen by expected revenue at risk.
    value_ranked = simulate(
        scores,
        ScenarioAssumptions(
            target_fraction=c.top_fraction,
            horizon_days=r.projection_horizon_days,
            ranking="value_at_risk",
            **r.scenarios["base"],
        ),
        c.horizon_days,
        season,
    )
    top = scores[scores["in_top_decile"]]
    seg = _read_json(PROCESSED_DIR / "segmentation.json")
    names = {p["cluster_id"]: p["segment_name"] for p in seg["profiles"]}
    cohort = {
        "customers": int(len(top)),
        "share_of_scored": float(len(top) / len(scores)),
        "min_risk": float(top["churn_probability"].min()),
        "mean_risk": float(top["churn_probability"].mean()),
        "max_risk": float(top["churn_probability"].max()),
        "projected_revenue": float(top["projected_revenue"].sum()),
        "expected_revenue_at_risk": float(top["expected_revenue_at_risk"].sum()),
        "all_scored_expected_revenue_at_risk": float(scores["expected_revenue_at_risk"].sum()),
        "segment_mix": [
            {"cluster_id": int(k), "segment_name": names[int(k)], "customers": int(v)}
            for k, v in top["cluster_id"].value_counts().sort_index().items()
        ],
        "risk_histogram": [
            {"bin_start": float(b), "customers": int(n)}
            for b, n in zip(
                np.arange(0, 1, 0.05),
                np.histogram(scores["churn_probability"], bins=np.arange(0, 1.0001, 0.05))[0],
                strict=True,
            )
        ],
        "tie_policy": "Ranked by probability (desc) then customer key (asc); cohort size = ceil(10% of scored customers).",
    }
    report = {
        "currency": r.currency,
        "season_factor": meta["seasonal_factor"],
        "projection": {
            "horizon_days": r.projection_horizon_days,
            "method": "180-day gross qualifying spend / 180, capped at the 99.5th percentile daily rate, x horizon x seasonal factor",
            "daily_rate_cap": meta["daily_rate_cap"],
            "capped_customers": meta["capped_customers"],
        },
        "cohort": cohort,
        "scenarios": scenarios,
        "value_ranked_base": value_ranked,
        "disclaimer": (
            "Scenario estimates under stated assumptions. The dataset contains no retention "
            "campaign or intervention outcomes, so no revenue has been shown to be saved."
        ),
    }
    _json(PROCESSED_DIR / "retention_report.json", report)
    return report


def stage_bundle(cfg: PipelineConfig = DEFAULT_CONFIG) -> dict:
    """Assemble the persistable results bundle (pseudonymous keys only)."""
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    dataset_meta = _read_json(INTERIM_DIR / "dataset_metadata.json")
    manifest = {
        "run_id": str(uuid.uuid4()),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "code_version": git_sha(),
        "config": cfg.to_dict(),
        "dataset": dataset_meta,
    }
    for name in (
        "validation_report",
        "cleaning_report",
        "features_meta",
        "segmentation",
        "churn_report",
        "score_meta",
        "shap_report",
        "retention_report",
    ):
        manifest[name] = _read_json(PROCESSED_DIR / f"{name}.json")
    _json(BUNDLE_DIR / "manifest.json", manifest)
    for name in ("scores", "segment_assignments", "shap_local"):
        df = pd.read_parquet(PROCESSED_DIR / f"{name}.parquet")
        if "customer_id" in df.columns:
            raise AssertionError(f"{name} must not contain raw customer IDs")
        df.to_parquet(BUNDLE_DIR / f"{name}.parquet", index=False)
    _json(REPORTS_DIR / "results_summary.json", summarise(manifest))
    return manifest


def summarise(m: dict) -> dict:
    """Aggregate-only summary committed to the repository for documentation."""
    cr, seg, ret = m["churn_report"], m["segmentation"], m["retention_report"]
    sel = cr["selected_family"]
    return {
        "dataset": {
            k: m["dataset"][k]
            for k in ("source_name", "doi", "licence", "raw_rows", "date_min", "date_max", "zip_sha256")
        },
        "cleaning": m["cleaning_report"]["output"],
        "exclusions": m["cleaning_report"]["exclusions"],
        "segmentation": {
            "customers": seg["customers"],
            "selected_k": seg["selected_k"],
            "silhouette": seg["silhouette"],
            "k_table": seg["k_table"],
            "segments": [
                {k: p[k] for k in ("cluster_id", "segment_name", "customers", "share", "revenue_share", "median")}
                for p in seg["profiles"]
            ],
        },
        "churn": {
            "definition": cr["definition"],
            "split": cr["split"],
            "class_balance": cr["class_balance"],
            "selected_family": sel,
            "selected_params": cr["selected_params"],
            "threshold": cr["threshold"],
            "validation_best": {
                f: {k: cr["best_per_family"][f][k] for k in ("roc_auc", "pr_auc", "recall", "precision")}
                for f in FAMILY_ORDER
            },
            "test": {
                f: {k: v for k, v in cr["test_results"][f].items() if k != "top_fraction_per_snapshot"}
                | {"top_decile_per_snapshot": cr["test_results"][f]["top_fraction_per_snapshot"]}
                for f in FAMILY_ORDER
            },
            "test_per_snapshot": cr["test_per_snapshot"],
            "seen_vs_unseen": cr["seen_vs_unseen"],
            "horizon_sensitivity": m["features_meta"]["horizon_sensitivity"],
        },
        "shap": {
            "explainer": m["shap_report"]["explainer"],
            "additivity_max_abs_error": m["shap_report"]["additivity_max_abs_error"],
            "top_features": [
                {k: g[k] for k in ("rank", "feature", "mean_abs_shap", "direction")}
                for g in m["shap_report"]["global"][:10]
            ],
        },
        "retention": {
            "scoring_cutoff": m["score_meta"]["scoring_cutoff"],
            "scored_customers": m["score_meta"]["scored_customers"],
            "cohort": {k: v for k, v in ret["cohort"].items() if k != "risk_histogram"},
            "season_factor": ret["season_factor"],
            "scenarios": ret["scenarios"],
            "value_ranked_base": ret["value_ranked_base"],
        },
        "run": {"run_id": m["run_id"], "created_at": m["created_at"], "code_version": m["code_version"]},
    }


STAGES = {
    "validate": stage_validate,
    "clean": stage_clean,
    "features": stage_features,
    "segment": stage_segment,
    "churn": stage_churn,
    "score": stage_score,
    "explain": stage_explain,
    "simulate": stage_simulate,
    "bundle": stage_bundle,
}


def run_all(cfg: PipelineConfig = DEFAULT_CONFIG, local_archive: Path | None = None) -> dict:
    stage_acquire(cfg, local_archive)
    stage_validate()
    stage_clean()
    stage_features(cfg)
    stage_segment(cfg)
    stage_churn(cfg)
    stage_score(cfg)
    stage_explain(cfg)
    stage_simulate(cfg)
    return stage_bundle(cfg)
