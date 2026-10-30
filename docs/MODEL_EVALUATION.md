# Model evaluation

All numbers below come from the executed pipeline. The source is
`reports/results_summary.json`, and they are served by `/api/v1/models/metrics`
and `/api/v1/churn/metrics`. The test partition is the snapshots 2011-07-01,
2011-08-01 and 2011-09-01: 8,256 rows, 3,631 inactive (44.0%).

## Held-out test results

Each model uses its own validation-chosen threshold (the highest threshold
reaching validation recall ≥ 0.75).

| Model | ROC-AUC | PR-AUC | Recall | Precision | F1 | Brier | Threshold |
|---|---|---|---|---|---|---|---|
| **Logistic regression (selected)** | **0.767** | **0.691** | **0.678** | **0.655** | **0.666** | **0.197** | 0.415 |
| HistGradientBoosting | 0.765 | 0.684 | 0.737 | 0.630 | 0.679 | 0.198 | 0.383 |
| Random forest | 0.768 | 0.682 | 0.727 | 0.638 | 0.680 | 0.197 | 0.406 |

The three families are within 0.003 ROC-AUC on test. Selection was locked on
validation before test was scored, so the forest's marginally higher test
ROC-AUC does not change the choice. Changing it now would be test-set
selection.

### Confusion matrix (selected model, test)

| | Predicted active | Predicted inactive |
|---|---|---|
| **Actually active** | TN 3,328 | FP 1,297 |
| **Actually inactive** | FN 1,170 | TP 2,461 |

**Business meaning:**

* A **false negative** (1,170) is a customer who went quiet without being
  flagged. That revenue is lost with no chance to act.
* A **false positive** (1,297) costs one unnecessary contact. At the
  simulator's base assumption of £3 per contact, that is a small cost.
* The asymmetry is why the threshold targets recall. Test recall (0.678) is
  below the validation target (0.75) because the validation months had a
  higher base rate (58% vs 44%). That seasonal shift is a known limitation.

## Top-10% targeting (the decision the project supports)

Customers are ranked within each test month, and the top 10% of that month
are selected, which mirrors monthly operation:

| Model | Selected | True churners | Precision@10% | Capture rate | Lift |
|---|---|---|---|---|---|
| **Logistic regression** | 827 | 661 | **79.9%** | **18.2%** | **1.82×** |
| HistGradientBoosting | 827 | 656 | 79.3% | 18.1% | 1.80× |
| Random forest | 827 | 641 | 77.5% | 17.6% | 1.76× |

The selected share is 10.02% of the population (827 of 8,256, using ceil per
month).

With a 44% base rate, the maximum possible lift at 10% is 1 ÷ 0.44 ≈ 2.27×,
so 1.82× is a large share of the achievable gain. **Capture is capped at about
23%:** contacting 10% of customers can reach at most 10/44 of churners.

### Observed churn by risk decile (selected model, test)

| Decile | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Churn rate | 79.9% | 67.1% | 63.3% | 58.5% | 50.5% | 40.9% | 34.0% | 23.5% | 17.4% | 4.6% |

The ranking is monotonic: risk decreases steadily from decile 1 to decile 10.

## Variability over time

| Test cutoff | Customers | Churn rate | ROC-AUC | Recall | Precision@10% |
|---|---|---|---|---|---|
| 2011-07-01 | 2,722 | 48.4% | 0.773 | 0.663 | 84.2% |
| 2011-08-01 | 2,766 | 44.3% | 0.771 | 0.685 | 81.6% |
| 2011-09-01 | 2,768 | 39.3% | 0.761 | 0.688 | 74.0% |

ROC-AUC is stable (0.76–0.77). Precision@10% falls with the base rate as the
Q4 season approaches.

## Seen vs previously unseen customers

| Test rows | Rows | ROC-AUC | Recall |
|---|---|---|---|
| Customer seen in a train/validation snapshot | 6,967 | 0.782 | 0.617 |
| Customer never seen before | 1,289 | 0.692 | 0.928 |

The model ranks new customers noticeably less well, because they have little
history. Their high recall reflects a high base rate of inactivity among
first-time buyers, not better discrimination.

## Calibration

A reliability curve (10 quantile bins) is stored for each model and shown on
the Model Performance page. The test Brier score is 0.197. No post-hoc
calibration was applied. With balanced class weights and a training base rate
of 45%, the probability distortion from weighting is small. Calibrating on
validation would have imported its higher, seasonal base rate. Revenue-at-risk
figures use these probabilities directly and should be read as approximate.

## How evaluation is protected from leakage

See `CHURN_MODELING.md`. In summary: features come strictly before each
cutoff; partitions are chronological and purged; preprocessing is fitted
inside the training pipeline; model, hyper-parameters and threshold are chosen
on validation; test is scored once; and a test shuffles test labels to prove
selection doesn't depend on them.

## SHAP explainability

Code: `explainability/shap_explain.py`.

* **Explainer:** `shap.LinearExplainer` with an independent masker for the
  selected logistic regression. Background: 500 training-partition snapshots
  sampled with seed 42. Tree models, if selected, use `TreeExplainer` in
  `tree_path_dependent` mode. The interventional mode showed additivity
  errors of about 0.2 log-odds with HistGradientBoosting's binned splits.
* **Output space:** log-odds of the inactivity class (probability space for a
  random forest). Contributions to derived columns, such as missing-value
  indicators, are summed back onto the original feature.
* **Additivity check:** base value + Σ contributions reproduces every scored
  customer's model output. The maximum absolute error in this run is
  **1.8 × 10⁻¹⁵**. A test also checks additivity for all three model
  families.
* **Global:** mean |SHAP| over all 3,471 scored customers. The direction is
  the sign of the correlation between feature value and SHAP value. A
  300-customer deterministic sample feeds the beeswarm.
* **Local:** the top 8 contributions for each of the 348 top-decile
  customers (2,784 rows), with a plain-language sentence for each.

### Global drivers (actual)

| Rank | Feature | Mean \|SHAP\| | Direction |
|---|---|---|---|
| 1 | frequency_lifetime | 0.775 | higher values lower risk |
| 2 | frequency_prev_90 | 0.464 | higher values lower risk |
| 3 | mean_gap_days | 0.349 | higher values raise risk |
| 4 | frequency_trend | 0.272 | higher values lower risk |
| 5 | recency_to_gap_ratio | 0.270 | higher values raise risk |
| 6 | tenure_days | 0.266 | higher values raise risk |
| 7 | monetary_lifetime | 0.259 | higher values lower risk |
| 8 | frequency | 0.259 | higher values raise risk* |
| 9 | monetary | 0.190 | higher values raise risk* |
| 10 | recency_days | 0.178 | higher values lower risk* |

**In business language:** customers with a long purchase history, a habit of
ordering in the previous quarter and a rising order count are least likely to
go quiet. Customers with long typical gaps between orders, and those who are
overdue relative to their own rhythm, are most likely to.

\* **Read correlated features together.** The 180-day `frequency`, `monetary`
and `recency_days` overlap heavily with lifetime frequency, the 90-day splits
and `recency_to_gap_ratio`. A linear model splits credit between correlated
inputs, so a feature's individual sign can look counter-intuitive while the
group effect is intuitive. For example, recency is mostly carried by
`recency_to_gap_ratio`. These are associations the model learned, **not
causal effects**. Changing a customer's recency would not mechanically change
their risk.
