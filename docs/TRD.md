# Technical requirements and design: CustomerPulse

## Stack (pinned in `backend/uv.lock` and `frontend/package-lock.json`)

| Layer | Technology |
|---|---|
| Analysis | Python 3.12, pandas 3.1, NumPy 2.5, scikit-learn 1.9, SHAP 0.54, SciPy, Matplotlib, Pandera 0.35, joblib |
| Persistence | PostgreSQL 17 / Neon, SQLAlchemy 2.1, Alembic 1.20, psycopg 3.3 |
| API | FastAPI 0.162, Pydantic 2.14, pydantic-settings |
| Frontend | React 19.3, TypeScript 7, Vite 8, Tailwind CSS 4.3, Recharts 3.10, React Router 8 |
| Quality | pytest 9, ruff, mypy, Vitest 5, Testing Library, Playwright 1.64, oxlint, gitleaks |
| Delivery | GitHub Actions, Vercel Hobby, Neon Free |

The analysis libraries are an optional extra (`--extra analysis`). The API
installs only core dependencies (about 50 MB), and CI asserts that it imports
without pandas or scikit-learn.

## Pipeline contract

`uv run customerpulse <stage>` runs these stages in order. Each stage reads
its inputs from disk and writes its outputs, so stages can be re-run
individually.

| Stage | Inputs | Outputs |
|---|---|---|
| `acquire` | official URL or `--local-archive` | `data/interim/transactions_raw.parquet`, `dataset_metadata.json` |
| `validate` | raw parquet | `validation_report.json` |
| `clean` | raw parquet | `purchases.parquet`, `returns.parquet`, `cleaning_report.json` |
| `features` | clean tables | `training_snapshots.parquet` (labelled), `scoring_features.parquet`, `customer_rfm.parquet`, `features_meta.json` |
| `segment` | `customer_rfm` | `segment_assignments.parquet`, `segmentation.json`, figures |
| `churn` | training snapshots | `artifacts/churn_model.joblib`, `churn_report.json`, `test_scores.parquet`, figures |
| `score` | model, scoring features, segments | `scores.parquet`, `score_meta.json` |
| `explain` | model, snapshots, scores | `shap_report.json`, `shap_local.parquet`, figure |
| `simulate` | scores | `retention_report.json` |
| `bundle` | all of the above | `artifacts/latest/{manifest.json, scores, segment_assignments, shap_local}.parquet`, `reports/results_summary.json` |
| `run-all` | — | all of the above |
| `persist` | bundle | rows in PostgreSQL (writer role) |
| `setup-roles` | admin URL + role passwords | schema and roles |

Determinism comes from a fixed `RANDOM_SEED = 42` everywhere (K-Means, forest,
HistGB, SHAP background, samples). There are no system-clock dependencies in
features. Stable sorting (`mergesort`) and key-based tie-breaking are used
throughout.

## Retention scenario formulas

Implemented in `analytics/retention.py` (pandas), `analytics/scenario_math.py`
(API) and `frontend/src/lib/simulate.ts` (dashboard). Parity is tested across
all three.

```
daily_rate_i      = min(180-day gross qualifying spend_i / 180, cap)
                    cap = 99.5th percentile of daily rates  (£152.59/day; 18 customers capped)
seasonal_factor   = (revenue in [T−1y, T−1y+H) / H) ÷ (revenue in [T−1y−180, T−1y) / 180)
                    = 0.591 for T = 2011-12-10, H = 90 (Dec–Mar is quieter than Jun–Dec)
projected_i       = daily_rate_i × horizon × seasonal_factor
revenue_at_risk   = Σ_{i ∈ targeted} p_i × projected_i
retained          = revenue_at_risk × effectiveness           (assumption)
campaign_cost     = n_targeted × cost_per_contact             (assumption)
net_impact        = retained × margin − campaign_cost         (margin = 1 ⇒ revenue basis, not profit)
break_even_eff.   = campaign_cost ÷ (revenue_at_risk × margin)
```

* **Targeting:** `ceil(fraction × n)` customers (float-safe), ranked by
  probability (`risk`) or probability × daily rate (`value_at_risk`). Ties are
  broken by customer key, ascending. With 3,471 scored customers, the cohort
  is exactly 348 (10.03%).
* **Probability horizon:** the probability `p_i` is always the model's 90-day
  inactivity probability. Changing the revenue horizon changes only the
  revenue projection.
* **Presets:** conservative (5% effectiveness, £5 per contact), base (10%,
  £3) and optimistic (20%, £2). These are illustrative assumptions, not
  evidence.

### Actual scenario outputs (top 10% by risk, 90-day horizon, revenue basis)

| Scenario | Targeted | Expected revenue at risk | Retained | Cost | Net | Break-even effectiveness |
|---|---|---|---|---|---|---|
| Conservative | 348 | £15,610 | £781 | £1,740 | −£959 | 11.1% |
| Base | 348 | £15,610 | £1,561 | £1,044 | £517 | 6.7% |
| Optimistic | 348 | £15,610 | £3,122 | £696 | £2,426 | 4.5% |
| Base, **ranked by risk × value** | 348 | £81,035 | £8,104 | £1,044 | £7,060 | 1.3% |

The highest-risk 348 customers are mostly low-spend: 182 Hibernating, 156
Promising and 10 At Risk. Their mean risk is 75.3%, but they carry only 6.6%
of the £237,624 expected revenue at risk across all scored customers. Ranking
by risk × value targets fewer certain churners (mean risk 40.2%) but covers
5.2× more revenue at risk. That is the decision the dashboard surfaces. **All
values are scenario estimates; no intervention outcome exists in the data.**

## API design

See `API.md`. The main choices:

* Synchronous SQLAlchemy sessions with `NullPool` for serverless use.
* A `get_session` dependency that can be overridden in tests.
* Response models for the main shapes, with JSON report blobs for nested
  methodology data.
* A JSON log line per request.

## Frontend design

* **Routing:** React Router data router. Seven routes are lazy-loaded; the
  Overview loads eagerly.
* **Data fetching:** `useApi`, a fetch hook with abort, retry and derived
  loading state. Placeholder data is never substituted.
* **Charts:** Recharts with shared axis and grid tokens, hover tooltips on
  every chart, and table views.
* **Simulator:** recomputes about 3.5k rows × 41 sensitivity points per
  change, in well under a frame budget.
* **API base:** `VITE_API_BASE_URL` at build time; the Vite proxy in
  development.

## Environments

| Environment | Database | API | Frontend |
|---|---|---|---|
| Local | project-local PostgreSQL 17 cluster (`.localdb/`, port 55432) | `uvicorn` on :8000 | Vite on :5173 (proxy `/api`) |
| CI | disposable `postgres:17` service | TestClient | `vite preview` on :4173 with a mocked API |
| Production | Neon Free project (dedicated) | Vercel project, root `backend/` | Vercel project, root `frontend/` |

## Configuration (`.env.example`)

| Variable | Used by | Secret |
|---|---|---|
| `CUSTOMERPULSE_PSEUDONYM_SECRET` | pipeline | yes |
| `ADMIN_DATABASE_URL` | `setup-roles` only | yes |
| `MIGRATOR_DATABASE_URL` | Alembic | yes |
| `WRITER_DATABASE_URL` | `persist` | yes |
| `DATABASE_URL` | API (reader) | yes |
| `CP_MIGRATOR_PASSWORD`, `CP_WRITER_PASSWORD`, `CP_READER_PASSWORD` | `setup-roles` | yes |
| `CORS_ORIGINS` | API | no |
| `CUSTOMERPULSE_TEST_ADMIN_URL` | tests (non-production) | yes |
| `VITE_API_BASE_URL` | frontend build | no (public URL) |
