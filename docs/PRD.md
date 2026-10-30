# Product requirements: CustomerPulse

## Problem

An online retailer knows that customers who stop ordering are expensive to
replace. It does not know which customers are drifting away, why, or whether
contacting them would be worth the cost. Analyses that stop at a scatter plot
of clusters or a model score don't answer those questions.

**Guiding principle (from the design reference):** connect analysis to a
business decision.

## Users

| User | Needs |
|---|---|
| CRM / retention manager | Who to contact this month; expected value; what a campaign could return |
| Commercial lead | How the customer base splits into segments and where revenue concentrates |
| Analyst / data scientist | Trustworthy methodology: leakage controls, metrics, explanations, limitations |
| Recruiter / reviewer | A clear, honest, end-to-end demonstration of data skills |

## Objectives

1. Describe the customer base in business segments derived from RFM
   behaviour.
2. Predict which active customers are likely to make no purchase in the next
   90 days.
3. Explain the drivers of that risk globally and per customer, without
   implying causality.
4. Rank customers, select the highest-risk 10%, and estimate revenue at risk
   and campaign economics under explicit assumptions.
5. Let users change those assumptions and compare strategies.

## Scope: functional requirements

| ID | Requirement | Where |
|---|---|---|
| F1 | Reproducible acquisition of the official dataset with attribution and checksum | `ingestion/`, Data & Methodology page |
| F2 | Data-quality report with actual exclusion counts | `/data-quality`, Methodology page |
| F3 | RFM K-Means with silhouette-based K, size and stability guards | Customer Segmentation page |
| F4 | Business-readable segment names and recommended actions from tested rules | Segmentation, Segment Profiles |
| F5 | Explicit behavioural churn definition with leakage-safe temporal evaluation | Model Performance, Methodology |
| F6 | Baseline and alternative models compared on recall, precision, F1, ROC-AUC, PR-AUC, calibration and top-decile metrics | Model Performance |
| F7 | Global and individual SHAP explanations in plain language | SHAP page, customer drawer |
| F8 | Ranked customer list with filters, pagination and pseudonymous keys | Churn Risk page |
| F9 | Top-10% cohort, revenue at risk and scenario economics with visible assumptions | Overview, Simulator |
| F10 | Interactive simulator: target %, effectiveness, cost per contact, horizon, optional margin, ranking strategy, presets | Simulator |
| F11 | Run status and versioning; never silently serve failed or stale results | `/analysis-runs`, sidebar badge |

## Non-functional requirements

* **Truthfulness:**
  * No fabricated metrics.
  * Scenario values are always labelled as estimates.
  * Revenue and profit are kept distinct.
  * Inactivity is not described as permanent churn.
* **Privacy:** pseudonymous keys only; no raw IDs, invoices or products in the
  API.
* **Security:** read-only public API, least-privilege database roles, and no
  secrets in the repository or frontend.
* **Reproducibility:** pinned dependencies and lockfiles, a fixed seed, a
  recorded configuration, the dataset checksum and the git SHA for each run.
* **Accessibility and responsiveness:** usable at 390 px to 1440 px, keyboard
  navigable, and a table view for key charts.
* **Cost:** free tiers only (Neon Free, Vercel Hobby, GitHub Actions).

## Out of scope

* Real-time ingestion or scheduled retraining. The dataset is a fixed
  historical extract.
* Sending campaigns, or any write path from the dashboard.
* Causal estimates of campaign effect. These would need an experiment that
  this dataset does not contain.

## Success criteria and current status

| Criterion | Status |
|---|---|
| Model beats random targeting in the top decile | Yes. Test precision@10% is 79.9% vs a 44.0% base rate (lift 1.82×) |
| Leakage controls demonstrated by tests | Yes (`test_leakage.py`, `test_features.py`) |
| Every dashboard number comes from the API | Yes. Error states show no figures |
| Decision insight surfaced | Yes. The risk-only top 10% holds £15.6k expected revenue at risk; a risk × value ranking of the same 348 customers holds £81.0k (scenario estimates) |
| Deployed on free tiers | Pending owner authorisation of Neon and Vercel (see `DEPLOYMENT.md`) |
