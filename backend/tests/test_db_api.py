"""Database, role-permission and API tests against a disposable PostgreSQL database.

Requires ``CUSTOMERPULSE_TEST_ADMIN_URL``: an administrative URL to a server
where a throwaway database named ``customerpulse_test`` may be created and
dropped. Role passwords come from CP_*_PASSWORD. Never point this at
production.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from customerpulse.analytics.retention import ScenarioAssumptions, simulate
from customerpulse.analytics.scenario_math import CustomerRisk, simulate_rows
from customerpulse.database.persist import persist_bundle
from customerpulse.database.roles import setup_roles
from customerpulse.database.session import get_session

from .fake_bundle import make_bundle

ADMIN = os.environ.get("CUSTOMERPULSE_TEST_ADMIN_URL")
TEST_DB = "customerpulse_test"
pytestmark = [pytest.mark.db, pytest.mark.skipif(not ADMIN, reason="CUSTOMERPULSE_TEST_ADMIN_URL not set")]
BACKEND = Path(__file__).resolve().parents[1]


def _with(url: str, user: str | None = None, password: str | None = None, db: str | None = None) -> str:
    u = urlsplit(url.replace("postgresql+psycopg://", "postgresql://"))
    host = u.hostname + (f":{u.port}" if u.port else "")
    user = user or u.username
    password = password if password is not None else u.password
    netloc = f"{user}:{password}@{host}" if password else f"{user}@{host}"
    return urlunsplit((u.scheme, netloc, "/" + (db or u.path.lstrip("/")), u.query, ""))


@pytest.fixture(scope="module")
def urls():
    with psycopg.connect(ADMIN, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")
    admin = _with(ADMIN, db=TEST_DB)
    setup_roles(admin)
    u = {
        "admin": admin,
        "migrator": _with(ADMIN, "cp_migrator", os.environ["CP_MIGRATOR_PASSWORD"], TEST_DB),
        "writer": _with(ADMIN, "cp_writer", os.environ["CP_WRITER_PASSWORD"], TEST_DB),
        "reader": _with(ADMIN, "cp_reader", os.environ["CP_READER_PASSWORD"], TEST_DB),
    }
    env = {**os.environ, "MIGRATOR_DATABASE_URL": u["migrator"]}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True, capture_output=True
    )
    yield u
    with psycopg.connect(ADMIN, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")


def _engine(url):
    return create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))


@pytest.fixture(scope="module")
def persisted(urls, tmp_path_factory):
    good = make_bundle(tmp_path_factory.mktemp("good"), seed=1)
    run_ok = persist_bundle(good, engine=_engine(urls["writer"]))
    bad = make_bundle(tmp_path_factory.mktemp("bad"), seed=2, corrupt=True)
    with pytest.raises(Exception):
        persist_bundle(bad, engine=_engine(urls["writer"]))
    return {"ok": run_ok, "good_bundle": good}


@pytest.fixture(scope="module")
def client(urls, persisted):
    from customerpulse.api.app import app

    factory = sessionmaker(bind=_engine(urls["reader"]))

    def override():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_migrations_are_current(urls):
    env = {**os.environ, "MIGRATOR_DATABASE_URL": urls["migrator"]}
    out = subprocess.run(
        [sys.executable, "-m", "alembic", "check"], cwd=BACKEND, env=env, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr


@pytest.mark.parametrize(
    "stmt",
    [
        "DELETE FROM segments",
        "UPDATE churn_scores SET churn_probability = 0",
        "INSERT INTO retention_scenarios (run_id, name, assumptions, results) VALUES (gen_random_uuid(), 'x', '{}', '{}')",
        "CREATE TABLE intruder (x int)",
        "DROP TABLE segments",
    ],
)
def test_reader_role_cannot_modify(urls, persisted, stmt):
    with _engine(urls["reader"]).connect() as c:
        c.execute(text("SET TRANSACTION READ WRITE"))
        with pytest.raises(Exception) as e:
            c.execute(text(stmt))
        assert "permission denied" in str(e.value) or "must be owner" in str(e.value)


def test_writer_role_cannot_change_schema(urls, persisted):
    with _engine(urls["writer"]).begin() as c, pytest.raises(Exception):
        c.execute(text("CREATE TABLE intruder (x int)"))


def test_constraints_reject_invalid_probability(urls, persisted):
    with _engine(urls["writer"]).begin() as c, pytest.raises(Exception, match="ck_probability"):
        c.execute(text("UPDATE churn_scores SET churn_probability = 2 WHERE risk_rank = 1"))


def test_failed_run_is_recorded_and_not_served(client, persisted):
    runs = client.get("/api/v1/analysis-runs").json()
    assert {r["status"] for r in runs} == {"succeeded", "failed"}
    failed = next(r for r in runs if r["status"] == "failed")
    assert failed["error_summary"] and "postgresql://" not in failed["error_summary"]
    s = client.get("/api/v1/summary").json()
    assert s["run"]["run_id"] == persisted["ok"]
    assert s["latest_attempt"]["status"] == "failed"


def test_duplicate_run_rejected(urls, persisted):
    with pytest.raises(RuntimeError, match="already persisted"):
        persist_bundle(persisted["good_bundle"], engine=_engine(urls["writer"]))


def test_health_and_summary(client):
    assert client.get("/api/v1/health").json()["database"] == "ok"
    s = client.get("/api/v1/summary").json()
    assert s["kpis"]["segment_count"] == 3
    assert s["kpis"]["eligible_customers"] == 35
    assert [b["risk_band"] for b in s["risk_bands"]] == ["Very high", "High", "Medium", "Low"]


def test_pagination_and_filters(client):
    r = client.get("/api/v1/customers", params={"page": 2, "page_size": 10}).json()
    assert r["meta"] == {"page": 2, "page_size": 10, "total": 35, "pages": 4}
    assert [x["risk_rank"] for x in r["items"]] == list(range(11, 21))
    top = client.get("/api/v1/churn/top-risk", params={"page_size": 100}).json()
    assert top["meta"]["total"] == 4 and all(x["in_top_decile"] for x in top["items"])
    seg = client.get("/api/v1/customers", params={"segment": 1, "page_size": 100}).json()
    assert all(x["cluster_id"] == 1 for x in seg["items"])
    band = client.get("/api/v1/customers", params={"risk_band": "Low", "page_size": 100}).json()
    assert band["items"] and all(x["risk_band"] == "Low" for x in band["items"])


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/customers?page_size=101",
        "/api/v1/customers?page=0",
        "/api/v1/customers?risk_band=Extreme",
        "/api/v1/customers?sort=customer_id",
        "/api/v1/customers/12345",
        "/api/v1/customers/C-'%20OR%201=1",
        "/api/v1/retention/simulate?effectiveness=2",
        "/api/v1/retention/simulate?ranking=random",
        "/api/v1/segments/-1",
    ],
)
def test_invalid_queries_rejected(client, path):
    assert client.get(path).status_code == 422


def test_not_found(client):
    assert client.get("/api/v1/segments/7").status_code == 404
    assert client.get("/api/v1/customers/C-000000000000").status_code == 404


def test_customer_detail_and_explanations(client):
    key = client.get("/api/v1/churn/top-risk?page_size=1").json()["items"][0]["customer_key"]
    d = client.get(f"/api/v1/customers/{key}").json()
    assert d["explanation_available"] and len(d["explanation"]) == 3
    assert "customer_id" not in d["features"]
    e = client.get("/api/v1/churn/explanations", params={"customer_key": key}).json()
    assert e["local"][0]["rank"] == 1 and len(e["global"]) == 23
    low = client.get("/api/v1/customers?risk_band=Low&page_size=1").json()["items"][0]["customer_key"]
    assert client.get("/api/v1/churn/explanations", params={"customer_key": low}).status_code == 404


def test_segments_models_retention_endpoints(client):
    seg = client.get("/api/v1/segments?scatter_points=10").json()
    assert seg["selected_k"] == 3 and len(seg["scatter"]) == 10 and len(seg["profiles"]) == 3
    det = client.get("/api/v1/segments/0").json()
    assert sum(b["customers"] for b in det["distributions"]["monetary"]) == det["profile"]["customers"]
    mm = client.get("/api/v1/models/metrics").json()
    assert {m["evaluation_split"] for m in mm["metrics"]} == {"validation", "test"}
    assert sum(m["is_selected"] and m["evaluation_split"] == "test" for m in mm["metrics"]) == 1
    sim = client.get("/api/v1/retention/simulator-data").json()
    assert len(sim["rows"]) == 35 and "customer_key" not in sim["columns"]
    assert client.get("/api/v1/retention/scenarios").json()["disclaimer"]
    assert client.get("/api/v1/data-quality").json()["exclusions"][0]["reason"] == "missing_customer_id"


def test_api_simulation_matches_pipeline_simulation(client, persisted):
    import pandas as pd

    scores = pd.read_parquet(persisted["good_bundle"] / "scores.parquet")
    for ranking in ("risk", "value_at_risk"):
        api = client.get(
            "/api/v1/retention/simulate",
            params={
                "target_fraction": 0.2,
                "effectiveness": 0.15,
                "cost_per_contact": 2,
                "horizon_days": 60,
                "ranking": ranking,
            },
        ).json()
        ref = simulate(scores, ScenarioAssumptions(0.2, 0.15, 2.0, 60, 1.0, ranking), 90, 1.0)
        for k in (
            "targeted_customers",
            "expected_revenue_at_risk",
            "scenario_revenue_retained",
            "campaign_cost",
            "net_impact",
        ):
            assert api[k] == pytest.approx(ref[k]), k


def test_pure_simulation_parity_without_db():
    import pandas as pd

    df = pd.DataFrame(
        {
            "customer_key": ["a", "b", "c", "d"],
            "churn_probability": [0.9, 0.9, 0.2, 0.5],
            "daily_revenue_rate": [1.0, 3.0, 50.0, 2.0],
        }
    )
    rows = [CustomerRisk(*t) for t in df.itertuples(index=False)]
    for ranking in ("risk", "value_at_risk"):
        a = simulate_rows(rows, 0.5, 0.1, 1.0, 90, 0.5, ranking, 0.8)
        b = simulate(df, ScenarioAssumptions(0.5, 0.1, 1.0, 90, 0.5, ranking), 90, 0.8)
        assert a["net_impact"] == pytest.approx(b["net_impact"])


def test_openapi_lists_only_get_endpoints(client):
    spec = client.get("/api/openapi.json").json()
    methods = {m for p in spec["paths"].values() for m in p}
    assert methods == {"get"}
    assert all(p.startswith("/api/v1/") for p in spec["paths"])


def test_cors_restricted(client):
    ok = client.options(
        "/api/v1/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options(
        "/api/v1/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in bad.headers


def test_responses_do_not_leak_secrets_or_raw_ids(client):
    body = (
        client.get("/api/v1/summary").text
        + client.get("/api/v1/data-quality").text
        + client.get("/api/v1/customers?page_size=100").text
    )
    for secret_env in ("CP_READER_PASSWORD", "CP_WRITER_PASSWORD", "CUSTOMERPULSE_PSEUDONYM_SECRET"):
        v = os.environ.get(secret_env)
        if v:
            assert v not in body
    assert "postgresql://" not in body and '"customer_id"' not in body
