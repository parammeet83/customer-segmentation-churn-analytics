"""Read-only `/api/v1` endpoints. No endpoint writes to the database."""

from __future__ import annotations

import math
import random
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from customerpulse import __version__
from customerpulse.analytics.scenario_math import CustomerRisk, simulate_rows
from customerpulse.api import service as svc
from customerpulse.database.models import (
    AnalysisRun,
    ChurnScore,
    CustomerSegment,
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
from customerpulse.database.session import get_session
from customerpulse.schemas import responses as r

router = APIRouter(prefix="/api/v1")
DB = Annotated[Session, Depends(get_session)]
CUSTOMER_KEY = r"^C-[0-9a-f]{12}$"
MAX_PAGE_SIZE = 100


@router.get("/health", response_model=r.Health, tags=["meta"])
def health(db: DB) -> r.Health:
    try:
        db.execute(text("SELECT 1"))
        return r.Health(status="ok", database="ok", version=__version__)
    except Exception:  # noqa: BLE001 - health must not raise
        return r.Health(status="degraded", database="unavailable", version=__version__)


@router.get("/analysis-runs", response_model=list[r.RunInfo], tags=["meta"])
def analysis_runs(db: DB, limit: Annotated[int, Query(ge=1, le=50)] = 20) -> list[dict]:
    runs = db.scalars(select(AnalysisRun).order_by(svc.RECENCY, AnalysisRun.started_at.desc()).limit(limit))
    return [svc.run_info(x) for x in runs]


@router.get("/summary", response_model=r.Summary, tags=["overview"])
def summary(db: DB) -> dict:
    run = svc.latest_successful_run(db)
    attempt = svc.latest_attempt(db)
    rep = run.reports
    cr, ret = rep["churn_report"], rep["retention_report"]
    sel = svc.required(
        db.scalar(
            select(ModelMetric).where(
                ModelMetric.run_id == run.id, ModelMetric.evaluation_split == "test", ModelMetric.is_selected
            )
        ),
        "selected test metrics",
    )
    ds = svc.required(db.get(DatasetVersion, run.dataset_version_id), "dataset version")
    segs = db.scalars(select(Segment).where(Segment.run_id == run.id).order_by(Segment.cluster_id)).all()
    bands = db.execute(
        select(
            ChurnScore.risk_band,
            func.count(),
            func.avg(ChurnScore.churn_probability),
            func.sum(ChurnScore.expected_revenue_at_risk),
        )
        .where(ChurnScore.run_id == run.id)
        .group_by(ChurnScore.risk_band)
    ).all()
    order = {"Very high": 0, "High": 1, "Medium": 2, "Low": 3}
    snaps = cr["class_balance"]
    overall = sum(b["churn_rate"] * b["rows"] for b in snaps) / sum(b["rows"] for b in snaps)
    top = cr["test_top_fraction"]
    cohort = ret["cohort"]
    value_ranked = ret["value_ranked_base"]
    takeaway = (
        f"Contacting the {cohort['customers']:,} highest-risk customers covers an estimated "
        f"£{cohort['expected_revenue_at_risk']:,.0f} of expected revenue at risk; ranking the same number of "
        f"customers by risk × value instead covers £{value_ranked['expected_revenue_at_risk']:,.0f}. "
        "Both are scenario estimates under stated assumptions."
    )
    return {
        "run": svc.run_info(run),
        "latest_attempt": svc.run_info(attempt) if attempt and attempt.id != run.id else None,
        "dataset": {
            "source_name": ds.source_name,
            "doi": ds.doi,
            "licence": ds.licence,
            "citation": ds.citation,
            "raw_rows": ds.raw_rows,
            "date_min": ds.date_min,
            "date_max": ds.date_max,
            "purchase_lines": rep["cleaning_report"]["output"]["purchase_lines"],
            "purchase_customers": rep["cleaning_report"]["output"]["purchase_customers"],
        },
        "kpis": {
            "eligible_customers": rep["score_meta"]["scored_customers"],
            "segmented_customers": rep["segmentation"]["customers"],
            "segment_count": run.selected_k,
            "churn_rate_test": next(b["churn_rate"] for b in snaps if b["partition"] == "test"),
            "churn_rate_overall_snapshots": overall,
            "selected_model": run.selected_model,
            "test_roc_auc": sel.roc_auc,
            "test_pr_auc": sel.pr_auc,
            "test_recall": sel.recall,
            "top_decile_customers": cohort["customers"],
            "top_decile_capture_rate_test": top["capture_rate"],
            "top_decile_lift_test": top["lift"],
            "expected_revenue_at_risk_top_decile": cohort["expected_revenue_at_risk"],
            "expected_revenue_at_risk_all_scored": cohort["all_scored_expected_revenue_at_risk"],
            "currency": ret["currency"],
        },
        "segments": [svc.segment_dict(s) for s in segs],
        "risk_bands": sorted(
            [
                {"risk_band": b, "customers": n, "mean_probability": float(p), "expected_revenue_at_risk": float(v)}
                for b, n, p, v in bands
            ],
            key=lambda x: order[x["risk_band"]],
        ),
        "takeaway": takeaway,
    }


@router.get("/data-quality", tags=["methodology"])
def data_quality(db: DB) -> dict:
    run = svc.latest_successful_run(db)
    ds = svc.required(db.get(DatasetVersion, run.dataset_version_id), "dataset version")
    items = db.scalars(select(DataQualityItem).where(DataQualityItem.run_id == run.id)).all()
    rep = run.reports
    return {
        "run_id": str(run.id),
        "dataset": {
            "source_name": ds.source_name,
            "source_url": ds.source_url,
            "doi": ds.doi,
            "licence": ds.licence,
            "citation": ds.citation,
            "zip_sha256": ds.zip_sha256,
            "raw_rows": ds.raw_rows,
            "date_min": ds.date_min,
            "date_max": ds.date_max,
            "details": ds.details,
        },
        "validation": rep["validation_report"],
        "profile": rep["cleaning_report"]["profile"],
        "exclusions": [{"reason": i.reason, "rows": i.rows, "share_of_raw": i.share_of_raw} for i in items],
        "output": rep["cleaning_report"]["output"],
        "monthly_purchase_value": rep["cleaning_report"]["monthly_purchase_value"],
        "features": rep["features_meta"],
        "config": run.config,
    }


@router.get("/segments", response_model=r.SegmentsResponse, tags=["segmentation"])
def segments(db: DB, scatter_points: Annotated[int, Query(ge=0, le=3000)] = 1500) -> dict:
    run = svc.latest_successful_run(db)
    seg = run.reports["segmentation"]
    profiles = db.scalars(select(Segment).where(Segment.run_id == run.id).order_by(Segment.cluster_id)).all()
    ks = db.scalars(
        select(SegmentKSelection).where(SegmentKSelection.run_id == run.id).order_by(SegmentKSelection.k)
    ).all()
    pts = db.execute(
        select(
            CustomerSegment.customer_key,
            CustomerSegment.cluster_id,
            CustomerSegment.pca_x,
            CustomerSegment.pca_y,
            CustomerSegment.recency_days,
            CustomerSegment.frequency,
            CustomerSegment.monetary,
        )
        .where(CustomerSegment.run_id == run.id)
        .order_by(CustomerSegment.customer_key)
    ).all()
    sample = random.Random(42).sample(pts, min(scatter_points, len(pts)))  # noqa: S311 - deterministic display sample
    return {
        "run_id": str(run.id),
        "selected_k": run.selected_k,
        "silhouette": seg["silhouette"],
        "selection_rule": seg["selection_rule"],
        "transform": seg["transform"],
        "population": seg["population"],
        "k_table": [
            {c.name: getattr(k, c.name) for c in SegmentKSelection.__table__.columns if c.name != "run_id"} for k in ks
        ],
        "pca_explained_variance": seg["pca_explained_variance"],
        "profiles": [svc.segment_dict(s) for s in profiles],
        "scatter": [
            {
                "cluster_id": c,
                "x": round(x, 4),
                "y": round(y, 4),
                "recency_days": round(rd, 1),
                "frequency": f,
                "monetary": round(m, 2),
            }
            for _, c, x, y, rd, f, m in sample
        ],
        "population_quantiles": seg["population_quantiles"],
    }


@router.get("/segments/{segment_id}", response_model=r.SegmentDetail, tags=["segmentation"])
def segment_detail(db: DB, segment_id: Annotated[int, Path(ge=0, le=50)]) -> dict:
    run = svc.latest_successful_run(db)
    seg = db.get(Segment, (run.id, segment_id))
    if seg is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    dists = {
        "recency_days": svc.histogram(
            db, run.id, segment_id, CustomerSegment.recency_days, [0, 30, 60, 90, 180, 270, 365, 545, 740]
        ),
        "frequency": svc.histogram(db, run.id, segment_id, CustomerSegment.frequency, [1, 2, 3, 5, 8, 13, 21, 50, 400]),
        "monetary": svc.histogram(
            db, run.id, segment_id, CustomerSegment.monetary, [0, 250, 500, 1000, 2500, 5000, 10000, 25000, 600000]
        ),
    }
    agg = db.execute(
        select(
            func.count(), func.avg(ChurnScore.churn_probability), func.count().filter(ChurnScore.in_top_decile)
        ).where(ChurnScore.run_id == run.id, ChurnScore.cluster_id == segment_id)
    ).one()
    return {
        "profile": svc.segment_dict(seg),
        "distributions": dists,
        "scored_customers": agg[0],
        "mean_churn_probability": float(agg[1]) if agg[1] is not None else None,
        "top_decile_customers": agg[2],
    }


def _paged_customers(
    db: Session,
    page: int,
    page_size: int,
    segment: int | None,
    risk_band: str | None,
    top_decile: bool | None,
    sort: str,
) -> dict:
    run = svc.latest_successful_run(db)
    names = svc.segment_names(db, run.id)
    q = svc.customer_query(run.id)
    if segment is not None:
        q = q.where(ChurnScore.cluster_id == segment)
    if risk_band is not None:
        q = q.where(ChurnScore.risk_band == risk_band)
    if top_decile is not None:
        q = q.where(ChurnScore.in_top_decile == top_decile)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.execute(
        q.order_by(svc.SORTS[sort], ChurnScore.customer_key).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "meta": {"page": page, "page_size": page_size, "total": total, "pages": max(1, math.ceil(total / page_size))},
        "items": [svc.customer_row(s, sn, names) for s, sn in rows],
    }


RiskBand = Literal["Very high", "High", "Medium", "Low"]
SortKey = Literal["risk", "value_at_risk", "monetary", "recency"]


@router.get("/customers", response_model=r.CustomerList, tags=["customers"])
def customers(
    db: DB,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 25,
    segment: Annotated[int | None, Query(ge=0, le=50)] = None,
    risk_band: RiskBand | None = None,
    top_decile: bool | None = None,
    sort: SortKey = "risk",
) -> dict:
    return _paged_customers(db, page, page_size, segment, risk_band, top_decile, sort)


@router.get("/churn/top-risk", response_model=r.CustomerList, tags=["churn"])
def top_risk(
    db: DB,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 25,
    segment: Annotated[int | None, Query(ge=0, le=50)] = None,
) -> dict:
    return _paged_customers(db, page, page_size, segment, None, True, "risk")


@router.get("/customers/{customer_key}", response_model=r.CustomerDetail, tags=["customers"])
def customer_detail(db: DB, customer_key: Annotated[str, Path(pattern=CUSTOMER_KEY)]) -> dict:
    run = svc.latest_successful_run(db)
    row = db.execute(svc.customer_query(run.id).where(ChurnScore.customer_key == customer_key)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found in the latest scored population")
    score, snap = row
    descs = dict(
        db.execute(select(ShapGlobal.feature, ShapGlobal.description).where(ShapGlobal.run_id == run.id)).all()
    )
    local = db.scalars(
        select(ShapLocal)
        .where(ShapLocal.run_id == run.id, ShapLocal.customer_key == customer_key)
        .order_by(ShapLocal.rank)
    ).all()
    return {
        "customer": svc.customer_row(score, snap, svc.segment_names(db, run.id)),
        "features": snap.features,
        "observation_date": snap.observation_date,
        "explanation": [
            {
                "feature": x.feature,
                "description": descs.get(x.feature, x.feature),
                "feature_value": x.feature_value,
                "shap_value": x.shap_value,
                "rank": x.rank,
                "explanation": x.explanation,
            }
            for x in local
        ],
        "explanation_available": bool(local),
        "note": "Individual SHAP explanations are stored for the top-decile cohort. Contributions are associations, not causes.",
    }


@router.get("/churn/metrics", tags=["churn"])
def churn_metrics(db: DB) -> dict:
    run = svc.latest_successful_run(db)
    cr = run.reports["churn_report"]
    keys = (
        "definition",
        "split",
        "class_balance",
        "selection_metric",
        "threshold_rule",
        "threshold",
        "selected_family",
        "selected_params",
        "test_per_snapshot",
        "test_top_fraction",
        "test_deciles",
        "seen_vs_unseen",
        "repeated_customers",
    )
    out = {k: cr[k] for k in keys}
    out["horizon_sensitivity"] = run.reports["features_meta"]["horizon_sensitivity"]
    out["run_id"] = str(run.id)
    return out


@router.get("/models/metrics", tags=["churn"])
def model_metrics(db: DB) -> dict:
    run = svc.latest_successful_run(db)
    rows = db.scalars(
        select(ModelMetric)
        .where(ModelMetric.run_id == run.id)
        .order_by(ModelMetric.evaluation_split, ModelMetric.model_name, ModelMetric.config_index)
    ).all()
    curves = db.scalars(select(ModelCurve).where(ModelCurve.run_id == run.id)).all()
    cols = [c.name for c in ModelMetric.__table__.columns if c.name not in ("id", "run_id")]
    return {
        "run_id": str(run.id),
        "selected_model": run.selected_model,
        "metrics": [{c: getattr(m, c) for c in cols} for m in rows],
        "curves": [{"model_name": c.model_name, "curve_type": c.curve_type, "points": c.points} for c in curves],
    }


@router.get("/churn/explanations", tags=["explainability"])
def explanations(db: DB, customer_key: Annotated[str | None, Query(pattern=CUSTOMER_KEY)] = None) -> dict:
    run = svc.latest_successful_run(db)
    shap_r = run.reports["shap_report"]
    glob = db.scalars(select(ShapGlobal).where(ShapGlobal.run_id == run.id).order_by(ShapGlobal.rank)).all()
    examples = db.scalars(
        select(ChurnScore.customer_key)
        .where(ChurnScore.run_id == run.id, ChurnScore.in_top_decile)
        .order_by(ChurnScore.risk_rank)
        .limit(10)
    ).all()
    out = {
        "run_id": str(run.id),
        "explainer": shap_r["explainer"],
        "model_family": shap_r["model_family"],
        "output_space": shap_r["output_space"],
        "base_value": shap_r["base_value"],
        "additivity_max_abs_error": shap_r["additivity_max_abs_error"],
        "background": shap_r["background"],
        "caveat": shap_r["caveat"],
        "global": [
            {c.name: getattr(g, c.name) for c in ShapGlobal.__table__.columns if c.name != "run_id"} for g in glob
        ],
        "beeswarm": shap_r["beeswarm"],
        "example_customers": list(examples),
        "local": None,
    }
    if customer_key is not None:
        local = db.scalars(
            select(ShapLocal)
            .where(ShapLocal.run_id == run.id, ShapLocal.customer_key == customer_key)
            .order_by(ShapLocal.rank)
        ).all()
        if not local:
            raise HTTPException(
                status_code=404,
                detail="No stored explanation for this customer (only the top-decile cohort is explained)",
            )
        out["local"] = [
            {c.name: getattr(x, c.name) for c in ShapLocal.__table__.columns if c.name != "run_id"} for x in local
        ]
    return out


@router.get("/retention/scenarios", tags=["retention"])
def retention_scenarios(db: DB) -> dict:
    run = svc.latest_successful_run(db)
    ret = run.reports["retention_report"]
    scen = db.scalars(select(RetentionScenario).where(RetentionScenario.run_id == run.id)).all()
    return {
        "run_id": str(run.id),
        "currency": ret["currency"],
        "season_factor": ret["season_factor"],
        "projection": ret["projection"],
        "cohort": ret["cohort"],
        "scenarios": [{"name": s.name, "assumptions": s.assumptions, "results": s.results} for s in scen],
        "disclaimer": ret["disclaimer"],
    }


@router.get("/retention/simulator-data", tags=["retention"])
def simulator_data(db: DB) -> dict:
    """Compact per-customer inputs so the dashboard can recalculate instantly.

    Contains only probability, daily revenue rate and segment, ordered by risk
    rank; customer keys are deliberately omitted.
    """
    run = svc.latest_successful_run(db)
    rows = db.execute(
        select(ChurnScore.churn_probability, ChurnScore.daily_revenue_rate, ChurnScore.cluster_id)
        .where(ChurnScore.run_id == run.id)
        .order_by(ChurnScore.risk_rank)
    ).all()
    ret = run.reports["retention_report"]
    return {
        "run_id": str(run.id),
        "currency": ret["currency"],
        "season_factor": ret["season_factor"]["factor"],
        "churn_horizon_days": run.config["churn"]["horizon_days"],
        "columns": ["churn_probability", "daily_revenue_rate", "cluster_id"],
        "rows": [[round(p, 6), round(d, 4), c] for p, d, c in rows],
        "segments": svc.segment_names(db, run.id),
        "defaults": run.config["retention"]["scenarios"],
    }


@router.get("/retention/simulate", response_model=r.SimulationResult, tags=["retention"])
def retention_simulate(
    db: DB,
    target_fraction: Annotated[float, Query(gt=0, le=1)] = 0.10,
    effectiveness: Annotated[float, Query(ge=0, le=1)] = 0.10,
    cost_per_contact: Annotated[float, Query(ge=0, le=1000)] = 3.0,
    horizon_days: Annotated[int, Query(ge=1, le=365)] = 90,
    margin: Annotated[float, Query(gt=0, le=1)] = 1.0,
    ranking: Literal["risk", "value_at_risk"] = "risk",
) -> dict:
    run = svc.latest_successful_run(db)
    ret = run.reports["retention_report"]
    rows = [
        CustomerRisk(k, p, d)
        for k, p, d in db.execute(
            select(ChurnScore.customer_key, ChurnScore.churn_probability, ChurnScore.daily_revenue_rate).where(
                ChurnScore.run_id == run.id
            )
        )
    ]
    season = ret["season_factor"]["factor"]
    res = simulate_rows(rows, target_fraction, effectiveness, cost_per_contact, horizon_days, margin, ranking, season)
    return {**res, "season_factor": season, "currency": ret["currency"]}
