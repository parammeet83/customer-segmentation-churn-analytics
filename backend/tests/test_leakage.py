"""Temporal leakage safeguards for labels, splits, preprocessing and selection."""

import numpy as np
import pandas as pd
import pytest

from customerpulse.churn.models import make_model, run_churn_experiment
from customerpulse.churn.splits import TemporalSplit, assert_no_label_overlap, temporal_split
from customerpulse.features import snapshots as s

from .conftest import empty_returns, make_purchases, simulate_purchases

DAY = pd.Timedelta(days=1)


def test_label_is_one_only_without_purchase_in_window():
    p = make_purchases(
        [
            ("A", "1", "2011-01-10", "X", 1, 1.0),
            ("B", "2", "2011-01-10", "X", 1, 1.0),
            ("A", "3", "2011-03-15", "X", 1, 1.0),  # inside [Mar 1, May 30)
            ("B", "4", "2011-06-15", "X", 1, 1.0),  # after the window
            ("B", "5", "2011-12-01", "X", 1, 1.0),
        ]
    )
    inv = s.invoice_table(p)
    y = s.label_churn(inv, pd.Series(["A", "B"]), pd.Timestamp("2011-03-01"), 90, s.data_end_of(p))
    assert list(y) == [0, 1]


def test_label_window_boundary_is_exclusive():
    p = make_purchases(
        [
            ("A", "1", "2011-01-10", "X", 1, 1.0),
            ("A", "2", "2011-05-30 00:00", "X", 1, 1.0),
            ("A", "3", "2011-12-01", "X", 1, 1.0),
        ]
    )
    y = s.label_churn(s.invoice_table(p), pd.Series(["A"]), pd.Timestamp("2011-03-01"), 90, s.data_end_of(p))
    assert y.iat[0] == 1  # 2011-03-01 + 90 days = 2011-05-30, excluded


def test_incomplete_label_window_is_rejected():
    p = make_purchases([("A", "1", "2011-01-10", "X", 1, 1.0), ("A", "2", "2011-04-01", "X", 1, 1.0)])
    with pytest.raises(ValueError):
        s.label_churn(s.invoice_table(p), pd.Series(["A"]), pd.Timestamp("2011-03-01"), 90, s.data_end_of(p))


def test_snapshot_cutoffs_only_with_full_future_window():
    end = pd.Timestamp("2011-12-10")
    cuts = s.snapshot_cutoffs("2010-06-01", end, 90)
    assert all(c + 90 * DAY <= end for c in cuts)
    assert cuts[-1] == pd.Timestamp("2011-09-01")


def _monthly(n):
    return list(pd.date_range("2010-06-01", periods=n, freq="MS"))


def test_temporal_split_order_and_purge():
    sp = temporal_split(_monthly(16), n_test=3, n_val=3, horizon_days=90)
    assert max(sp.train) < min(sp.validation) < min(sp.test)
    assert max(sp.train) + 90 * DAY <= min(sp.validation)
    assert max(sp.validation) + 90 * DAY <= min(sp.test)
    assert len(sp.purged) > 0
    used = set(sp.train) | set(sp.validation) | set(sp.test)
    assert not used & set(sp.purged)


def test_overlap_detector_catches_contaminated_split():
    c = _monthly(6)
    bad = TemporalSplit(train=c[:2], validation=c[2:4], test=c[4:], purged=[], horizon_days=90)
    with pytest.raises(AssertionError):
        assert_no_label_overlap(bad)


def test_preprocessing_is_fitted_on_training_rows_only():
    rng = np.random.default_rng(0)
    train = pd.DataFrame(rng.normal(size=(200, len(s.MODEL_FEATURES))), columns=list(s.MODEL_FEATURES))
    train.loc[::7, "mean_gap_days"] = np.nan
    y = (train["recency_days"] > 0).astype(int).to_numpy()
    model = make_model("logistic_regression", {"C": 1.0}, 0).fit(train, y)
    assert model.named_steps["impute"].statistics_ == pytest.approx(train.median().to_numpy())


@pytest.fixture(scope="module")
def experiment_inputs():
    p = simulate_purchases()
    cuts = s.snapshot_cutoffs("2010-06-01", s.data_end_of(p), 90)
    snaps = s.build_training_snapshots(p, empty_returns(), cuts, 180, 90)
    return snaps, temporal_split(cuts, 3, 3, 90)


def test_selection_and_threshold_do_not_depend_on_test_labels(experiment_inputs):
    snaps, split = experiment_inputs
    a = run_churn_experiment(snaps, split, seed=1)
    shuffled = snaps.copy()
    test_mask = shuffled["cutoff"].isin(split.test)
    shuffled.loc[test_mask, "churned"] = np.random.default_rng(3).permutation(
        shuffled.loc[test_mask, "churned"].to_numpy()
    )
    b = run_churn_experiment(shuffled, split, seed=1)
    assert a.selected_family == b.selected_family
    assert a.selected_params == b.selected_params
    assert a.threshold == pytest.approx(b.threshold)


def test_experiment_reports_partitions_and_metrics(experiment_inputs):
    snaps, split = experiment_inputs
    e = run_churn_experiment(snaps, split, seed=1)
    names = [c["partition"] for c in e.class_balance]
    assert names == ["train", "validation", "test"]
    for m in e.test_results.values():
        assert 0 <= m["roc_auc"] <= 1 and 0 <= m["recall"] <= 1
        assert m["tp"] + m["fp"] + m["tn"] + m["fn"] == m["n"]
    assert {r["group"] for r in e.seen_vs_unseen} <= {"seen_in_train_or_validation", "unseen_customers"}
