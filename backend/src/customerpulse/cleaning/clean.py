"""Deterministic cleaning of Online Retail II transaction lines.

Every raw row ends up in exactly one of three places:

* ``purchases``  - qualifying merchandise purchase lines (drive R, F and M)
* ``returns``    - cancellation lines for identified customers (tracked separately)
* ``excluded``   - everything else, with the first matching exclusion reason

Purchases and returns are kept apart so that refunds never inflate or
deflate purchase frequency. The rules are applied in a fixed priority order
and the counts are written to the cleaning report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

OVERLAP_SHEET = "Year 2010-2011"
OVERLAP_END = pd.Timestamp("2010-12-10")

# Stock codes that are fees, postage, manual adjustments or tests rather than
# merchandise. Matched case-insensitively after stripping whitespace.
NON_MERCHANDISE_CODES = frozenset(
    {
        "POST",
        "DOT",
        "C2",
        "C3",
        "M",
        "D",
        "S",
        "B",
        "BANK CHARGES",
        "ADJUST",
        "ADJUST2",
        "AMAZONFEE",
        "CRUK",
        "PADS",
        "TEST001",
        "TEST002",
    }
)

# Priority-ordered exclusion reasons (first match wins).
EXCLUSION_REASONS = (
    "sheet_overlap_duplicate",
    "exact_duplicate_line",
    "invalid_invoice_date",
    "missing_customer_id",
    "missing_stock_code",
    "adjustment_invoice",
    "non_merchandise_code",
    "non_positive_price",
    "non_cancellation_negative_quantity",
    "cancellation_positive_quantity",
    "zero_quantity",
)


@dataclass
class CleaningResult:
    purchases: pd.DataFrame
    returns: pd.DataFrame
    excluded_counts: dict[str, int]
    report: dict = field(default_factory=dict)


def normalise(raw: pd.DataFrame) -> pd.DataFrame:
    """Rename to snake_case and normalise identifier types."""
    df = raw.rename(
        columns={
            "Invoice": "invoice",
            "StockCode": "stock_code",
            "Description": "description",
            "Quantity": "quantity",
            "InvoiceDate": "invoice_date",
            "Price": "price",
            "Customer ID": "customer_id",
            "Country": "country",
        }
    ).copy()
    df["invoice"] = df["invoice"].astype("string").str.strip().str.upper()
    df["stock_code"] = df["stock_code"].astype("string").str.strip().str.upper()
    df["country"] = df["country"].astype("string").str.strip()
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="coerce", format="mixed")
    cid = pd.to_numeric(df["customer_id"], errors="coerce")
    df["customer_id"] = cid.astype("Int64").astype("string")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    return df


def assign_exclusions(df: pd.DataFrame) -> pd.Series:
    """Return a Series of the first-matching exclusion reason (NA if kept)."""
    reason = pd.Series(pd.NA, index=df.index, dtype="string")

    def mark(mask: pd.Series, name: str) -> None:
        m = mask.fillna(False) & reason.isna()
        reason[m] = name

    business_cols = [
        "invoice",
        "stock_code",
        "description",
        "quantity",
        "invoice_date",
        "price",
        "customer_id",
        "country",
    ]
    if "source_sheet" in df.columns:
        mark(
            (df["source_sheet"] == OVERLAP_SHEET) & (df["invoice_date"] < OVERLAP_END),
            "sheet_overlap_duplicate",
        )
    kept = reason.isna()
    dup = pd.Series(False, index=df.index)
    dup[kept] = df.loc[kept, business_cols].duplicated(keep="first")
    mark(dup, "exact_duplicate_line")
    mark(df["invoice_date"].isna(), "invalid_invoice_date")
    mark(df["customer_id"].isna(), "missing_customer_id")
    mark(df["stock_code"].isna() | (df["stock_code"] == ""), "missing_stock_code")
    mark(df["invoice"].str.startswith("A"), "adjustment_invoice")
    mark(df["stock_code"].isin(NON_MERCHANDISE_CODES), "non_merchandise_code")
    mark(df["price"].isna() | (df["price"] <= 0), "non_positive_price")
    is_cancel = df["invoice"].str.startswith("C")
    mark(~is_cancel & (df["quantity"] < 0), "non_cancellation_negative_quantity")
    mark(is_cancel & (df["quantity"] > 0), "cancellation_positive_quantity")
    mark(df["quantity"].isna() | (df["quantity"] == 0), "zero_quantity")
    return reason


def clean(raw: pd.DataFrame) -> CleaningResult:
    df = normalise(raw)
    reason = assign_exclusions(df)
    kept = df[reason.isna()].copy()
    kept["line_value"] = kept["quantity"] * kept["price"]
    is_cancel = kept["invoice"].str.startswith("C")

    purchases = kept[~is_cancel].copy()
    returns = kept[is_cancel].copy()
    returns["quantity"] = returns["quantity"].abs()
    returns["line_value"] = returns["line_value"].abs()

    cols = [
        "invoice",
        "stock_code",
        "quantity",
        "invoice_date",
        "price",
        "line_value",
        "customer_id",
        "country",
    ]
    purchases = purchases[cols].sort_values(["invoice_date", "invoice", "stock_code"], kind="mergesort")
    returns = returns[cols].sort_values(["invoice_date", "invoice", "stock_code"], kind="mergesort")
    purchases = purchases.reset_index(drop=True)
    returns = returns.reset_index(drop=True)

    counts = {r: int((reason == r).sum()) for r in EXCLUSION_REASONS}
    report = build_report(df, purchases, returns, counts)
    return CleaningResult(purchases=purchases, returns=returns, excluded_counts=counts, report=report)


def build_report(
    df: pd.DataFrame,
    purchases: pd.DataFrame,
    returns: pd.DataFrame,
    counts: dict[str, int],
) -> dict:
    n = len(df)
    excluded = sum(counts.values())
    if excluded + len(purchases) + len(returns) != n:
        raise AssertionError("Cleaning accounting does not reconcile with raw row count")
    profile = {
        "raw_rows": n,
        "missing_customer_id_rows": int(df["customer_id"].isna().sum()),
        "missing_description_rows": int(df["description"].isna().sum()),
        "cancellation_rows": int(df["invoice"].str.startswith("C").sum()),
        "negative_quantity_rows": int((df["quantity"] < 0).sum()),
        "zero_or_negative_price_rows": int((df["price"] <= 0).sum()),
        "invalid_date_rows": int(df["invoice_date"].isna().sum()),
        "countries": int(df["country"].nunique()),
        "raw_customer_ids": int(df["customer_id"].nunique()),
    }
    monthly = purchases.set_index("invoice_date")["line_value"].resample("MS").sum().round(2)
    return {
        "profile": profile,
        "exclusions": [{"reason": r, "rows": c, "share_of_raw": round(c / n, 6)} for r, c in counts.items()],
        "output": {
            "purchase_lines": int(len(purchases)),
            "purchase_invoices": int(purchases["invoice"].nunique()),
            "purchase_customers": int(purchases["customer_id"].nunique()),
            "gross_purchase_value": round(float(purchases["line_value"].sum()), 2),
            "return_lines": int(len(returns)),
            "return_invoices": int(returns["invoice"].nunique()),
            "return_value": round(float(returns["line_value"].sum()), 2),
            "date_min": str(purchases["invoice_date"].min()),
            "date_max": str(purchases["invoice_date"].max()),
            "uk_share_of_purchase_lines": round(float((purchases["country"] == "United Kingdom").mean()), 4),
        },
        "monthly_purchase_value": [{"month": str(k.date()), "value": float(v)} for k, v in monthly.items()],
        "line_value_quantiles": {
            str(q): round(float(np.quantile(purchases["line_value"], q)), 2) for q in (0.5, 0.9, 0.99, 0.999)
        },
    }
