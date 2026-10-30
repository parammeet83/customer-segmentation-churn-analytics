"""Read-only queries for the API. All SQL is parameterised via SQLAlchemy."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import Select, and_, func, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session

from customerpulse.database.models import (
    AnalysisRun,
    ChurnScore,
    CustomerSegment,
    CustomerSnapshot,
    Segment,
)


def run_info(r: AnalysisRun) -> dict:
    return {
        "run_id": str(r.id),
        "status": r.status,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "code_version": r.code_version,
        "selected_k": r.selected_k,
        "selected_model": r.selected_model,
        "model_version": r.model_version,
        "scoring_cutoff": r.scoring_cutoff,
        "error_summary": r.error_summary,
    }


def latest_successful_run(db: Session) -> AnalysisRun:
    run = db.scalar(
        select(AnalysisRun).where(AnalysisRun.status == "succeeded").order_by(AnalysisRun.finished_at.desc()).limit(1)
    )
    if run is None:
        raise HTTPException(status_code=503, detail="No successful analysis run is available yet")
    return run


RECENCY = func.coalesce(AnalysisRun.finished_at, AnalysisRun.started_at).desc()


def latest_attempt(db: Session) -> AnalysisRun | None:
    return db.scalar(select(AnalysisRun).order_by(RECENCY, AnalysisRun.started_at.desc()).limit(1))


def segment_names(db: Session, run_id: uuid.UUID) -> dict[int, str]:
    return {
        c: n for c, n in db.execute(select(Segment.cluster_id, Segment.segment_name).where(Segment.run_id == run_id))
    }


def segment_dict(s: Segment) -> dict:
    return {
        k: getattr(s, k)
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
    }


SORTS = {
    "risk": ChurnScore.risk_rank.asc(),
    "value_at_risk": ChurnScore.expected_revenue_at_risk.desc(),
    "monetary": CustomerSnapshot.monetary.desc(),
    "recency": CustomerSnapshot.recency_days.desc(),
}


def customer_query(run_id: uuid.UUID) -> Select:
    return (
        select(ChurnScore, CustomerSnapshot)
        .join(
            CustomerSnapshot,
            and_(
                CustomerSnapshot.run_id == ChurnScore.run_id, CustomerSnapshot.customer_key == ChurnScore.customer_key
            ),
        )
        .where(ChurnScore.run_id == run_id)
    )


def customer_row(score: ChurnScore, snap: CustomerSnapshot, names: dict[int, str]) -> dict:
    return {
        "customer_key": score.customer_key,
        "cluster_id": score.cluster_id,
        "segment_name": names.get(score.cluster_id, "Unknown"),
        "churn_probability": score.churn_probability,
        "risk_rank": score.risk_rank,
        "risk_percentile": score.risk_percentile,
        "risk_band": score.risk_band,
        "in_top_decile": score.in_top_decile,
        "above_threshold": score.above_threshold,
        "recency_days": snap.recency_days,
        "frequency": snap.frequency,
        "monetary": snap.monetary,
        "projected_revenue": score.projected_revenue,
        "expected_revenue_at_risk": score.expected_revenue_at_risk,
    }


def histogram(db: Session, run_id: uuid.UUID, cluster_id: int, column, bins: list[float]) -> list[dict]:
    """Counts per bin computed in SQL (width_bucket) for one segment."""
    bucket = func.width_bucket(column, array([float(b) for b in bins]))
    rows = dict(
        db.execute(
            select(bucket, func.count())
            .where(CustomerSegment.run_id == run_id, CustomerSegment.cluster_id == cluster_id)
            .group_by(bucket)
        ).all()
    )
    out = []
    for i in range(len(bins) - 1):
        out.append({"bin_start": bins[i], "bin_end": bins[i + 1], "customers": int(rows.get(i + 1, 0))})
    overflow = int(rows.get(len(bins), 0))
    if overflow:
        out[-1]["customers"] += overflow
    return out
