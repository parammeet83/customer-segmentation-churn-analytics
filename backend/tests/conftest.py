"""Shared synthetic fixtures. Tests never need the real dataset."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from dotenv import load_dotenv

from customerpulse.config import REPO_ROOT

# Local runs read the git-ignored .env; CI provides the same variables directly.
load_dotenv(REPO_ROOT / ".env")


def raw_row(invoice, stock, qty, date, price, cust, country="United Kingdom", sheet="Year 2010-2011", desc="ITEM"):
    return {
        "Invoice": invoice,
        "StockCode": stock,
        "Description": desc,
        "Quantity": qty,
        "InvoiceDate": pd.Timestamp(date),
        "Price": price,
        "Customer ID": cust,
        "Country": country,
        "source_sheet": sheet,
    }


@pytest.fixture
def raw_small() -> pd.DataFrame:
    rows = [
        raw_row("536365", "85123A", 6, "2011-01-05 10:00", 2.55, 17850.0),
        raw_row("536365", "71053", 6, "2011-01-05 10:00", 3.39, 17850.0),
        raw_row("536365", "71053", 6, "2011-01-05 10:00", 3.39, 17850.0),  # exact duplicate
        raw_row("536366", "22633", 4, "2011-01-06 11:00", 1.85, None),  # missing customer
        raw_row("C536367", "85123A", -2, "2011-01-07 12:00", 2.55, 17850.0),  # cancellation
        raw_row("536368", "POST", 1, "2011-01-08 12:00", 18.0, 12583.0),  # postage
        raw_row("536368", "22728", 24, "2011-01-08 12:00", 3.75, 12583.0),
        raw_row("536369", "22728", 3, "2011-01-09 12:00", 0.0, 12583.0),  # zero price
        raw_row("A563185", "B", 1, "2011-01-10 12:00", -11062.06, None),  # bad debt adj.
        raw_row("536370", "22728", -5, "2011-01-11 12:00", 0.0, None),  # stock adjustment
        # Sheet-overlap duplicate of an early-December invoice
        raw_row("536000", "22728", 2, "2010-12-02 09:00", 3.75, 12583.0, sheet="Year 2009-2010"),
        raw_row("536000", "22728", 2, "2010-12-02 09:00", 3.75, 12583.0, sheet="Year 2010-2011"),
    ]
    return pd.DataFrame(rows)


def make_purchases(rows: list[tuple]) -> pd.DataFrame:
    """rows: (customer_id, invoice, date, stock_code, quantity, price)."""
    df = pd.DataFrame(rows, columns=["customer_id", "invoice", "invoice_date", "stock_code", "quantity", "price"])
    df["invoice_date"] = pd.to_datetime(df["invoice_date"], format="mixed")
    df["line_value"] = df["quantity"] * df["price"]
    df["country"] = "United Kingdom"
    return df


def empty_returns() -> pd.DataFrame:
    return make_purchases([]).astype({"quantity": float, "price": float, "line_value": float})


def simulate_purchases() -> pd.DataFrame:
    """Two years of synthetic purchases with heterogeneous purchase rates.

    Some customers stop buying part-way through, so the inactivity label is
    learnable from recency/frequency features.
    """
    rng = np.random.default_rng(7)
    rows = []
    inv = 100000
    start = pd.Timestamp("2009-12-01")
    for c in range(400):
        rate = rng.choice([0.01, 0.03, 0.08])  # purchases per day
        stop = start + pd.Timedelta(days=int(rng.integers(120, 740)))
        t = start + pd.Timedelta(days=float(rng.exponential(1 / rate)))
        while t < min(stop, pd.Timestamp("2011-12-09")):
            inv += 1
            for _ in range(int(rng.integers(1, 4))):
                rows.append(
                    (
                        str(10000 + c),
                        str(inv),
                        t.floor("min"),
                        f"S{int(rng.integers(50))}",
                        int(rng.integers(1, 12)),
                        float(rng.choice([1.25, 2.5, 4.95])),
                    )
                )
            t += pd.Timedelta(days=float(rng.exponential(1 / rate)))
    return make_purchases(rows)


@pytest.fixture
def simulated_purchases() -> pd.DataFrame:
    return simulate_purchases()
