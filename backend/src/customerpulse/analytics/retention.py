"""Revenue projection, top-risk cohort selection and retention scenarios.

All monetary outputs here are *scenario estimates* driven by explicit
assumptions. The dataset contains no retention campaign or intervention
outcome, so nothing in this module measures revenue actually saved.

Formulas
--------
daily_rate_i          = min(gross qualifying spend in lookback / lookback days, cap)
                        (cap = a high quantile of the daily rate, limiting outliers)
projected_revenue_i   = daily_rate_i * horizon * seasonal_factor
revenue_at_risk_i     = p_i * projected_revenue_i
retained (scenario)   = sum(revenue_at_risk_i over targeted) * effectiveness
campaign_cost         = n_targeted * cost_per_contact
net_impact            = retained * margin - campaign_cost
                        (margin = 1.0 means a revenue-basis comparison, not profit)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from customerpulse.churn.evaluate import rank_order, top_k_count

DAY = pd.Timedelta(days=1)
RANKINGS = ("risk", "value_at_risk")


def seasonal_factor(invoices: pd.DataFrame, cutoff: pd.Timestamp, lookback_days: int, horizon_days: int) -> dict:
    """Ratio of one-year-earlier horizon revenue to one-year-earlier lookback revenue.

    Uses only data before ``cutoff``: the same calendar windows shifted back
    one year. If that history is unavailable the factor is 1.0.
    """
    cutoff = pd.Timestamp(cutoff)
    prior = cutoff - pd.DateOffset(years=1)
    look_start = prior - lookback_days * DAY
    horizon_end = prior + horizon_days * DAY
    if look_start < invoices["invoice_date"].min() or horizon_end > cutoff:
        return {"factor": 1.0, "available": False}
    d = invoices["invoice_date"]
    lookback_rev = invoices.loc[(d >= look_start) & (d < prior), "value"].sum()
    horizon_rev = invoices.loc[(d >= prior) & (d < horizon_end), "value"].sum()
    lookback_daily = lookback_rev / lookback_days
    horizon_daily = horizon_rev / horizon_days
    return {
        "factor": float(horizon_daily / lookback_daily) if lookback_daily > 0 else 1.0,
        "available": True,
        "reference_lookback": [str(look_start.date()), str(prior.date())],
        "reference_horizon": [str(prior.date()), str(horizon_end.date())],
    }


def project_revenue(
    features: pd.DataFrame,
    lookback_days: int,
    horizon_days: int,
    season: float,
    cap_quantile: float,
) -> pd.DataFrame:
    out = features[["customer_key", "monetary"]].copy()
    raw_rate = out["monetary"] / lookback_days
    cap = float(raw_rate.quantile(cap_quantile))
    out["daily_revenue_rate"] = raw_rate.clip(upper=cap)
    out["projection_capped"] = raw_rate > cap
    out["projected_revenue"] = out["daily_revenue_rate"] * horizon_days * season
    out.attrs["daily_rate_cap"] = cap
    return out


@dataclass(frozen=True)
class ScenarioAssumptions:
    target_fraction: float = 0.10
    effectiveness: float = 0.10
    cost_per_contact: float = 3.0
    horizon_days: int = 90
    margin: float = 1.0
    # "risk": rank by churn probability (the default top-10%-at-risk cohort).
    # "value_at_risk": rank by probability x projected revenue.
    ranking: str = "risk"

    def validate(self) -> None:
        if not 0 < self.target_fraction <= 1:
            raise ValueError("target_fraction must be in (0, 1]")
        if not 0 <= self.effectiveness <= 1:
            raise ValueError("effectiveness must be in [0, 1]")
        if self.cost_per_contact < 0:
            raise ValueError("cost_per_contact must be >= 0")
        if not 1 <= self.horizon_days <= 365:
            raise ValueError("horizon_days must be in [1, 365]")
        if not 0 < self.margin <= 1:
            raise ValueError("margin must be in (0, 1]")
        if self.ranking not in RANKINGS:
            raise ValueError(f"ranking must be one of {RANKINGS}")


def select_top(scores: pd.DataFrame, fraction: float, ranking: str = "risk") -> pd.DataFrame:
    """Rows of the top fraction by the chosen ranking, tie-break on key."""
    k = top_k_count(len(scores), fraction)
    if ranking == "risk":
        key = scores["churn_probability"].to_numpy()
    elif ranking == "value_at_risk":
        key = (scores["churn_probability"] * scores["daily_revenue_rate"]).to_numpy()
    else:
        raise ValueError(f"ranking must be one of {RANKINGS}")
    idx = rank_order(key, scores["customer_key"].to_numpy())[:k]
    return scores.iloc[idx]


def simulate(
    scores: pd.DataFrame,
    a: ScenarioAssumptions,
    base_horizon_days: int,
    season: float = 1.0,
) -> dict:
    """Scenario economics for the targeted cohort.

    ``scores`` needs customer_key, churn_probability and daily_revenue_rate.
    The revenue horizon may differ from the churn horizon; the probability is
    still the model's ``base_horizon_days`` inactivity probability.
    """
    a.validate()
    top = select_top(scores, a.target_fraction, a.ranking)
    projected = top["daily_revenue_rate"].to_numpy() * a.horizon_days * season
    at_risk = float(np.sum(top["churn_probability"].to_numpy() * projected))
    retained = at_risk * a.effectiveness
    cost = len(top) * a.cost_per_contact
    net = retained * a.margin - cost
    return {
        "assumptions": asdict(a),
        "targeted_customers": int(len(top)),
        "population": int(len(scores)),
        "average_risk": float(top["churn_probability"].mean()),
        "projected_revenue": float(projected.sum()),
        "expected_revenue_at_risk": at_risk,
        "scenario_revenue_retained": retained,
        "campaign_cost": float(cost),
        "net_impact": float(net),
        "net_impact_basis": "revenue" if a.margin == 1.0 else "gross margin",
        "break_even_effectiveness": (float(cost / (at_risk * a.margin)) if at_risk > 0 else None),
        "label": "Scenario estimate under stated assumptions - not observed savings",
    }
