# Testing

Tests are developed alongside the code and run in CI on every push and pull
request (`.github/workflows/ci.yml`). The counts below are from CI run
`41064961471` on commit `fd6d345`, and from local runs on the same code.

| Suite | Tool | Count | Result |
|---|---|---|---|
| Backend: data, leakage, segmentation, churn, SHAP, retention, DB, API | pytest | 95 | all pass; 78% line coverage of `customerpulse` |
| Frontend: unit and component | Vitest + Testing Library | 19 | all pass |
| Frontend: end-to-end (desktop 1440×900, tablet 820×1180, Pixel 7) | Playwright | 39 (13 × 3 viewports) | all pass |
| Static checks | ruff, ruff format, mypy (38 files), oxlint, `tsc` | — | clean |
| Secret scan | gitleaks (default rules) | — | no leaks |

No test uses the real dataset or production. The analysis tests use synthetic
transactions, and database/API tests use a synthetic results bundle
(`tests/fake_bundle.py`) loaded into a throwaway database. Frontend tests use
synthetic API fixtures (`frontend/src/test/fixtures.ts`).

## Backend (`backend/tests`)

| File | What it proves |
|---|---|
| `test_cleaning.py` | every raw row is accounted for; sheet overlap, duplicates, missing IDs, postage codes, zero prices and invalid dates are excluded with the right reason; cancellations become positive-valued returns; float customer IDs are normalised; cleaning is order-independent; Pandera rejects malformed invoice codes |
| `test_features.py` | frequency counts invoices, not lines; monetary and recency values; only customers active in the lookback are eligible; **a transaction at or after the cutoff changes nothing**; returns don't affect frequency; non-midnight cutoffs are rejected; no identifier or label is a model feature; lifetime RFM for segmentation |
| `test_leakage.py` | labels are 1 only without a purchase in the window; the window end is exclusive; incomplete windows raise; snapshot cutoffs have full future windows; the split is ordered and purged; the overlap detector catches a contaminated split; imputer statistics equal the **training** medians; **selection and threshold are unchanged when test labels are shuffled**; partition and metric sanity |
| `test_segmentation.py` | standardisation; invalid RFM is rejected; silhouette recovers K = 3 on three blobs; deterministic labels; canonical IDs ordered by spend; guards respected; undersized clusters fail the guard; every naming rule (parametrised); duplicate names are disambiguated |
| `test_evaluation.py` | top-k sizing (including the float edge case 30 × 0.1 = 3); tie-breaking by key; precision, capture and lift; the recall-target threshold is the highest that meets the target; confusion matrix; curve bounds; per-snapshot top-fraction and decile tables |
| `test_shap_retention.py` | SHAP shapes and feature alignment; **exact additivity for all three model families** in their output space; global ranking order; local explanation format and wording; a missing feature raises; top-k tie handling; value ranking; scenario formulas; margin basis and sensitivity; invalid assumptions rejected; projection cap and seasonal factor; pseudonymous keys are stable and secret-dependent |
| `test_db_api.py` (needs `CUSTOMERPULSE_TEST_ADMIN_URL`) | migrations match the models (`alembic check`); **the reader role cannot DELETE, UPDATE, INSERT, CREATE or DROP even with READ WRITE**; the writer cannot run DDL; CHECK constraints; a failed persist is recorded with a secret-free summary and the API keeps serving the previous run; duplicate runs are rejected; health and summary; pagination and filters; 422 for invalid parameters (including injection-like keys); 404s; customer detail and explanations; segments, models and retention endpoints; API vs pipeline simulation parity; only GET routes; CORS restricted; no secrets or raw IDs in responses |

Run locally:

```bash
cd backend
uv sync --extra analysis
uv run pytest                    # DB tests are skipped if CUSTOMERPULSE_TEST_ADMIN_URL is unset
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

`CUSTOMERPULSE_TEST_ADMIN_URL` must point to a **non-production** server where
a database named `customerpulse_test` may be created and dropped. Locally,
that is the project's own cluster on port 55432.

## Frontend (`frontend/`)

| File | What it proves |
|---|---|
| `src/lib/simulate.test.ts` | client scenario maths matches the backend formulas (the same four-customer fixture and expected values as the Python parity test); responds to every assumption; float-safe top-k |
| `src/lib/format.test.ts` | currency and percent formatting; colour follows the cluster ID |
| `src/test/app.test.tsx` | loading → data; all 8 sidebar links and navigation; **API failure shows an error with retry and no figures**; empty state; segment labels, K and silhouette; profile tabs; churn filters sent to the API; customer drawer; model comparison and confusion matrix; SHAP local explanation; **simulator recalculates on slider and ranking changes** and always shows the disclaimer; attribution on the methodology page |
| `e2e/dashboard.spec.ts` | each of the 8 pages renders one `h1`, has **no horizontal overflow** and no page errors on desktop, tablet and phone; desktop and mobile-menu navigation; simulator recalculation; filters update the URL; Escape closes the drawer; the API-failure state; skip link focus |

```bash
cd frontend
npm ci
npm run lint && npm run typecheck && npm test
npx playwright install chromium
npm run test:e2e        # builds, serves with vite preview, mocks the API
```

## Manual verification performed

* The full pipeline ran on the real dataset (`customerpulse run-all`). The
  bundle was persisted to a local PostgreSQL 17 database, and every endpoint
  was exercised against it.
* The dashboard was screenshotted against the real local API at 1440 px and
  390 px. No console errors appeared, and horizontal overflow was fixed on
  phone width.
* The reader role was checked against the real database: DELETE, INSERT and
  CREATE were blocked, as was UPDATE after forcing READ WRITE.

## Not covered

* Automated accessibility auditing (axe) is not yet part of CI. The
  accessibility checks are semantic: landmarks, labels, `aria-*` attributes,
  table views for charts and a skip link.
* Production smoke tests depend on deployment; see `DEPLOYMENT.md`.
