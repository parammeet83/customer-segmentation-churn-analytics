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
- [ ] `.env.example`
- [ ] Ruff / mypy configuration
- [ ] Frontend scaffold (Vite + React + TS + Tailwind)
- [ ] All 15 Markdown documents

## Phase 3 — Dataset processing
- [x] Acquisition with fixed URL, local-archive fallback, checksum metadata
- [x] Pandera structural validation
- [x] Cleaning with priority-ordered exclusion reasons and reconciliation
- [x] Point-in-time customer features (23 model features)
- [ ] Tests: cleaning, features, leakage

## Phase 4 — Segmentation
- [x] log1p + StandardScaler, K = 2..10 silhouette, inertia, stability ARI
- [x] Guarded K selection (selected K = 4, silhouette 0.365)
- [x] Rule-based segment naming + recommended actions
- [x] PCA projection, figures
- [ ] Tests

## Phase 5 — Churn prediction
- [x] Monthly snapshots, 90-day inactivity labels, horizon sensitivity (60/90/120)
- [x] Purged chronological split (train 6 / val 3 / test 3 snapshots)
- [x] Logistic regression, random forest, HistGradientBoosting with class weights
- [x] Validation-only selection and threshold; single test evaluation
- [x] Top-decile precision, capture, lift; per-snapshot and seen/unseen customer analysis
- [ ] Tests

## Phase 6 — SHAP and retention
- [x] LinearExplainer / TreeExplainer, aggregated to original features, additivity check
- [x] Global ranking, beeswarm sample, local top-decile explanations
- [x] Revenue projection, seasonal factor, cap, top-10% cohort, scenarios
- [x] Value-aware ranking comparison
- [ ] Tests

## Phase 7 — Database and backend
- [ ] SQLAlchemy models + Alembic migration
- [ ] Least-privilege roles (migrator / writer / reader) + permission test
- [ ] `customerpulse persist` (transactional, run status)
- [ ] FastAPI read-only API under `/api/v1`
- [ ] API tests

## Phase 8 — Frontend
- [ ] Design system from reference (navy, grid, gold, red/gold/teal)
- [ ] 8 pages wired to the API with loading/error/empty states
- [ ] Retention simulator (client-side recalculation)
- [ ] Vitest + Playwright tests

## Phase 9 — CI
- [ ] CI workflow (lint, types, tests, build, migrations, secret scan)
- [ ] Manual `workflow_dispatch` analysis workflow
- [ ] Verified green run

## Phase 10 — Deployment
- [ ] Neon Free project (owner authorisation required)
- [ ] Vercel API + frontend projects (owner authorisation required)
- [ ] Production smoke tests

## Phase 11 — Final verification
- [ ] Full test suite, secret scan, 15 docs reviewed, screenshots, push
