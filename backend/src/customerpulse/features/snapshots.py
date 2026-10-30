"""Point-in-time customer features and behavioural inactivity labels.

Conventions (tested in ``tests/test_features.py`` and ``tests/test_leakage.py``):

* ``cutoff`` is a midnight timestamp. Features only use transactions with
  ``invoice_date < cutoff``.
* The label window is ``[cutoff, cutoff + horizon_days)``. A customer is
  labelled ``churned = 1`` when they make no qualifying purchase in it.
* A customer is eligible at a cutoff only if they made at least one
  qualifying purchase in the lookback window ``[cutoff - lookback, cutoff)``.
* Labels are only produced when the full label window lies inside the data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Model features. Customer identifiers, dates and labels are never included.
MODEL_FEATURES: tuple[str, ...] = (
    "recency_days",
    "frequency",
    "monetary",
    "avg_order_value",
    "total_units",
    "distinct_products",
    "active_months",
    "frequency_per_active_month",
    "frequency_lifetime",
    "monetary_lifetime",
    "tenure_days",
    "mean_gap_days",
    "std_gap_days",
    "recency_to_gap_ratio",
    "spend_last_90",
    "spend_prev_90",
    "spend_trend",
    "frequency_last_90",
    "frequency_prev_90",
    "frequency_trend",
    "return_value",
    "return_rate",
    "is_uk",
)

FEATURE_DESCRIPTIONS: dict[str, str] = {
    "recency_days": "Days since the customer's most recent purchase",
    "frequency": "Distinct purchase invoices in the last 180 days",
    "monetary": "Gross merchandise spend in the last 180 days (GBP)",
    "avg_order_value": "Average spend per invoice in the last 180 days (GBP)",
    "total_units": "Units purchased in the last 180 days",
    "distinct_products": "Distinct products purchased in the last 180 days",
    "active_months": "Calendar months with a purchase in the last 180 days",
    "frequency_per_active_month": "Invoices per active month in the last 180 days",
    "frequency_lifetime": "Distinct purchase invoices since the data begins",
    "monetary_lifetime": "Gross merchandise spend since the data begins (GBP)",
    "tenure_days": "Days since first observed purchase (data starts Dec 2009)",
    "mean_gap_days": "Average days between purchase days (needs 2+ purchase days)",
    "std_gap_days": "Variation in days between purchase days",
    "recency_to_gap_ratio": "Days since last purchase relative to the usual gap",
    "spend_last_90": "Spend in the most recent 90 days (GBP)",
    "spend_prev_90": "Spend in the 90 days before that (GBP)",
    "spend_trend": "Log change in spend: last 90 days vs the previous 90",
    "frequency_last_90": "Invoices in the most recent 90 days",
    "frequency_prev_90": "Invoices in the 90 days before that",
    "frequency_trend": "Change in invoice count: last 90 days minus previous 90",
    "return_value": "Value of cancelled/returned lines in the last 180 days (GBP)",
    "return_rate": "Returned value as a share of gross spend in the last 180 days",
    "is_uk": "Customer's most frequent country is the United Kingdom",
}

DAY = pd.Timedelta(days=1)


def invoice_table(purchases: pd.DataFrame) -> pd.DataFrame:
    """Collapse purchase lines into one row per (customer, invoice)."""
    inv = (
        purchases.groupby(["customer_id", "invoice"], sort=False, observed=True)
        .agg(
            invoice_date=("invoice_date", "min"),
            value=("line_value", "sum"),
            units=("quantity", "sum"),
            country=("country", "first"),
        )
        .reset_index()
    )
    return inv.sort_values(["customer_id", "invoice_date"], kind="mergesort").reset_index(drop=True)


def _gap_stats(inv_hist: pd.DataFrame) -> pd.DataFrame:
    """Mean/std of gaps (days) between distinct purchase days per customer."""
    days = (
        inv_hist.assign(day=inv_hist["invoice_date"].dt.normalize())[["customer_id", "day"]]
        .drop_duplicates()
        .sort_values(["customer_id", "day"], kind="mergesort")
    )
    days["gap"] = days.groupby("customer_id")["day"].diff().dt.days
    g = days.dropna(subset=["gap"]).groupby("customer_id")["gap"]
    out = pd.DataFrame({"mean_gap_days": g.mean(), "std_gap_days": g.std(ddof=0)})
    return out


def build_features(
    purchases: pd.DataFrame,
    returns: pd.DataFrame,
    cutoff: pd.Timestamp,
    lookback_days: int = 180,
    invoices: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Customer features at ``cutoff`` using only transactions before it."""
    cutoff = pd.Timestamp(cutoff)
    if cutoff != cutoff.normalize():
        raise ValueError("cutoff must be a midnight timestamp")
    inv_all = invoices if invoices is not None else invoice_table(purchases)
    hist = inv_all[inv_all["invoice_date"] < cutoff]
    start = cutoff - lookback_days * DAY
    mid = cutoff - 90 * DAY
    win = hist[hist["invoice_date"] >= start]
    eligible = win["customer_id"].unique()
    if len(eligible) == 0:
        return pd.DataFrame(columns=["customer_id", *MODEL_FEATURES])

    hist = hist[hist["customer_id"].isin(eligible)]
    lines = purchases[
        (purchases["invoice_date"] >= start)
        & (purchases["invoice_date"] < cutoff)
        & purchases["customer_id"].isin(eligible)
    ]

    g_win = win.groupby("customer_id")
    f = pd.DataFrame(
        {
            "frequency": g_win["invoice"].nunique(),
            "monetary": g_win["value"].sum(),
            "total_units": g_win["units"].sum(),
            "active_months": g_win["invoice_date"].agg(lambda s: s.dt.to_period("M").nunique()),
        }
    )
    g_hist = hist.groupby("customer_id")
    f["last_purchase"] = g_hist["invoice_date"].max()
    f["first_purchase"] = g_hist["invoice_date"].min()
    f["frequency_lifetime"] = g_hist["invoice"].nunique()
    f["monetary_lifetime"] = g_hist["value"].sum()
    f["country"] = g_hist["country"].agg(lambda s: s.mode().iat[0])
    f["distinct_products"] = lines.groupby("customer_id")["stock_code"].nunique()

    recent = win[win["invoice_date"] >= mid].groupby("customer_id")
    prior = win[win["invoice_date"] < mid].groupby("customer_id")
    f["spend_last_90"] = recent["value"].sum()
    f["spend_prev_90"] = prior["value"].sum()
    f["frequency_last_90"] = recent["invoice"].nunique()
    f["frequency_prev_90"] = prior["invoice"].nunique()
    fill0 = ["spend_last_90", "spend_prev_90", "frequency_last_90", "frequency_prev_90", "distinct_products"]
    f[fill0] = f[fill0].fillna(0)

    ret = returns[
        (returns["invoice_date"] >= start) & (returns["invoice_date"] < cutoff) & returns["customer_id"].isin(eligible)
    ]
    f["return_value"] = ret.groupby("customer_id")["line_value"].sum()
    f["return_value"] = f["return_value"].fillna(0.0)

    f = f.join(_gap_stats(hist))

    f["recency_days"] = (cutoff - f["last_purchase"]) / DAY
    f["tenure_days"] = (cutoff - f["first_purchase"]) / DAY
    f["avg_order_value"] = f["monetary"] / f["frequency"]
    f["frequency_per_active_month"] = f["frequency"] / f["active_months"]
    f["recency_to_gap_ratio"] = f["recency_days"] / f["mean_gap_days"].where(f["mean_gap_days"] > 0)
    f["spend_trend"] = np.log1p(f["spend_last_90"]) - np.log1p(f["spend_prev_90"])
    f["frequency_trend"] = f["frequency_last_90"] - f["frequency_prev_90"]
    f["return_rate"] = (f["return_value"] / f["monetary"]).clip(upper=1.0)
    f["is_uk"] = (f["country"] == "United Kingdom").astype(int)

    f = f.reset_index().rename(columns={"index": "customer_id"})
    f["cutoff"] = cutoff
    f["lookback_start"] = start
    cols = ["customer_id", "cutoff", "lookback_start", "last_purchase", "first_purchase", "country", *MODEL_FEATURES]
    return f[cols].sort_values("customer_id", kind="mergesort").reset_index(drop=True)


def label_churn(
    invoices: pd.DataFrame,
    customers: pd.Series,
    cutoff: pd.Timestamp,
    horizon_days: int,
    data_end: pd.Timestamp,
) -> pd.Series:
    """1 if the customer has no purchase in ``[cutoff, cutoff+horizon)``.

    Raises if the label window is not fully covered by the data.
    """
    cutoff = pd.Timestamp(cutoff)
    window_end = cutoff + horizon_days * DAY
    if window_end > data_end:
        raise ValueError(f"Label window ending {window_end.date()} exceeds data end {data_end.date()}")
    fut = invoices[(invoices["invoice_date"] >= cutoff) & (invoices["invoice_date"] < window_end)]
    active = set(fut["customer_id"].unique())
    return customers.map(lambda c: 0 if c in active else 1).astype(int)


def data_end_of(purchases: pd.DataFrame) -> pd.Timestamp:
    """Exclusive end of observed data: midnight after the last purchase day."""
    return purchases["invoice_date"].max().normalize() + DAY


def snapshot_cutoffs(first_snapshot: str, data_end: pd.Timestamp, horizon_days: int) -> list[pd.Timestamp]:
    """Monthly cutoffs whose full label window is inside the data."""
    out = []
    for c in pd.date_range(first_snapshot, data_end, freq="MS"):
        if c + horizon_days * DAY <= data_end:
            out.append(c)
    return out


def build_training_snapshots(
    purchases: pd.DataFrame,
    returns: pd.DataFrame,
    cutoffs: list[pd.Timestamp],
    lookback_days: int,
    horizon_days: int,
) -> pd.DataFrame:
    """Stack labelled snapshots for every cutoff."""
    invoices = invoice_table(purchases)
    data_end = data_end_of(purchases)
    frames = []
    for c in cutoffs:
        feats = build_features(purchases, returns, c, lookback_days, invoices)
        feats["label_window_end"] = c + horizon_days * DAY
        feats["churned"] = label_churn(invoices, feats["customer_id"], c, horizon_days, data_end).values
        frames.append(feats)
    return pd.concat(frames, ignore_index=True)


def horizon_sensitivity(
    purchases: pd.DataFrame,
    returns: pd.DataFrame,
    first_snapshot: str,
    lookback_days: int,
    horizons: tuple[int, ...],
) -> list[dict]:
    """Churn rate and coverage for alternative inactivity horizons."""
    invoices = invoice_table(purchases)
    data_end = data_end_of(purchases)
    rows = []
    for h in horizons:
        cutoffs = snapshot_cutoffs(first_snapshot, data_end, h)
        rates, n = [], 0
        for c in cutoffs:
            feats = build_features(purchases, returns, c, lookback_days, invoices)
            y = label_churn(invoices, feats["customer_id"], c, h, data_end)
            rates.append(float(y.mean()))
            n += len(y)
        rows.append(
            {
                "horizon_days": h,
                "n_snapshots": len(cutoffs),
                "n_observations": n,
                "first_cutoff": str(cutoffs[0].date()) if cutoffs else None,
                "last_cutoff": str(cutoffs[-1].date()) if cutoffs else None,
                "mean_churn_rate": round(float(np.mean(rates)), 4) if rates else None,
                "min_churn_rate": round(float(np.min(rates)), 4) if rates else None,
                "max_churn_rate": round(float(np.max(rates)), 4) if rates else None,
            }
        )
    return rows
