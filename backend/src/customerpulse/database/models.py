"""SQLAlchemy ORM models for persisted analysis results.

Every result table is keyed by ``run_id`` so several analysis runs can coexist;
the public API serves only the most recent run whose status is ``succeeded``.
Raw transactions and raw customer IDs are never stored here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

RUN_FK = "analysis_runs.id"


class Base(DeclarativeBase):
    pass


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(Text)
    doi: Mapped[str] = mapped_column(String(200))
    licence: Mapped[str] = mapped_column(String(50))
    citation: Mapped[str] = mapped_column(Text)
    zip_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    xlsx_sha256: Mapped[str] = mapped_column(String(64))
    raw_rows: Mapped[int] = mapped_column(Integer)
    date_min: Mapped[datetime] = mapped_column(DateTime)
    date_max: Mapped[datetime] = mapped_column(DateTime)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    details: Mapped[dict] = mapped_column(JSONB)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="ck_run_status"),
        Index("ix_runs_status_finished", "status", "finished_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code_version: Mapped[str | None] = mapped_column(String(64))
    config: Mapped[dict] = mapped_column(JSONB)
    churn_definition: Mapped[dict] = mapped_column(JSONB)
    selected_k: Mapped[int | None] = mapped_column(Integer)
    selected_model: Mapped[str | None] = mapped_column(String(100))
    model_version: Mapped[str | None] = mapped_column(String(100))
    scoring_cutoff: Mapped[date | None] = mapped_column(Date)
    reports: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_summary: Mapped[str | None] = mapped_column(String(500))


class DataQualityItem(Base):
    __tablename__ = "data_quality_items"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), primary_key=True)
    reason: Mapped[str] = mapped_column(String(100), primary_key=True)
    rows: Mapped[int] = mapped_column(Integer)
    share_of_raw: Mapped[float] = mapped_column(Float)


class SegmentKSelection(Base):
    __tablename__ = "segment_k_selection"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), primary_key=True)
    k: Mapped[int] = mapped_column(Integer, primary_key=True)
    silhouette: Mapped[float] = mapped_column(Float)
    inertia: Mapped[float] = mapped_column(Float)
    min_cluster_share: Mapped[float] = mapped_column(Float)
    max_cluster_share: Mapped[float] = mapped_column(Float)
    stability_ari: Mapped[float] = mapped_column(Float)
    in_selectable_range: Mapped[bool] = mapped_column(Boolean)
    passes_guards: Mapped[bool] = mapped_column(Boolean)
    selected: Mapped[bool] = mapped_column(Boolean)


class Segment(Base):
    __tablename__ = "segments"
    __table_args__ = (
        UniqueConstraint("run_id", "segment_name", name="uq_segment_name"),
        CheckConstraint("share >= 0 AND share <= 1", name="ck_segment_share"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_name: Mapped[str] = mapped_column(String(120))
    recommended_action: Mapped[str] = mapped_column(Text)
    customers: Mapped[int] = mapped_column(Integer)
    share: Mapped[float] = mapped_column(Float)
    revenue: Mapped[float] = mapped_column(Float)
    revenue_share: Mapped[float] = mapped_column(Float)
    levels: Mapped[dict] = mapped_column(JSONB)
    median: Mapped[dict] = mapped_column(JSONB)
    mean: Mapped[dict] = mapped_column(JSONB)
    quartiles: Mapped[dict] = mapped_column(JSONB)
    centroid: Mapped[dict] = mapped_column(JSONB)


class CustomerSegment(Base):
    __tablename__ = "customer_segments"
    __table_args__ = (
        ForeignKeyConstraint(["run_id", "cluster_id"], ["segments.run_id", "segments.cluster_id"], ondelete="CASCADE"),
        Index("ix_customer_segments_cluster", "run_id", "cluster_id"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), primary_key=True)
    customer_key: Mapped[str] = mapped_column(String(20), primary_key=True)
    cluster_id: Mapped[int] = mapped_column(Integer)
    pca_x: Mapped[float] = mapped_column(Float)
    pca_y: Mapped[float] = mapped_column(Float)
    recency_days: Mapped[float] = mapped_column(Float)
    frequency: Mapped[int] = mapped_column(Integer)
    monetary: Mapped[float] = mapped_column(Float)
    tenure_days: Mapped[float] = mapped_column(Float)


class CustomerSnapshot(Base):
    """Scoring-date features for each scored customer."""

    __tablename__ = "customer_snapshots"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), primary_key=True)
    customer_key: Mapped[str] = mapped_column(String(20), primary_key=True)
    observation_date: Mapped[date] = mapped_column(Date)
    feature_cutoff: Mapped[datetime] = mapped_column(DateTime)
    feature_version: Mapped[str] = mapped_column(String(20))
    recency_days: Mapped[float] = mapped_column(Float)
    frequency: Mapped[int] = mapped_column(Integer)
    monetary: Mapped[float] = mapped_column(Float)
    features: Mapped[dict] = mapped_column(JSONB)


class ChurnScore(Base):
    __tablename__ = "churn_scores"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "customer_key"],
            ["customer_snapshots.run_id", "customer_snapshots.customer_key"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("run_id", "risk_rank", name="uq_churn_rank"),
        CheckConstraint("churn_probability >= 0 AND churn_probability <= 1", name="ck_probability"),
        CheckConstraint("risk_band IN ('Very high', 'High', 'Medium', 'Low')", name="ck_risk_band"),
        Index("ix_churn_scores_rank", "run_id", "risk_rank"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), primary_key=True)
    customer_key: Mapped[str] = mapped_column(String(20), primary_key=True)
    observation_date: Mapped[date] = mapped_column(Date)
    model_version: Mapped[str] = mapped_column(String(100))
    cluster_id: Mapped[int] = mapped_column(Integer)
    churn_probability: Mapped[float] = mapped_column(Float)
    risk_rank: Mapped[int] = mapped_column(Integer)
    risk_percentile: Mapped[float] = mapped_column(Float)
    risk_band: Mapped[str] = mapped_column(String(20))
    in_top_decile: Mapped[bool] = mapped_column(Boolean)
    above_threshold: Mapped[bool] = mapped_column(Boolean)
    daily_revenue_rate: Mapped[float] = mapped_column(Float)
    projected_revenue: Mapped[float] = mapped_column(Float)
    projection_capped: Mapped[bool] = mapped_column(Boolean)
    expected_revenue_at_risk: Mapped[float] = mapped_column(Float)


class ModelMetric(Base):
    __tablename__ = "model_metrics"
    __table_args__ = (
        UniqueConstraint("run_id", "model_name", "evaluation_split", "config_index", name="uq_model_metric"),
        CheckConstraint("evaluation_split IN ('validation', 'test')", name="ck_eval_split"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(60))
    model_version: Mapped[str] = mapped_column(String(100))
    config_index: Mapped[int] = mapped_column(Integer)
    evaluation_split: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    is_selected: Mapped[bool] = mapped_column(Boolean)
    is_family_best: Mapped[bool] = mapped_column(Boolean)
    params: Mapped[dict] = mapped_column(JSONB)
    n: Mapped[int] = mapped_column(Integer)
    positives: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[float] = mapped_column(Float)
    recall: Mapped[float] = mapped_column(Float)
    precision: Mapped[float] = mapped_column(Float)
    f1: Mapped[float] = mapped_column(Float)
    roc_auc: Mapped[float] = mapped_column(Float)
    pr_auc: Mapped[float] = mapped_column(Float)
    brier: Mapped[float] = mapped_column(Float)
    tp: Mapped[int] = mapped_column(Integer)
    fp: Mapped[int] = mapped_column(Integer)
    tn: Mapped[int] = mapped_column(Integer)
    fn: Mapped[int] = mapped_column(Integer)
    top_precision: Mapped[float] = mapped_column(Float)
    top_capture_rate: Mapped[float] = mapped_column(Float)
    top_lift: Mapped[float] = mapped_column(Float)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class ModelCurve(Base):
    __tablename__ = "model_curves"
    __table_args__ = (CheckConstraint("curve_type IN ('roc', 'pr', 'calibration')", name="ck_curve_type"),)

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(60), primary_key=True)
    curve_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    points: Mapped[list] = mapped_column(JSONB)


class ShapGlobal(Base):
    __tablename__ = "shap_global"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), primary_key=True)
    feature: Mapped[str] = mapped_column(String(60), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    mean_abs_shap: Mapped[float] = mapped_column(Float)
    mean_shap: Mapped[float] = mapped_column(Float)
    value_shap_correlation: Mapped[float] = mapped_column(Float)
    direction: Mapped[str] = mapped_column(String(60))


class ShapLocal(Base):
    __tablename__ = "shap_local"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "customer_key"], ["churn_scores.run_id", "churn_scores.customer_key"], ondelete="CASCADE"
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), primary_key=True)
    customer_key: Mapped[str] = mapped_column(String(20), primary_key=True)
    feature: Mapped[str] = mapped_column(String(60), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer)
    feature_value: Mapped[float | None] = mapped_column(Float)
    shap_value: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)


class RetentionScenario(Base):
    __tablename__ = "retention_scenarios"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey(RUN_FK, ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    assumptions: Mapped[dict] = mapped_column(JSONB)
    results: Mapped[dict] = mapped_column(JSONB)
