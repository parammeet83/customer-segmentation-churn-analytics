# Segmentation methodology (RFM + K-Means)

Code: `backend/src/customerpulse/segmentation/kmeans.py`, `naming.py`.
Configuration: `SegmentationConfig` in `config.py`.

## Population and features

* **Population:** all 5,852 customers with at least one qualifying purchase
  before the scoring cutoff (2011-12-10).
* **Features:** lifetime `recency_days`, `frequency` (distinct invoices) and
  `monetary` (gross spend).
* **Transform:** `log1p` on all three, because each is heavily right-skewed
  (monetary ranges from a few pounds to £581k). Then `StandardScaler`, fitted
  on this population only. Non-finite or negative values raise an error.

Outliers are kept. The log transform limits their influence, and the
bootstrap stability check below would expose clusters that depend on a
handful of extreme customers.

## Choosing K

For K = 2 to 10:

* K-Means with `n_init=20` and `random_state=42` (deterministic)
* **Silhouette** computed in the scaled log space, on all customers (5,852 is
  below the 10,000-row sampling threshold, so no sampling was needed)
* **Inertia**
* **Cluster size shares**
* **Bootstrap stability:** 10 refits on 80% subsamples, each compared with the
  full-data labels using the adjusted Rand index (ARI)

**Selection rule:** the highest silhouette among K in [3, 8], with every
cluster holding at least 3% of customers and mean stability ARI ≥ 0.75.

K = 2 is reported but not eligible. Two groups ("good" and "lapsed") are too
coarse to drive different retention actions. K above 8 is excluded because
that many segments can't be acted on.

### Actual results

| K | Silhouette | Smallest cluster | Stability ARI | Eligible |
|---|---|---|---|---|
| 2 | 0.438 | 39.7% | 0.996 | outside range |
| 3 | 0.348 | 20.5% | 0.965 | yes |
| **4** | **0.365** | **20.1%** | **0.952** | **selected** |
| 5 | 0.342 | 7.8% | 0.929 | yes |
| 6 | 0.336 | 7.6% | 0.856 | yes |
| 7 | 0.303 | 5.7% | 0.804 | yes |
| 8 | 0.295 | 5.9% | 0.790 | yes |
| 9 | 0.290 | 4.3% | 0.867 | outside range |
| 10 | 0.289 | 3.7% | 0.872 | outside range |

**Selected K = 4, silhouette 0.365.** That is moderate separation, which is
typical of RFM data: customer behaviour is a continuum, not a set of tight
clusters. The segments are useful summaries of that continuum, not natural
categories.

Cluster IDs are relabelled by descending median monetary value, so ID 0 is
always the highest-value cluster. That keeps IDs and colours stable across
runs.

## Naming segments in business language

Each cluster's **median** recency, frequency, monetary value and tenure are
compared with population quantiles:

* recency: `recent` ≤ 33rd percentile (40.5 d); `lapsing` ≤ 67th (263.5 d); otherwise `lapsed`
* frequency and monetary: `low` ≤ 33rd percentile, `high` ≥ 67th, otherwise `mid`
  (frequency 2 / 5 invoices; monetary £458 / £1,572)
* `is_new`: tenure ≤ 25th percentile (311.5 d) **and** low frequency
* `established`: tenure ≥ median (529.4 d)

Ordered rules (the first match wins), tested in `tests/test_segmentation.py`:

1. recent + high F + high M → **Champions**
2. recent + not-low M + (high F, or mid F and established) → **Loyal Customers**
3. recent + new → **New Customers**
4. recent (otherwise) → **Promising Customers**
5. not recent + (high F or high M) → **At Risk**
6. lapsing → **Needs Attention**
7. lapsed + low F → **Hibernating Customers**
8. otherwise → a neutral descriptive name, e.g. "Lapsed, mid-frequency, mid-spend customers"

Duplicate names are disambiguated by spend ("higher spend" / "lower spend").
"Loyal" requires above-median tenure, because one or two recent orders don't
make a loyal relationship. In this run, the cluster with a median of 3
invoices and 218 days of tenure is therefore named **Promising** rather than
Loyal.

### Actual segment profiles (medians)

| ID | Segment | Customers | Share | Revenue share | Recency (d) | Invoices | Spend | Tenure (d) |
|---|---|---|---|---|---|---|---|---|
| 0 | Champions | 1,178 | 20.1% | 73.2% | 16 | 13 | £4,908 | 678 |
| 1 | At Risk | 1,459 | 24.9% | 17.0% | 182 | 5 | £1,457 | 619 |
| 2 | Promising Customers | 1,245 | 21.3% | 6.1% | 24 | 3 | £720 | 218 |
| 3 | Hibernating Customers | 1,970 | 33.7% | 3.7% | 400 | 1 | £277 | 438 |

### Recommended actions (`naming.ACTIONS`)

* **Champions:** protect and reward (early access, loyalty perks, referrals).
  Avoid discount-led contact that erodes margin.
* **At Risk:** prioritise win-back. These customers had high historical value
  but have slowed, so contact them personally before the gap widens.
* **Promising Customers:** nurture towards a repeat cadence with
  recommendations and modest incentives.
* **Hibernating Customers:** low-cost reactivation only (email).

## Visualisation

The dashboard shows a 2-D **PCA projection** of the scaled log-RFM space. The
axes explain 76% and 19% of the variance and are labelled "Projection axis 1
and 2 (PCA)" so they aren't mistaken for raw RFM features. An alternative
view plots original recency against monetary value on log scales. The scatter
uses a deterministic 1,500-customer sample.

## Relationship to churn modelling

Segment membership is **not** a churn-model feature. Segments describe the
customer base at the scoring date. Historical snapshots would need their own
point-in-time segmentation to be used as features without leakage. The two
analyses meet in the scored table, which shows the segment mix of the top-10%
risk cohort.
