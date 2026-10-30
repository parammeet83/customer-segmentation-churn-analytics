# API

A read-only FastAPI service (`backend/src/customerpulse/api/`). OpenAPI JSON
is at `/api/openapi.json` and interactive docs at `/api/docs`. Every data
endpoint is under **`/api/v1`** and is `GET`-only. A test asserts that the
OpenAPI spec contains no other methods.

All data endpoints serve the **latest successful analysis run**. If no run
has succeeded, they return `503 {"detail": "No successful analysis run is
available yet"}`.

## Endpoints

| Endpoint | Parameters | Returns |
|---|---|---|
| `GET /api/v1/health` | — | `{status, database, version}`; never raises |
| `GET /api/v1/summary` | — | served run, latest attempt (if different and not successful), dataset coverage, KPIs, segments, risk bands, takeaway sentence |
| `GET /api/v1/analysis-runs` | `limit` 1–50 (default 20) | recent runs with status and safe error summaries |
| `GET /api/v1/data-quality` | — | dataset version and checksum, validation report, raw profile, exclusions, cleaning output, monthly purchase value, feature metadata, run config |
| `GET /api/v1/segments` | `scatter_points` 0–3000 (default 1500) | K table, selection rule, silhouette, PCA variance, profiles, deterministic scatter sample, population quantiles |
| `GET /api/v1/segments/{segment_id}` | `segment_id` 0–50 | profile, SQL-computed recency/frequency/monetary histograms, scored customers, mean churn probability, top-decile count |
| `GET /api/v1/customers` | `page` ≥ 1, `page_size` 1–100, `segment`, `risk_band` ∈ {Very high, High, Medium, Low}, `top_decile`, `sort` ∈ {risk, value_at_risk, monetary, recency} | paginated scored customers |
| `GET /api/v1/customers/{customer_key}` | key must match `^C-[0-9a-f]{12}$` | features, score, segment, SHAP contributions (top-decile customers) |
| `GET /api/v1/churn/top-risk` | `page`, `page_size`, `segment` | paginated top-decile cohort |
| `GET /api/v1/churn/metrics` | — | churn definition, split, class balance, selection and threshold rules, per-snapshot and seen/unseen metrics, deciles, horizon sensitivity |
| `GET /api/v1/models/metrics` | — | all validation and test metric rows, ROC/PR/calibration curves |
| `GET /api/v1/churn/explanations` | optional `customer_key` | explainer metadata, additivity error, global ranking, beeswarm sample, example keys, and local contributions when a key is given (404 if not stored) |
| `GET /api/v1/retention/scenarios` | — | stored scenarios, cohort summary, projection method, seasonal factor, disclaimer |
| `GET /api/v1/retention/simulator-data` | — | compact `[probability, daily_revenue_rate, cluster_id]` rows in risk order (**no customer keys**), season factor, defaults |
| `GET /api/v1/retention/simulate` | `target_fraction` (0, 1], `effectiveness` [0, 1], `cost_per_contact` [0, 1000], `horizon_days` 1–365, `margin` (0, 1], `ranking` ∈ {risk, value_at_risk} | server-side scenario result (reference implementation for the dashboard) |

### Example

```http
GET /api/v1/retention/simulate?target_fraction=0.1&effectiveness=0.1&cost_per_contact=3
```

```json
{
  "assumptions": {"target_fraction": 0.1, "effectiveness": 0.1, "cost_per_contact": 3.0,
                  "horizon_days": 90, "margin": 1.0, "ranking": "risk"},
  "targeted_customers": 348,
  "expected_revenue_at_risk": 15610.28,
  "scenario_revenue_retained": 1561.03,
  "campaign_cost": 1044.0,
  "net_impact": 517.03,
  "net_impact_basis": "revenue",
  "label": "Scenario estimate under stated assumptions - not observed savings",
  "season_factor": 0.591, "currency": "GBP"
}
```

(The values above are from the actual current run, rounded.)

## Behaviour and safety

* **Validation:** Pydantic and FastAPI validate every parameter. Out-of-range
  or malformed values return `422`, and unknown segments or customers return
  `404`.
* **Pagination:** `page_size` is capped at 100. The scatter sample is capped
  at 3,000 points.
* **SQL:** all queries go through SQLAlchemy with bound parameters; there is
  no string-built SQL.
* **Errors:** database errors return `503 {"detail": "Database temporarily
  unavailable"}`. Unexpected errors return `500 {"detail": "Internal server
  error"}`. Neither leaks internals.
* **Logging:** a structured JSON line per request (`request_id`, method,
  path, status, ms). Every response carries an `X-Request-ID` header.
* **CORS:** `allow_origins` comes from `CORS_ORIGINS` (exact origins, no
  wildcard), methods are `GET` only, and credentials are disabled. A test
  checks that an unknown origin gets no CORS header.
* **Caching:** successful data responses send `Cache-Control: public,
  max-age=300`.
* **Database access:** the API connects with the read-only `cp_reader` role
  (`DATABASE_URL`), using `NullPool` suited to serverless execution.
* **Privacy:** only pseudonymous keys and aggregated behavioural features are
  returned. Raw customer IDs, invoices and product lines are never stored in
  or returned by the API.
* **No write or training endpoints** exist.

## Running locally

```bash
cd backend
uv run uvicorn customerpulse.api.app:app --port 8000
# http://localhost:8000/api/docs
```
