# Cleaning and feature engineering

Code: `backend/src/customerpulse/cleaning/clean.py`,
`features/snapshots.py`, `features/rfm.py`, `features/pseudonymize.py`.

## 1. Cleaning policy

Every raw row ends in exactly one of three places:

* **purchases**: qualifying merchandise lines, which drive R, F and M
* **returns**: cancellation lines for identified customers
* **excluded**: everything else, labelled with its first matching reason

The code asserts that `purchases + returns + excluded == raw rows`.

Exclusion rules, in priority order, with counts from the actual run:

| # | Reason | Rule | Rows |
|---|---|---|---|
| 1 | `sheet_overlap_duplicate` | second-sheet rows dated before 2010-12-10 (verified identical to the first sheet) | 22,523 |
| 2 | `exact_duplicate_line` | identical on all eight business columns | 11,812 |
| 3 | `invalid_invoice_date` | unparseable timestamp | 0 |
| 4 | `missing_customer_id` | no customer ID, so the line cannot be attributed | 235,151 |
| 5 | `missing_stock_code` | empty product code | 0 |
| 6 | `adjustment_invoice` | invoice prefix `A` (bad-debt adjustments) | 0* |
| 7 | `non_merchandise_code` | `POST`, `DOT`, `C2`, `C3`, `M`, `D`, `S`, `B`, `BANK CHARGES`, `ADJUST`, `ADJUST2`, `AMAZONFEE`, `CRUK`, `PADS`, `TEST001`, `TEST002` | 3,660 |
| 8 | `non_positive_price` | price ≤ 0 | 60 |
| 9 | `non_cancellation_negative_quantity` | negative quantity without a `C` invoice (stock write-offs) | 0* |
| 10 | `cancellation_positive_quantity` | `C` invoice with positive quantity | 0* |
| 11 | `zero_quantity` | quantity 0 | 0 |

\* These rows exist in the raw data, but every one of them also lacks a
customer ID, so rule 4 catches them first.

**Result:** 776,579 purchase lines on 36,594 invoices from 5,852 customers
(£17,068,582.72 gross), plus 17,586 return lines (£709,953.43).

### Revenue policy

* **Gross purchase value** is the sum of `quantity × price` over qualifying
  merchandise lines. This is the *monetary* measure.
* **Returns** are the absolute value of cancellation lines. They are tracked
  separately as `return_value` and `return_rate` and never reduce purchase
  frequency.
* Postage and fees are excluded from spend because they are not customer
  demand for products.
* A missing monetary value is never treated as zero. Rows with an invalid price
  are excluded and counted.

## 2. Point-in-time conventions

* An observation **cutoff** is a midnight timestamp.
* Features use transactions with `invoice_date < cutoff` only.
* A customer is **eligible** at a cutoff if they made a qualifying purchase in
  the lookback window `[cutoff − 180 days, cutoff)`.
* The observation date is always explicit. The system clock is never used.
* The scoring cutoff is `2011-12-10`, the midnight after the last transaction
  day.

These rules are enforced in `build_features`, which raises on a non-midnight
cutoff, and are tested in `tests/test_features.py` and `tests/test_leakage.py`.

## 3. Churn-model features (23)

| Feature | Definition |
|---|---|
| `recency_days` | days from the last qualifying purchase to the cutoff |
| `frequency` | distinct qualifying invoices in the 180-day lookback (**invoices, not lines**) |
| `monetary` | gross qualifying spend in the lookback (GBP) |
| `avg_order_value` | monetary ÷ frequency |
| `total_units` | units purchased in the lookback |
| `distinct_products` | distinct stock codes in the lookback |
| `active_months` | calendar months with a purchase in the lookback |
| `frequency_per_active_month` | frequency ÷ active months |
| `frequency_lifetime` | distinct invoices since the data begins |
| `monetary_lifetime` | gross spend since the data begins |
| `tenure_days` | days since first observed purchase (left-censored at Dec 2009) |
| `mean_gap_days` | mean days between distinct purchase days (missing if only one purchase day) |
| `std_gap_days` | standard deviation of those gaps |
| `recency_to_gap_ratio` | recency ÷ mean gap ("how overdue") |
| `spend_last_90` / `spend_prev_90` | spend in the most recent 90 days and the 90 days before |
| `spend_trend` | `log1p(spend_last_90) − log1p(spend_prev_90)` |
| `frequency_last_90` / `frequency_prev_90` | invoices in each 90-day half |
| `frequency_trend` | `frequency_last_90 − frequency_prev_90` |
| `return_value` | value of cancelled lines in the lookback |
| `return_rate` | return_value ÷ monetary, capped at 1 |
| `is_uk` | the customer's most frequent country is the United Kingdom |

The raw features are kept. Transformations happen inside the model pipeline:
signed `log1p` and scaling for the linear model, and native handling for the
trees. 26.6% of training rows have a single purchase day, so their gap features
are missing. The linear model imputes the **training** median and adds a
missing-value indicator.

`MODEL_FEATURES` never contains identifiers, dates, the country string or the
label. A test asserts this.

## 4. Segmentation RFM (customer base)

Segmentation describes the whole customer base at the scoring date. It uses
every qualifying purchase before `2011-12-10`, for all 5,852 customers:

* `recency_days` = days since the last purchase ever
* `frequency` = lifetime distinct invoices
* `monetary` = lifetime gross spend
* `tenure_days` is used for naming only

The broader window means long-inactive customers form their own segment
instead of disappearing.

## 5. Pseudonymous customer keys

`customer_key = "C-" + HMAC-SHA256(secret, customer_id)[:12]`

The secret (`CUSTOMERPULSE_PSEUDONYM_SECRET`) never leaves `.env` or the
provider secret stores. Raw IDs exist only in the local, git-ignored `data/`
folder. The bundle, database, API and dashboard use keys only, and a key
collision raises an error.

**Pseudonymisation is not anonymisation.** A distinctive behaviour profile
could still be linked back to a customer, so the API exposes aggregated
behavioural features only, with no product-level or transaction-level detail.
