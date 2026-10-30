import pandas as pd
import pytest

from customerpulse.features.rfm import customer_rfm
from customerpulse.features.snapshots import MODEL_FEATURES, build_features, invoice_table

from .conftest import empty_returns, make_purchases

CUTOFF = pd.Timestamp("2011-03-01")


@pytest.fixture
def purchases():
    return make_purchases(
        [
            # customer A: two invoices in window, three lines in the first
            ("A", "1", "2011-01-10 10:00", "X", 2, 5.0),
            ("A", "1", "2011-01-10 10:00", "Y", 1, 10.0),
            ("A", "1", "2011-01-10 10:00", "Z", 4, 1.0),
            ("A", "2", "2011-02-20 09:00", "X", 1, 5.0),
            ("A", "0", "2010-06-01 09:00", "X", 1, 5.0),  # before lookback
            # customer B: only purchased long before the lookback window
            ("B", "3", "2010-05-01 10:00", "X", 1, 5.0),
            # future purchases that must never enter features
            ("A", "9", "2011-03-01 00:00", "X", 100, 100.0),
            ("C", "8", "2011-03-15 10:00", "X", 1, 5.0),
        ]
    )


def test_frequency_counts_distinct_invoices_not_lines(purchases):
    f = build_features(purchases, empty_returns(), CUTOFF, 180).set_index("customer_id")
    assert f.loc["A", "frequency"] == 2
    assert f.loc["A", "frequency_lifetime"] == 3


def test_monetary_and_recency(purchases):
    f = build_features(purchases, empty_returns(), CUTOFF, 180).set_index("customer_id")
    assert f.loc["A", "monetary"] == pytest.approx(10 + 10 + 4 + 5)
    assert f.loc["A", "recency_days"] == pytest.approx(
        (CUTOFF - pd.Timestamp("2011-02-20 09:00")).total_seconds() / 86400
    )
    assert f.loc["A", "distinct_products"] == 3
    assert f.loc["A", "avg_order_value"] == pytest.approx(29 / 2)


def test_only_customers_active_in_lookback_are_eligible(purchases):
    f = build_features(purchases, empty_returns(), CUTOFF, 180)
    assert list(f["customer_id"]) == ["A"]


def test_no_future_transactions_enter_features(purchases):
    """A transaction at exactly the cutoff (or later) must not change features."""
    base = build_features(purchases[purchases["invoice_date"] < CUTOFF], empty_returns(), CUTOFF, 180)
    full = build_features(purchases, empty_returns(), CUTOFF, 180)
    pd.testing.assert_frame_equal(base, full)
    assert (full["last_purchase"] < CUTOFF).all()


def test_returns_tracked_separately(purchases):
    returns = make_purchases([("A", "C1", "2011-02-01 10:00", "X", 1, 5.0)])
    f = build_features(purchases, returns, CUTOFF, 180).set_index("customer_id")
    assert f.loc["A", "frequency"] == 2  # unchanged by the return
    assert f.loc["A", "return_value"] == pytest.approx(5.0)
    assert f.loc["A", "return_rate"] == pytest.approx(5.0 / 29)


def test_cutoff_must_be_midnight(purchases):
    with pytest.raises(ValueError):
        build_features(purchases, empty_returns(), pd.Timestamp("2011-03-01 12:00"), 180)


def test_model_features_exclude_identifiers_and_labels():
    banned = {
        "customer_id",
        "customer_key",
        "churned",
        "cutoff",
        "label_window_end",
        "last_purchase",
        "first_purchase",
        "country",
    }
    assert not banned & set(MODEL_FEATURES)


def test_features_are_finite_or_documented_missing(purchases):
    f = build_features(purchases, empty_returns(), CUTOFF, 180)
    allowed_missing = {"mean_gap_days", "std_gap_days", "recency_to_gap_ratio"}
    for col in MODEL_FEATURES:
        if col not in allowed_missing:
            assert f[col].notna().all(), col


def test_customer_rfm_uses_all_history_before_cutoff(purchases):
    rfm = customer_rfm(invoice_table(purchases), CUTOFF).set_index("customer_id")
    assert set(rfm.index) == {"A", "B"}
    assert rfm.loc["A", "frequency"] == 3
    assert rfm.loc["B", "recency_days"] > 300
