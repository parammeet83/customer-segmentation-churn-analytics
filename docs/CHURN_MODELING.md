# Churn modelling

Code: `features/snapshots.py` (labels), `churn/splits.py`, `churn/models.py`,
`churn/evaluate.py`. Configuration: `ChurnConfig` in `config.py`.

## Behavioural churn definition

> A customer who made a qualifying purchase in the **180 days** before a cutoff
> is labelled **inactive (churned = 1)** if they make **no qualifying purchase
> in the 90 days starting at the cutoff**. Otherwise churned = 0.

**This project predicts future purchase inactivity under a defined historical
behavioural rule. It does not establish that a customer has contractually or
permanently churned.**

* Snapshots are monthly, on the first day of each month at 00:00.
* Features use `[−∞, cutoff)` and the label uses `[cutoff, cutoff + 90 d)`.
  The two windows never overlap.
* A snapshot is created only if its full label window lies inside the data
  (data end = 2011-12-10). `label_churn` raises an error if it doesn't.
* The first snapshot is 2010-06-01, so every snapshot has a full 180-day
  lookback after the data start.
* Purchases are "qualifying" by the same rule for features and labels.

### Why 90 days

Across the training rows, the median gap between purchase days is **60 days**,
the 75th percentile **101 days** and the 90th **162 days**. Ninety days
without an order is therefore unusual for an active customer. A 60-day window
would flag many routine gaps; 120 days would leave fewer test snapshots and
detect inactivity later.

Sensitivity across horizons (same 180-day lookback):

| Horizon | Snapshots | Observations | Mean churn | Range by month |
|---|---|---|---|---|
| 60 d | 17 | 50,852 | 58.8% | 47%–71% |
| **90 d (used)** | 16 | 47,933 | 50.3% | 38%–62% |
| 120 d | 15 | 45,165 | 44.6% | 34%–56% |

## Temporal design and purging

There are 16 monthly snapshots, 2010-06-01 to 2011-09-01.

| Partition | Cutoffs | Rows | Customers | Churn rate |
|---|---|---|---|---|
| Train | 2010-06 → 2010-11 (6) | 17,119 | 3,893 | 45.5% |
| *Purged* | 2010-12, 2011-01 | — | — | — |
| Validation | 2011-02 → 2011-04 (3) | 9,985 | 3,745 | 58.0% |
| *Purged* | 2011-05, 2011-06 | — | — | — |
| Test | 2011-07 → 2011-09 (3) | 8,256 | 3,118 | 44.0% |

**Purge rule:** every snapshot in an earlier partition must satisfy
`cutoff + 90 d ≤ first cutoff of the next partition`. Snapshots that break
this are dropped, not moved. As a result, no training label observes the
validation period and no validation label observes the test period.
`assert_no_label_overlap` enforces this, and tests check it.

**Repeated customers:** a customer can appear in several monthly snapshots
(4.4 training rows per customer on average). This is a panel structure, not
independent rows. Evaluation is therefore by *time*, and a secondary analysis
separates test customers seen earlier from customers seen for the first time
(see `MODEL_EVALUATION.md`).

## Class imbalance

The overall churn rate is close to 50% (45% in train), so imbalance is
**mild**. It varies strongly with season (38%–62% by month).

* All models use `class_weight="balanced"` (or `balanced_subsample` for the
  forest).
* **SMOTE is not used.** Several features are discrete counts (invoices,
  active months), and synthetic interpolation would create impossible
  customers. The same customer also appears in many snapshots, so
  nearest-neighbour synthesis would blend a customer with copies of
  themselves.
* No resampling happens anywhere, so it can't contaminate splits.

## Models and preprocessing

All preprocessing lives **inside** an sklearn `Pipeline` that is fitted on
training rows only. A test checks that the imputer's statistics equal the
training medians.

| Family | Pipeline | Hyper-parameters tried |
|---|---|---|
| Logistic regression | median imputer + missing indicators → signed `log1p` → `StandardScaler` → `LogisticRegression(class_weight="balanced")` | C ∈ {0.01, 0.1, 1} |
| Random forest | median imputer + indicators → `RandomForestClassifier(300 trees, balanced_subsample)` | min_samples_leaf ∈ {10, 40}, max_features ∈ {sqrt, 0.5} |
| HistGradientBoosting | native missing-value handling, `class_weight="balanced"`, early stopping **off** (its random internal hold-out would mix months) | learning_rate ∈ {0.03, 0.1}, max_leaf_nodes ∈ {15, 31}, 200 iterations |

Deep learning is deliberately not used: this is a small tabular problem with
about 17k training rows.

## Selection protocol (validation only)

1. Fit every configuration on train.
2. Score validation. The best configuration per family is chosen by
   **validation ROC-AUC**.
3. The final family is the best validation ROC-AUC, preferring the simpler
   family when the gap is within 0.002.
4. **Operating threshold:** the highest validation threshold that still
   reaches recall ≥ 0.75.
5. Freeze everything, then score the test partition **once**.

`test_selection_and_threshold_do_not_depend_on_test_labels` shuffles test
labels and asserts that the selected family, parameters and threshold don't
change.

### Why not maximise F-beta for the threshold?

The first implementation maximised F2 on validation. With prevalence near 50%,
F2 is maximised by flagging almost everyone (test recall 0.97, 1,201 true
negatives out of 4,625). That is useless as an operating point, so it was
replaced with an explicit recall target, which is easier for the business to
reason about.

### Validation results (ROC-AUC)

| Model | Config | ROC-AUC |
|---|---|---|
| **Logistic regression** | **C = 0.1** | **0.7751** |
| Logistic regression | C = 1.0 | 0.7750 |
| Logistic regression | C = 0.01 | 0.7745 |
| Random forest | sqrt, leaf 40 | 0.7708 |
| HistGradientBoosting | lr 0.03, 15 leaves | 0.7700 |
| Random forest | 0.5, leaf 40 | 0.7697 |
| HistGradientBoosting | lr 0.03, 31 leaves | 0.7619 |
| Random forest | sqrt, leaf 10 | 0.7578 |
| HistGradientBoosting | lr 0.1, 15 leaves | 0.7558 |
| Random forest | 0.5, leaf 10 | 0.7539 |
| HistGradientBoosting | lr 0.1, 31 leaves | 0.7421 |

Selected: **logistic regression, C = 0.1, threshold 0.415**.

Test results are in `MODEL_EVALUATION.md`.

## Scoring the current customer base

The selected pipeline (trained on the training partition and evaluated on
test) scores the 3,471 customers who purchased in the 180 days before
2011-12-10. The model is deliberately **not** refitted on validation and test
data. Its test metrics therefore describe exactly the model that produced the
scores. The trade-off is that the model has seen no data newer than November
2010. Refitting on all labelled months is a documented next step.

Risk bands are defined by rank: **Very high** = top 10%, **High** = next 20%,
**Medium** = next 30%, **Low** = the remaining 40%. 1,518 scored customers
are above the operating threshold.

## Limitations

* Only one three-month test period exists after purging. There is too little
  history for rolling-origin backtesting.
* Seasonality shifts the base rate (validation 58% vs test 44%). Threshold
  recall therefore fell from 0.75 on validation to 0.68 on test.
* Customers with no earlier snapshot are ranked less well (test ROC-AUC 0.69
  vs 0.78).
* Inactivity is not the same as permanent loss. Seasonal buyers can be
  labelled inactive and return later.
