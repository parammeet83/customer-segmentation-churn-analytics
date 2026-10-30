import pandas as pd
import pytest

from customerpulse.cleaning.clean import EXCLUSION_REASONS, clean
from customerpulse.ingestion.validate import validate_raw


def test_every_raw_row_is_accounted_for(raw_small):
    r = clean(raw_small)
    assert len(r.purchases) + len(r.returns) + sum(r.excluded_counts.values()) == len(raw_small)
    assert set(r.excluded_counts) == set(EXCLUSION_REASONS)


def test_exclusion_reasons(raw_small):
    c = clean(raw_small).excluded_counts
    assert c["sheet_overlap_duplicate"] == 1
    assert c["exact_duplicate_line"] == 1
    # 536366 (missing id), A563185 (bad debt), 536370 (stock adjustment) all lack a customer
    assert c["missing_customer_id"] == 3
    assert c["non_merchandise_code"] == 1  # POST
    assert c["non_positive_price"] == 1


def test_purchases_and_returns_are_separate(raw_small):
    r = clean(raw_small)
    assert not r.purchases["invoice"].str.startswith("C").any()
    assert r.returns["invoice"].str.startswith("C").all()
    assert (r.returns["quantity"] > 0).all() and (r.returns["line_value"] > 0).all()
    assert r.returns["line_value"].sum() == pytest.approx(2 * 2.55)


def test_purchase_values_and_identifiers(raw_small):
    r = clean(raw_small)
    p = r.purchases
    assert (p["quantity"] > 0).all() and (p["price"] > 0).all()
    assert p["customer_id"].notna().all()
    assert set(p["customer_id"]) == {"17850", "12583"}  # float IDs normalised to strings
    assert p["line_value"].sum() == pytest.approx(6 * 2.55 + 6 * 3.39 + 24 * 3.75 + 2 * 3.75)


def test_cleaning_is_deterministic(raw_small):
    a, b = clean(raw_small), clean(raw_small.sample(frac=1, random_state=1))
    pd.testing.assert_frame_equal(a.purchases, b.purchases)


def test_invalid_date_is_excluded(raw_small):
    df = raw_small.copy()
    df["InvoiceDate"] = df["InvoiceDate"].astype(object)
    df.loc[0, "InvoiceDate"] = "not a date"
    assert clean(df).excluded_counts["invalid_invoice_date"] == 1


def test_validation_rejects_bad_invoice_codes(raw_small):
    validate_raw(raw_small.astype({"InvoiceDate": "datetime64[us]"}))
    bad = raw_small.copy()
    bad.loc[0, "Invoice"] = "XYZ"
    with pytest.raises(Exception):
        validate_raw(bad)
