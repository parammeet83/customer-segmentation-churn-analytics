"""Structural validation of the raw transaction table (Pandera).

Validation checks *structure* (columns, types, value domains that must hold
for every row). Business rules such as "exclude cancellations" belong to the
cleaning stage, which reports counts instead of failing.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa

RAW_SCHEMA = pa.DataFrameSchema(
    {
        "Invoice": pa.Column(str, pa.Check.str_matches(r"^[CA]?\d{6}$"), nullable=False),
        "StockCode": pa.Column(str, nullable=False),
        "Description": pa.Column(str, nullable=True),
        "Quantity": pa.Column(int, nullable=False),
        "InvoiceDate": pa.Column("datetime64[us]", nullable=False, coerce=True),
        "Price": pa.Column(float, nullable=False),
        "Customer ID": pa.Column(float, pa.Check.between(10000, 99999), nullable=True),
        "Country": pa.Column(str, nullable=False),
        "source_sheet": pa.Column(str, pa.Check.isin(["Year 2009-2010", "Year 2010-2011"])),
    },
    strict=True,
)


def validate_raw(df: pd.DataFrame) -> dict:
    """Validate and return a summary; raises ``SchemaErrors`` on failure."""
    RAW_SCHEMA.validate(df, lazy=True)
    return {
        "status": "passed",
        "rows": int(len(df)),
        "columns": list(df.columns),
        "date_min": str(df["InvoiceDate"].min()),
        "date_max": str(df["InvoiceDate"].max()),
        "null_counts": {c: int(v) for c, v in df.isna().sum().items()},
        "distinct_invoices": int(df["Invoice"].nunique()),
        "distinct_customers": int(df["Customer ID"].nunique()),
        "distinct_stock_codes": int(df["StockCode"].nunique()),
        "countries": int(df["Country"].nunique()),
    }
