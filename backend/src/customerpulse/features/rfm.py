"""Customer-base RFM table used for K-Means segmentation.

Segmentation describes the whole known customer base at the scoring date,
so it uses every qualifying purchase before the cutoff (not just the 180-day
churn lookback). That lets long-inactive customers appear as their own
segment instead of disappearing from the analysis.
"""

from __future__ import annotations

import pandas as pd

from customerpulse.features.snapshots import DAY

RFM_COLUMNS = ("recency_days", "frequency", "monetary")


def customer_rfm(invoices: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Lifetime RFM + tenure for every customer with a purchase before cutoff."""
    cutoff = pd.Timestamp(cutoff)
    hist = invoices[invoices["invoice_date"] < cutoff]
    g = hist.groupby("customer_id")
    out = pd.DataFrame(
        {
            "last_purchase": g["invoice_date"].max(),
            "first_purchase": g["invoice_date"].min(),
            "frequency": g["invoice"].nunique(),
            "monetary": g["value"].sum(),
        }
    )
    out["recency_days"] = (cutoff - out["last_purchase"]) / DAY
    out["tenure_days"] = (cutoff - out["first_purchase"]) / DAY
    out["avg_order_value"] = out["monetary"] / out["frequency"]
    out = out.reset_index().rename(columns={"index": "customer_id"})
    return out.sort_values("customer_id", kind="mergesort").reset_index(drop=True)
