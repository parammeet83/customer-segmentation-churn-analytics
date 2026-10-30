import numpy as np
import pandas as pd
import pytest

from customerpulse.config import SegmentationConfig
from customerpulse.segmentation.kmeans import prepare_matrix, segment, select_k
from customerpulse.segmentation.naming import NEUTRAL_ACTION, Levels, name_clusters, name_from_levels

CFG = SegmentationConfig(
    k_min=2, k_max=6, selectable_k_min=2, selectable_k_max=6, n_init=5, stability_bootstrap_rounds=3
)


@pytest.fixture
def three_blobs() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    parts = []
    for rec, freq, mon, n in ((10, 30, 20000, 150), (120, 5, 1500, 150), (500, 1, 100, 150)):
        parts.append(
            pd.DataFrame(
                {
                    "recency_days": rec * np.exp(rng.normal(0, 0.15, n)),
                    "frequency": np.maximum(1, np.round(freq * np.exp(rng.normal(0, 0.15, n)))),
                    "monetary": mon * np.exp(rng.normal(0, 0.15, n)),
                    "tenure_days": 600.0,
                }
            )
        )
    df = pd.concat(parts, ignore_index=True)
    df["customer_key"] = [f"C-{i:04d}" for i in range(len(df))]
    return df


def test_prepare_matrix_is_standardised(three_blobs):
    Z, _ = prepare_matrix(three_blobs)
    assert Z.mean(axis=0) == pytest.approx([0, 0, 0], abs=1e-9)
    assert Z.std(axis=0) == pytest.approx([1, 1, 1], abs=1e-9)


def test_prepare_matrix_rejects_invalid_values(three_blobs):
    bad = three_blobs.copy()
    bad.loc[0, "monetary"] = np.nan
    with pytest.raises(ValueError):
        prepare_matrix(bad)
    bad.loc[0, "monetary"] = -5
    with pytest.raises(ValueError):
        prepare_matrix(bad)


def test_silhouette_selects_true_k_and_is_deterministic(three_blobs):
    a = segment(three_blobs, CFG, seed=1)
    b = segment(three_blobs, CFG, seed=1)
    assert a.selected_k == 3
    np.testing.assert_array_equal(a.labels, b.labels)
    assert sum(r["selected"] for r in a.k_table) == 1
    assert all(-1 <= r["silhouette"] <= 1 for r in a.k_table)
    assert a.pca_coords.shape == (len(three_blobs), 2)


def test_canonical_cluster_ids_ordered_by_monetary(three_blobs):
    res = segment(three_blobs, CFG, seed=1)
    med = three_blobs.assign(c=res.labels).groupby("c")["monetary"].median()
    assert list(med.index) == [0, 1, 2]
    assert med.is_monotonic_decreasing


def test_select_k_respects_guards():
    table = [
        {"k": 2, "silhouette": 0.9, "passes_guards": False},
        {"k": 3, "silhouette": 0.5, "passes_guards": True},
        {"k": 4, "silhouette": 0.6, "passes_guards": True},
    ]
    assert select_k(table) == 4
    with pytest.raises(ValueError):
        select_k([{"k": 3, "silhouette": 0.5, "passes_guards": False}])


def test_undersized_clusters_fail_guard(three_blobs):
    cfg = SegmentationConfig(
        k_min=2,
        k_max=4,
        selectable_k_min=2,
        selectable_k_max=4,
        n_init=5,
        stability_bootstrap_rounds=2,
        min_cluster_share=0.5,
    )
    with pytest.raises(ValueError):
        segment(three_blobs, cfg, seed=1)


@pytest.mark.parametrize(
    ("levels", "expected"),
    [
        (Levels("recent", "high", "high", False, True), "Champions"),
        (Levels("recent", "mid", "mid", False, True), "Loyal Customers"),
        (Levels("recent", "mid", "mid", False, False), "Promising Customers"),
        (Levels("recent", "low", "low", True, False), "New Customers"),
        (Levels("lapsing", "high", "mid", False, True), "At Risk"),
        (Levels("lapsing", "low", "low", False, True), "Needs Attention"),
        (Levels("lapsed", "low", "low", False, True), "Hibernating Customers"),
        (Levels("lapsed", "mid", "mid", False, True), "Lapsed, mid-frequency, mid-spend customers"),
    ],
)
def test_naming_rules(levels, expected):
    assert name_from_levels(levels) == expected


def test_duplicate_names_are_disambiguated_and_neutral_names_get_review_action(three_blobs):
    pop = three_blobs
    profiles = pd.DataFrame(
        {
            "recency_days": [500.0, 520.0, 400.0],
            "frequency": [1.0, 1.0, 8.0],
            "monetary": [150.0, 90.0, 2000.0],
            "tenure_days": [600.0, 600.0, 600.0],
        },
        index=[0, 1, 2],
    )
    named = name_clusters(profiles, pop)
    assert named["segment_name"].is_unique
    assert named.loc[0, "segment_name"] == "Hibernating Customers (higher spend)"
    assert named.loc[1, "segment_name"] == "Hibernating Customers (lower spend)"
    neutral = name_clusters(
        pd.DataFrame({"recency_days": [500.0], "frequency": [8.0], "monetary": [1500.0], "tenure_days": [600.0]}), pop
    )
    assert neutral.iloc[0]["recommended_action"] in {NEUTRAL_ACTION} or neutral.iloc[0]["base_name"] == "At Risk"
