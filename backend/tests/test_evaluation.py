import numpy as np
import pandas as pd
import pytest

from customerpulse.churn.evaluate import (
    classification_metrics,
    curves,
    decile_table,
    rank_order,
    threshold_for_recall,
    top_fraction_metrics,
    top_k_count,
)
from customerpulse.churn.models import top_fraction_per_snapshot


def test_top_k_count_rounds_up_with_minimum_one():
    assert top_k_count(100, 0.1) == 10
    assert top_k_count(101, 0.1) == 11
    assert top_k_count(5, 0.1) == 1
    assert top_k_count(0, 0.1) == 0
    with pytest.raises(ValueError):
        top_k_count(10, 0)


def test_rank_order_breaks_ties_by_key():
    order = rank_order(np.array([0.5, 0.9, 0.5, 0.9]), np.array(["d", "b", "a", "c"]))
    assert list(order) == [1, 3, 2, 0]


def test_top_fraction_metrics():
    y = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 1])
    s = np.array([0.9, 0.8, 0.7, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.2])
    m = top_fraction_metrics(y, s, 0.2)
    assert m["selected"] == 2
    assert m["precision"] == 1.0
    assert m["capture_rate"] == pytest.approx(2 / 3)
    assert m["lift"] == pytest.approx(1.0 / 0.3)


def test_threshold_for_recall_reaches_target():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 500)
    s = np.clip(y * 0.3 + rng.normal(0.4, 0.2, 500), 0, 1)
    thr = threshold_for_recall(y, s, 0.75)
    recall = ((s >= thr) & (y == 1)).sum() / y.sum()
    assert recall >= 0.75
    # A slightly higher threshold must fall below the target (highest such threshold).
    higher = s[s > thr].min()
    assert ((s >= higher) & (y == 1)).sum() / y.sum() < 0.75


def test_classification_metrics_confusion_matrix():
    y = np.array([1, 0, 1, 0])
    s = np.array([0.9, 0.8, 0.3, 0.1])
    m = classification_metrics(y, s, threshold=0.5, fraction=0.5)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)
    assert m["recall"] == 0.5 and m["precision"] == 0.5
    assert m["roc_auc"] == pytest.approx(0.75)


def test_curves_are_bounded():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 300)
    c = curves(y, rng.random(300))
    for key in ("roc", "pr", "calibration"):
        assert c[key] and all(0 <= p["x"] <= 1 and 0 <= p["y"] <= 1 for p in c[key])


def test_top_fraction_per_snapshot_and_deciles():
    frame = pd.DataFrame(
        {
            "cutoff": [pd.Timestamp("2011-01-01")] * 10 + [pd.Timestamp("2011-02-01")] * 10,
            "customer_id": [str(i) for i in range(20)],
            "churned": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0] * 2,
            "score": list(np.linspace(1, 0, 10)) * 2,
        }
    )
    m = top_fraction_per_snapshot(frame, 0.1)
    assert m["selected"] == 2 and m["true_churners_selected"] == 2 and m["capture_rate"] == 1.0
    d = decile_table(frame)
    assert len(d) == 10 and d[0]["churn_rate"] == 1.0 and sum(x["n"] for x in d) == 20
