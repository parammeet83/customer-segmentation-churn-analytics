# CustomerPulse — Implementation Plan

CustomerPulse turns the UCI Online Retail II transaction history into four
connected business answers: **who our customers are** (RFM + K-Means),
**who is likely to stop buying** (behavioural churn model), **why** (SHAP),
and **what targeting the highest-risk 10% could be worth** (retention
scenarios). The guiding principle comes from the design reference:
*connect analysis to a business decision.*

## 1. Mapping the four analytical stages to the system

| Stage | Python pipeline (`backend/src/customerpulse`) | Database (PostgreSQL) | API (`/api/v1`) | Dashboard page |
|---|---|---|---|---|
| 1. RFM + K-Means segmentation | `features/rfm.py`, `segmentation/kmeans.py` (silhouette K selection, stability), `segmentation/naming.py` (rule-based names) | `segments`, `segment_k_selection`, `segment_assignments` | `/segments`, `/segments/{id}` | Customer Segmentation, Segment Profiles |
| 2. Behavioural churn prediction | `features/snapshots.py` (point-in-time features, labels), `churn/splits.py` (purged chronological split), `churn/models.py`, `churn/evaluate.py` | `model_metrics`, `model_curves`, `customer_snapshots`, `churn_scores` | `/churn/metrics`, `/churn/top-risk`, `/models/metrics`, `/customers` | Churn Risk, Model Performance |
| 3. SHAP explainability | `explainability/shap_explain.py` (global, beeswarm, local, additivity check) | `shap_global`, `shap_local`, run-level beeswarm JSON | `/churn/explanations` | SHAP Explainability |
| 4. Retention campaign | `analytics/retention.py` (revenue projection, seasonal factor, top-k cohort, scenarios) | `retention_scenarios`, `churn_scores.projected_revenue` | `/retention/scenarios`, `/retention/simulator-data` | Retention Simulator, Overview |

Cross-cutting: `ingestion/` (acquire + Pandera validation), `cleaning/`
(exclusion accounting), `analysis_runs` / `dataset_versions` /
`data_quality` tables, `/summary`, `/data-quality`, `/analysis-runs`, the
Overview and Data & Methodology pages.

## 2. Architecture

```
UCI zip ──► local / GitHub Actions pipeline (pandas, sklearn, SHAP)
             │  raw + intermediate data stay in data/ (git-ignored)
             ▼
        results bundle (artifacts/latest, pseudonymous keys only)
             │  `customerpulse persist` (writer role)
             ▼
        PostgreSQL (local cluster for dev, Neon Free for production)
             │  read-only role
             ▼
        FastAPI read-only API (Vercel Python function)
             ▼
        React + TypeScript + Vite dashboard (Vercel static)
```

Training never runs inside a web request. The API only reads the latest
*successful* analysis run and reports its status and version.

## 3. Key methodological decisions (verified on the real data)

* **Cleaning:** 22,523 rows duplicated across the two workbook sheets
  (1–9 Dec 2010) and 11,812 exact duplicate lines removed; 235,151 lines
  without a customer ID excluded; fees/postage codes excluded from
  merchandise value; cancellations tracked separately as returns.
* **Churn rule:** customer active in the 180 days before a monthly cutoff is
  "inactive" if no qualifying purchase in the next 90 days. 60/120-day
  horizons evaluated for sensitivity.
* **Temporal design:** 16 monthly snapshots (Jun 2010–Sep 2011). Train 6,
  validation 3, test 3; 4 snapshots purged so no label window crosses a
  partition boundary.
* **Imbalance:** the churn rate is close to 50% overall (38–62% by month), so
  this is a mild imbalance. Class weights are used; SMOTE is not (counts are
  discrete and customers repeat across snapshots).
* **Threshold:** maximising F-beta degenerated to "flag everyone" at ~50%
  prevalence, so the operating threshold is the highest validation threshold
  reaching recall ≥ 0.75.
* **Selection:** validation ROC-AUC, simpler family preferred within 0.002.
  Test evaluated once after selection.
* **Segmentation:** log1p + StandardScaler on lifetime RFM for all customers;
  K chosen by silhouette among K = 3–8 with size (≥3%) and stability
  (bootstrap ARI ≥ 0.75) guards.
* **Retention:** revenue projection from 180-day spend rate, capped at the
  99.5th percentile, with a seasonal factor computed from the previous year.
  Scenario values are labelled as estimates; a value-aware ranking is
  reported alongside the risk-only top 10%.

## 4. Phases and status

| Phase | Status |
|---|---|
| 1. Inspection and planning | Done (environment, dataset, licence, DOI verified) |
| 2. Project foundation | Done |
| 3. Dataset processing | Done, tested |
| 4. K-Means segmentation | Done, tested (K = 4, silhouette 0.365) |
| 5. Churn prediction | Done, tested (test ROC-AUC 0.767, top-10% lift 1.82×) |
| 6. SHAP and retention | Done, tested |
| 7. Database and backend | Done, tested (local PostgreSQL 17; roles verified) |
| 8. Frontend | Done, tested (8 pages; desktop/tablet/phone) |
| 9. CI and reproducibility | Done (CI green; manual analysis workflow defined) |
| 10. Deployment | Prepared; **blocked on owner sign-in to Neon and Vercel** |
| 11. Final verification | Done locally; production verification pending deployment |

See `TASKS.md` for the detailed checklist.

## 5. Deployment constraints

* Neon Free and Vercel Hobby only; no billing, trials or paid features.
* Separate Neon project and separate Vercel projects; nothing shared with
  any other project.
* Account authorisation and secret entry must be done by the owner in the
  provider dashboards; credentials are never pasted into chat.
