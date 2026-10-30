import numpy as np
import pandas as pd
import pytest

from customerpulse.analytics.retention import (
    ScenarioAssumptions,
    project_revenue,
    seasonal_factor,
    select_top,
    simulate,
)
from customerpulse.churn.models import make_model
from customerpulse.explainability.shap_explain import explain, global_importance, local_explanations
from customerpulse.features.pseudonymize import add_customer_keys, customer_key, get_secret
from customerpulse.features.snapshots import MODEL_FEATURES

FEATS = list(MODEL_FEATURES)


@pytest.fixture(scope="module")
def train_frame():
    rng = np.random.default_rng(0)
    X = pd.DataFrame(np.abs(rng.normal(5, 3, size=(400, len(FEATS)))), columns=FEATS)
    X.loc[::5, "mean_gap_days"] = np.nan
    logit = 0.4 * (X["recency_days"] - 5) - 0.3 * (X["frequency"] - 5)
    y = (rng.random(400) < 1 / (1 + np.exp(-logit))).astype(int).to_numpy()
    return X, y


@pytest.mark.parametrize(
    ("family", "params"),
    [
        ("logistic_regression", {"C": 1.0}),
        ("hist_gradient_boosting", {"learning_rate": 0.1, "max_leaf_nodes": 15, "max_iter": 30}),
        ("random_forest", {"min_samples_leaf": 10, "max_features": "sqrt"}),
    ],
)
def test_explanations_align_with_features_and_are_additive(train_frame, family, params):
    X, y = train_frame
    model = make_model(family, params, 0).fit(X, y)
    rows = X.iloc[:50]
    out = explain(model, X.iloc[:100], rows)
    assert out.values.shape == (50, len(FEATS))
    assert out.features == FEATS
    target = out.model_output(model.predict_proba(rows)[:, 1])
    recon = out.base_value + out.values.sum(axis=1)
    assert out.output_space == ("probability" if family == "random_forest" else "log_odds")
    assert np.max(np.abs(recon - target)) < 1e-6


def test_global_and_local_format(train_frame):
    X, y = train_frame
    model = make_model("logistic_regression", {"C": 1.0}, 0).fit(X, y)
    out = explain(model, X.iloc[:100], X.iloc[:20])
    g = global_importance(out, X.iloc[:20])
    assert [r["rank"] for r in g] == list(range(1, len(FEATS) + 1))
    assert g[0]["mean_abs_shap"] >= g[-1]["mean_abs_shap"]
    assert g[0]["feature"] in {"recency_days", "frequency"}
    loc = local_explanations(out, X.iloc[:20].reset_index(drop=True), [f"C-{i}" for i in range(20)], top_n=3)
    assert len(loc) == 60
    assert {"customer_key", "feature", "feature_value", "shap_value", "rank", "explanation"} <= set(loc[0])
    assert all(("raised" in r["explanation"]) == (r["shap_value"] > 0) for r in loc)


def test_missing_feature_is_rejected(train_frame):
    X, y = train_frame
    model = make_model("logistic_regression", {"C": 1.0}, 0).fit(X, y)
    with pytest.raises(KeyError):
        explain(model, X, X.drop(columns=["recency_days"]))


# --------------------------------------------------------------------- retention


@pytest.fixture
def scores():
    return pd.DataFrame(
        {
            "customer_key": [f"C-{i:02d}" for i in range(20)],
            "churn_probability": [0.9, 0.9] + list(np.linspace(0.8, 0.1, 18)),
            "daily_revenue_rate": [1.0, 2.0] + [10.0] * 18,
        }
    )


def test_top_selection_ties_and_size(scores):
    top = select_top(scores, 0.1)
    assert list(top["customer_key"]) == ["C-00", "C-01"]  # tie broken by key
    assert len(select_top(scores, 0.15)) == 3


def test_value_ranking_prefers_expected_value(scores):
    top = select_top(scores, 0.1, ranking="value_at_risk")
    assert "C-00" not in set(top["customer_key"])


def test_scenario_formulas(scores):
    a = ScenarioAssumptions(target_fraction=0.1, effectiveness=0.2, cost_per_contact=1.0, horizon_days=90, margin=1.0)
    r = simulate(scores, a, base_horizon_days=90, season=0.5)
    projected = np.array([1.0, 2.0]) * 90 * 0.5
    at_risk = float((np.array([0.9, 0.9]) * projected).sum())
    assert r["targeted_customers"] == 2
    assert r["expected_revenue_at_risk"] == pytest.approx(at_risk)
    assert r["scenario_revenue_retained"] == pytest.approx(at_risk * 0.2)
    assert r["campaign_cost"] == 2.0
    assert r["net_impact"] == pytest.approx(at_risk * 0.2 - 2.0)
    assert r["break_even_effectiveness"] == pytest.approx(2.0 / at_risk)
    assert "not observed" in r["label"]


def test_margin_and_sensitivity(scores):
    base = simulate(scores, ScenarioAssumptions(effectiveness=0.1), 90)
    more = simulate(scores, ScenarioAssumptions(effectiveness=0.3), 90)
    margin = simulate(scores, ScenarioAssumptions(effectiveness=0.1, margin=0.4), 90)
    assert more["scenario_revenue_retained"] > base["scenario_revenue_retained"]
    assert margin["net_impact_basis"] == "gross margin"
    assert margin["net_impact"] < base["net_impact"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_fraction": 0},
        {"effectiveness": 1.5},
        {"cost_per_contact": -1},
        {"horizon_days": 0},
        {"margin": 0},
        {"ranking": "random"},
    ],
)
def test_invalid_assumptions_rejected(scores, kwargs):
    with pytest.raises(ValueError):
        simulate(scores, ScenarioAssumptions(**kwargs), 90)


def test_projection_cap_and_season():
    f = pd.DataFrame({"customer_key": [f"C-{i}" for i in range(100)], "monetary": [180.0] * 99 + [180000.0]})
    p = project_revenue(f, lookback_days=180, horizon_days=90, season=2.0, cap_quantile=0.99)
    assert p["projection_capped"].sum() == 1
    assert p.loc[0, "projected_revenue"] == pytest.approx(1.0 * 90 * 2.0)


def test_seasonal_factor_requires_history():
    inv = pd.DataFrame({"invoice_date": pd.to_datetime(["2011-01-01", "2011-02-01"]), "value": [1.0, 1.0]})
    assert seasonal_factor(inv, pd.Timestamp("2011-03-01"), 180, 90) == {"factor": 1.0, "available": False}


# ------------------------------------------------------------------ pseudonymise


def test_pseudonymous_keys_are_stable_and_secret_dependent(monkeypatch):
    a = customer_key("12345", b"secret-one-0123456789")
    assert a == customer_key("12345", b"secret-one-0123456789")
    assert a != customer_key("12345", b"secret-two-0123456789")
    assert a.startswith("C-") and "12345" not in a
    df = add_customer_keys(pd.DataFrame({"customer_id": ["1", "2", "1"]}), b"x" * 20)
    assert df["customer_key"].nunique() == 2
    monkeypatch.setenv("CUSTOMERPULSE_PSEUDONYM_SECRET", "short")
    with pytest.raises(RuntimeError):
        get_secret()
