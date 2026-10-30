"""Pydantic response models for the public API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]
    version: str


class RunInfo(BaseModel):
    run_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    code_version: str | None
    selected_k: int | None
    selected_model: str | None
    model_version: str | None
    scoring_cutoff: date | None
    error_summary: str | None = None


class Page(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class Kpi(BaseModel):
    eligible_customers: int
    segmented_customers: int
    segment_count: int
    churn_rate_test: float
    churn_rate_overall_snapshots: float
    selected_model: str
    test_roc_auc: float
    test_pr_auc: float
    test_recall: float
    top_decile_customers: int
    top_decile_capture_rate_test: float
    top_decile_lift_test: float
    expected_revenue_at_risk_top_decile: float
    expected_revenue_at_risk_all_scored: float
    currency: str


class Summary(BaseModel):
    run: RunInfo
    latest_attempt: RunInfo | None = Field(
        description="Most recent run of any status, if different from the served run"
    )
    dataset: dict[str, Any]
    kpis: Kpi
    segments: list[dict[str, Any]]
    risk_bands: list[dict[str, Any]]
    takeaway: str


class SegmentProfile(BaseModel):
    cluster_id: int
    segment_name: str
    recommended_action: str
    customers: int
    share: float
    revenue: float
    revenue_share: float
    levels: dict[str, Any]
    median: dict[str, float]
    mean: dict[str, float]
    quartiles: dict[str, list[float]]
    centroid: dict[str, float]


class SegmentsResponse(BaseModel):
    run_id: str
    selected_k: int
    silhouette: float
    selection_rule: str
    transform: str
    population: str
    k_table: list[dict[str, Any]]
    pca_explained_variance: list[float]
    profiles: list[SegmentProfile]
    scatter: list[dict[str, Any]]
    population_quantiles: dict[str, Any]


class SegmentDetail(BaseModel):
    profile: SegmentProfile
    distributions: dict[str, list[dict[str, Any]]]
    scored_customers: int
    mean_churn_probability: float | None
    top_decile_customers: int


class CustomerRow(BaseModel):
    customer_key: str
    cluster_id: int
    segment_name: str
    churn_probability: float
    risk_rank: int
    risk_percentile: float
    risk_band: str
    in_top_decile: bool
    above_threshold: bool
    recency_days: float
    frequency: int
    monetary: float
    projected_revenue: float
    expected_revenue_at_risk: float


class CustomerList(BaseModel):
    meta: Page
    items: list[CustomerRow]


class Contribution(BaseModel):
    feature: str
    description: str
    feature_value: float | None
    shap_value: float
    rank: int
    explanation: str


class CustomerDetail(BaseModel):
    customer: CustomerRow
    features: dict[str, float | None]
    observation_date: date
    explanation: list[Contribution]
    explanation_available: bool
    note: str


class SimulationResult(BaseModel):
    assumptions: dict[str, Any]
    targeted_customers: int
    population: int
    average_risk: float
    projected_revenue: float
    expected_revenue_at_risk: float
    scenario_revenue_retained: float
    campaign_cost: float
    net_impact: float
    net_impact_basis: str
    break_even_effectiveness: float | None
    label: str
    season_factor: float
    currency: str
