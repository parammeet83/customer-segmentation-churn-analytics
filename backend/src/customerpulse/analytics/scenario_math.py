"""Dependency-free retention scenario maths used by the API.

Mirrors :func:`customerpulse.analytics.retention.simulate` (a test asserts
parity) without importing pandas/numpy, so the public API stays small.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

RANKINGS = ("risk", "value_at_risk")


@dataclass(frozen=True)
class CustomerRisk:
    customer_key: str
    churn_probability: float
    daily_revenue_rate: float


def top_k(n: int, fraction: float) -> int:
    return 0 if n == 0 else max(1, math.ceil(round(n * fraction, 9)))  # round: 30 * 0.1 must give 3, not 4


def simulate_rows(
    rows: Sequence[CustomerRisk],
    target_fraction: float,
    effectiveness: float,
    cost_per_contact: float,
    horizon_days: int,
    margin: float = 1.0,
    ranking: str = "risk",
    season: float = 1.0,
) -> dict:
    if ranking not in RANKINGS:
        raise ValueError(f"ranking must be one of {RANKINGS}")
    if ranking == "risk":
        ordered = sorted(rows, key=lambda r: (-r.churn_probability, r.customer_key))
    else:
        ordered = sorted(rows, key=lambda r: (-(r.churn_probability * r.daily_revenue_rate), r.customer_key))
    top = ordered[: top_k(len(rows), target_fraction)]
    projected = [r.daily_revenue_rate * horizon_days * season for r in top]
    at_risk = sum(r.churn_probability * p for r, p in zip(top, projected, strict=True))
    retained = at_risk * effectiveness
    cost = len(top) * cost_per_contact
    return {
        "assumptions": {
            "target_fraction": target_fraction,
            "effectiveness": effectiveness,
            "cost_per_contact": cost_per_contact,
            "horizon_days": horizon_days,
            "margin": margin,
            "ranking": ranking,
        },
        "targeted_customers": len(top),
        "population": len(rows),
        "average_risk": sum(r.churn_probability for r in top) / len(top) if top else 0.0,
        "projected_revenue": sum(projected),
        "expected_revenue_at_risk": at_risk,
        "scenario_revenue_retained": retained,
        "campaign_cost": float(cost),
        "net_impact": retained * margin - cost,
        "net_impact_basis": "revenue" if margin == 1.0 else "gross margin",
        "break_even_effectiveness": cost / (at_risk * margin) if at_risk > 0 else None,
        "label": "Scenario estimate under stated assumptions - not observed savings",
    }
