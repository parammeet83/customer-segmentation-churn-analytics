"""Load a results bundle into PostgreSQL using the writer role.

The run row is committed first with status ``running``. All result rows are
then written in one transaction; only if that succeeds is the run marked
``succeeded``. On failure the run is marked ``failed`` with a short,
secret-free error summary, and the API keeps serving the previous
successful run.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from customerpulse.database.models import (
    AnalysisRun,
    ChurnScore,
    CustomerSegment,
    CustomerSnapshot,
    DataQualityItem,
    DatasetVersion,
    ModelCurve,
    ModelMetric,
    RetentionScenario,
    Segment,
    SegmentKSelection,
    ShapGlobal,
    ShapLocal,
)
from customerpulse.database.session import engine_for
from customerpulse.features.snapshots import MODEL_FEATURES
from customerpulse.settings import get_settings

logger = logging.getLogger(__name__)
METRIC_KEYS = (
    "n",
    "positives",
    "threshold",
    "recall",
    "precision",
    "f1",
    "roc_auc",
    "pr_auc",
    "brier",
    "tp",
    "fp",
    "tn",
    "fn",
    "top_precision",
    "top_capture_rate",
    "top_lift",
)
REPORT_DROP = {"churn_report": ("validation_results", "test_curves"), "shap_report": ("global",)}


def _clean(v):
    """JSON/DB-safe scalars (NaN -> None, numpy -> python)."""
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def build_rows(manifest: dict, bundle: Path) -> dict[type, list[dict]]:
    run_id = uuid.UUID(manifest["run_id"])
    cr, seg, shap_r = manifest["churn_report"], manifest["segmentation"], manifest["shap_report"]
    model_version = f"{cr['selected_family']}-{manifest['run_id'][:8]}"
    rows: dict[type, list[dict]] = {}

    rows[DataQualityItem] = [{"run_id": run_id, **e} for e in manifest["cleaning_report"]["exclusions"]]
    rows[SegmentKSelection] = [
        {
            "run_id": run_id,
            **{
                k: r[k]
                for k in (
                    "k",
                    "silhouette",
                    "inertia",
                    "min_cluster_share",
                    "max_cluster_share",
                    "stability_ari",
                    "in_selectable_range",
                    "passes_guards",
                    "selected",
                )
            },
        }
        for r in seg["k_table"]
    ]
    rows[Segment] = [
        {
            "run_id": run_id,
            **{
                k: p[k]
                for k in (
                    "cluster_id",
                    "segment_name",
                    "recommended_action",
                    "customers",
                    "share",
                    "revenue",
                    "revenue_share",
                    "levels",
                    "median",
                    "mean",
                    "quartiles",
                    "centroid",
                )
            },
        }
        for p in seg["profiles"]
    ]
    assign = pd.read_parquet(bundle / "segment_assignments.parquet")
    rows[CustomerSegment] = [{"run_id": run_id, **r} for r in _records(assign)]

    scores = pd.read_parquet(bundle / "scores.parquet")
    obs = scores["cutoff"].iloc[0]
    snaps, churn = [], []
    for r in _records(scores):
        snaps.append(
            {
                "run_id": run_id,
                "customer_key": r["customer_key"],
                "observation_date": obs.date(),
                "feature_cutoff": obs.to_pydatetime(),
                "feature_version": manifest["config"]["feature_version"],
                "recency_days": r["recency_days"],
                "frequency": int(r["frequency"]),
                "monetary": r["monetary"],
                "features": {f: r[f] for f in MODEL_FEATURES},
            }
        )
        churn.append(
            {
                "run_id": run_id,
                "customer_key": r["customer_key"],
                "observation_date": obs.date(),
                "model_version": model_version,
                **{
                    k: r[k]
                    for k in (
                        "cluster_id",
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
                    )
                },
            }
        )
        churn[-1]["cluster_id"] = int(churn[-1]["cluster_id"])
    rows[CustomerSnapshot], rows[ChurnScore] = snaps, churn

    split = cr["split"]
    periods = {
        "validation": (split["validation"][0], split["validation"][-1]),
        "test": (split["test"][0], split["test"][-1]),
    }
    best_idx = {f: b["config_index"] for f, b in cr["best_per_family"].items()}
    metrics = []
    for v in cr["validation_results"]:
        metrics.append(
            {
                "run_id": run_id,
                "model_name": v["family"],
                "model_version": f"{v['family']}-{manifest['run_id'][:8]}-c{v['config_index']}",
                "config_index": v["config_index"],
                "evaluation_split": "validation",
                "period_start": _d(periods["validation"][0]),
                "period_end": _d(periods["validation"][1]),
                "is_selected": v["family"] == cr["selected_family"] and v["config_index"] == best_idx[v["family"]],
                "is_family_best": v["config_index"] == best_idx[v["family"]],
                "params": v["params"],
                **{k: _clean(v[k]) for k in METRIC_KEYS if k not in ("top_precision", "top_capture_rate", "top_lift")},
                "top_precision": v["top_precision"],
                "top_capture_rate": v["top_capture_rate"],
                "top_lift": v["top_lift"],
                "extra": {},
            }
        )
    for fam, t in cr["test_results"].items():
        metrics.append(
            {
                "run_id": run_id,
                "model_name": fam,
                "model_version": f"{fam}-{manifest['run_id'][:8]}-c{best_idx[fam]}",
                "config_index": best_idx[fam],
                "evaluation_split": "test",
                "period_start": _d(periods["test"][0]),
                "period_end": _d(periods["test"][1]),
                "is_selected": fam == cr["selected_family"],
                "is_family_best": True,
                "params": cr["best_per_family"][fam]["params"],
                **{k: _clean(t[k]) for k in METRIC_KEYS},
                "extra": {
                    "top_fraction_per_snapshot": t["top_fraction_per_snapshot"],
                    "f2": t["f2"],
                    "positive_rate": t["positive_rate"],
                },
            }
        )
    rows[ModelMetric] = metrics
    rows[ModelCurve] = [
        {"run_id": run_id, "model_name": fam, "curve_type": ct, "points": pts}
        for fam, c in cr["test_curves"].items()
        for ct, pts in c.items()
    ]
    rows[ShapGlobal] = [
        {
            "run_id": run_id,
            **{
                k: g[k]
                for k in (
                    "feature",
                    "rank",
                    "description",
                    "mean_abs_shap",
                    "mean_shap",
                    "value_shap_correlation",
                    "direction",
                )
            },
        }
        for g in shap_r["global"]
    ]
    local = pd.read_parquet(bundle / "shap_local.parquet")
    rows[ShapLocal] = [{"run_id": run_id, **r} for r in _records(local)]
    ret = manifest["retention_report"]
    scen = [
        {
            "run_id": run_id,
            "name": n,
            "assumptions": s["assumptions"],
            "results": {k: v for k, v in s.items() if k != "assumptions"},
        }
        for n, s in ret["scenarios"].items()
    ]
    vr = ret["value_ranked_base"]
    scen.append(
        {
            "run_id": run_id,
            "name": "base_value_ranked",
            "assumptions": vr["assumptions"],
            "results": {k: v for k, v in vr.items() if k != "assumptions"},
        }
    )
    rows[RetentionScenario] = scen
    return rows


def _reports(manifest: dict) -> dict:
    out = {}
    for key in (
        "validation_report",
        "cleaning_report",
        "features_meta",
        "segmentation",
        "churn_report",
        "score_meta",
        "shap_report",
        "retention_report",
    ):
        part = dict(manifest[key])
        for drop in REPORT_DROP.get(key, ()):
            part.pop(drop, None)
        if key == "segmentation":
            part.pop("profiles", None)
        out[key] = part
    return json.loads(json.dumps(out, default=str))


def _safe_error(exc: Exception) -> str:
    # Exception class plus a truncated first line; connection strings are never included.
    msg = str(exc).splitlines()[0] if str(exc) else ""
    if "postgres" in msg.lower() and "@" in msg:
        msg = "database error"
    return f"{type(exc).__name__}: {msg}"[:480]


def ensure_dataset_version(session: Session, manifest: dict) -> int:
    ds = manifest["dataset"]
    existing = session.scalar(select(DatasetVersion.id).where(DatasetVersion.zip_sha256 == ds["zip_sha256"]))
    if existing:
        return existing
    return session.scalar(
        insert(DatasetVersion)
        .values(
            source_name=ds["source_name"],
            source_url=ds["source_url"],
            doi=ds["doi"],
            licence=ds["licence"],
            citation=ds["citation"],
            zip_sha256=ds["zip_sha256"],
            xlsx_sha256=ds["xlsx_sha256"],
            raw_rows=ds["raw_rows"],
            date_min=datetime.fromisoformat(ds["date_min"]),
            date_max=datetime.fromisoformat(ds["date_max"]),
            details={
                k: ds[k] for k in ("sheets", "columns", "acquired_at", "zip_checksum_matches_recorded", "landing_page")
            },
        )
        .returning(DatasetVersion.id)
    )


def persist_bundle(bundle: Path | None = None, engine: Engine | None = None) -> str:
    from customerpulse.pipeline import BUNDLE_DIR

    bundle = bundle or BUNDLE_DIR
    manifest = json.loads((bundle / "manifest.json").read_text())
    if engine is None:
        url = get_settings().writer_database_url
        if not url:
            raise RuntimeError("WRITER_DATABASE_URL is not configured")
        engine = engine_for(url)
    run_id = uuid.UUID(manifest["run_id"])

    with Session(engine) as s, s.begin():
        if s.get(AnalysisRun, run_id) is not None:
            raise RuntimeError(f"Run {run_id} is already persisted")
        ds_id = ensure_dataset_version(s, manifest)
        s.add(
            AnalysisRun(
                id=run_id,
                dataset_version_id=ds_id,
                status="running",
                started_at=datetime.fromisoformat(manifest["created_at"]),
                code_version=manifest.get("code_version"),
                config=manifest["config"],
                churn_definition=manifest["churn_report"]["definition"],
                reports={},
            )
        )

    try:
        rows = build_rows(manifest, bundle)
        with Session(engine) as s, s.begin():
            for model in (
                DataQualityItem,
                SegmentKSelection,
                Segment,
                CustomerSegment,
                CustomerSnapshot,
                ChurnScore,
                ModelMetric,
                ModelCurve,
                ShapGlobal,
                ShapLocal,
                RetentionScenario,
            ):
                if rows.get(model):
                    s.execute(insert(model), rows[model])
            cr = manifest["churn_report"]
            s.execute(
                update(AnalysisRun)
                .where(AnalysisRun.id == run_id)
                .values(
                    status="succeeded",
                    finished_at=datetime.now(UTC),
                    selected_k=manifest["segmentation"]["selected_k"],
                    selected_model=cr["selected_family"],
                    model_version=f"{cr['selected_family']}-{manifest['run_id'][:8]}",
                    scoring_cutoff=_d(manifest["score_meta"]["scoring_cutoff"]),
                    reports=_reports(manifest),
                )
            )
    except Exception as exc:
        logger.error("Persisting run %s failed: %s", run_id, type(exc).__name__)
        with Session(engine) as s, s.begin():
            s.execute(
                update(AnalysisRun)
                .where(AnalysisRun.id == run_id)
                .values(status="failed", finished_at=datetime.now(UTC), error_summary=_safe_error(exc))
            )
        raise
    logger.info("Persisted run %s", run_id)
    return str(run_id)
