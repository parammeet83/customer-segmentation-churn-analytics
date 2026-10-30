# CustomerPulse — Task Checklist

Status legend: `[x]` done and verified · `[~]` in progress · `[ ]` not started.
Only items verified by running code are ticked.

## Phase 1 — Inspection and planning
- [x] Verify working directory, Git identity (`Parammeet <parammeet92@gmail.com>`), branch `main`, remote `origin`
- [x] Confirm GitHub repository is public and empty
- [x] Verify Python 3.12, Node 24, npm, uv, gh, local PostgreSQL 17
- [x] Download official UCI archive; verify SHA-256, sheets, 1,067,371 rows, date range
- [x] Verify licence (CC BY 4.0) and DOI (10.24432/C5CG6D — the DOI in the brief, C5BW33, belongs to the older *Online Retail* dataset)
- [x] Write `implementation_plan.md` with stage-to-system mapping

## Phase 2 — Foundation
- [x] `backend/` uv project, pinned lockfile, `customerpulse` CLI
- [x] `.gitignore` (data, artefacts, secrets, local DB, reference image)
- [x] Local `.env` with generated secrets (git-ignored)
- [x] Isolated local PostgreSQL cluster (`.localdb/`, port 55432)
- [x] `.env.example`
- [x] Ruff / mypy configuration
- [x] Frontend scaffold (Vite + React + TS + Tailwind)
- [x] All 15 Markdown documents

## Phase 3 — Dataset processing
- [x] Acquisition with fixed URL, local-archive fallback, checksum metadata
- [x] Pandera structural validation
- [x] Cleaning with priority-ordered exclusion reasons and reconciliation
- [x] Point-in-time customer features (23 model features)
- [x] Tests: cleaning, features, leakage

## Phase 4 — Segmentation
- [x] log1p + StandardScaler, K = 2..10 silhouette, inertia, stability ARI
- [x] Guarded K selection (selected K = 4, silhouette 0.365)
- [x] Rule-based segment naming + recommended actions
- [x] PCA projection, figures
- [x] Tests

## Phase 5 — Churn prediction
- [x] Monthly snapshots, 90-day inactivity labels, horizon sensitivity (60/90/120)
- [x] Purged chronological split (train 6 / val 3 / test 3 snapshots)
- [x] Logistic regression, random forest, HistGradientBoosting with class weights
- [x] Validation-only selection and threshold; single test evaluation
- [x] Top-decile precision, capture, lift; per-snapshot and seen/unseen customer analysis
- [x] Tests

## Phase 6 — SHAP and retention
- [x] LinearExplainer / TreeExplainer, aggregated to original features, additivity check
- [x] Global ranking, beeswarm sample, local top-decile explanations
- [x] Revenue projection, seasonal factor, cap, top-10% cohort, scenarios
- [x] Value-aware ranking comparison
- [x] Tests

## Phase 7 — Database and backend
- [x] SQLAlchemy models + Alembic migration
- [x] Least-privilege roles (migrator / writer / reader) + permission test
- [x] `customerpulse persist` (transactional, run status)
- [x] FastAPI read-only API under `/api/v1`
- [x] API tests

## Phase 8 — Frontend
- [x] Design system from reference (navy, grid, gold, red/gold/teal)
- [x] 8 pages wired to the API with loading/error/empty states
- [x] Retention simulator (client-side recalculation)
- [x] Vitest + Playwright tests

## Phase 9 — CI
- [x] CI workflow (lint, types, tests, build, migrations, secret scan)
- [x] Manual `workflow_dispatch` analysis workflow (defined; first GitHub run pending)
- [x] Verified green run (CI run 41064961471: backend 95 tests, frontend 19 + 39 e2e, gitleaks clean)

## Phase 10 — Deployment
- [x] Deployment configuration in repo (`backend/app.py`, `backend/.vercelignore`, `frontend/vercel.json`)
- [x] Step-by-step guide with secret placement (`docs/DEPLOYMENT.md`)
- [x] Neon Free project: roles, schema, migration 0001, run f72df6d9 persisted, permissions verified (2026-10-30)
- [ ] Vercel API + frontend projects (**blocked: owner must sign in to Vercel**)
- [ ] Production smoke tests (after deployment)

## Phase 11 — Final verification
- [x] Deterministic re-run at a committed SHA (results byte-identical apart from run id/time/SHA)
- [x] Full local test suite, lint, types
- [x] README with real screenshots and results; 15 Markdown documents
- [x] Commits pushed with the correct identity, no co-author trailers
- [ ] Live production verification (after deployment)
