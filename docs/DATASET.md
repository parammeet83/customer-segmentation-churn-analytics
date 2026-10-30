# Dataset

## Source and attribution

| Item | Value |
|---|---|
| Name | Online Retail II |
| Publisher | UCI Machine Learning Repository, dataset #502 |
| Landing page | https://archive.ics.uci.edu/dataset/502/online+retail+ii |
| DOI | https://doi.org/10.24432/C5CG6D |
| Licence | Creative Commons Attribution 4.0 International (CC BY 4.0) |
| Citation | Chen, D. (2012). *Online Retail II* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D |

> **DOI note.** The project brief cited `10.24432/C5BW33`. That DOI belongs to
> the older, single-year *Online Retail* dataset (UCI #352). The two-year
> *Online Retail II* dataset used here is `10.24432/C5CG6D`. Both were checked
> against the UCI pages on 2026-10-30.

CC BY 4.0 allows use, adaptation and redistribution with attribution. The raw
data is still **not** committed to this repository. It is downloaded from the
official source so the provenance stays unambiguous and the repository stays
small.

## What the data is

These are transaction lines from one UK-based, non-store online retailer that
sells all-occasion gift-ware, much of it to wholesalers. Each row is one
product line on an invoice.

| Column | Meaning |
|---|---|
| `Invoice` | 6-digit invoice number; a `C` prefix marks a cancellation, `A` an accounting adjustment |
| `StockCode` | product code (5 digits, sometimes with a letter suffix) or a service code such as `POST` |
| `Description` | product name |
| `Quantity` | units on the line (negative for cancellations and stock adjustments) |
| `InvoiceDate` | timestamp |
| `Price` | unit price in GBP |
| `Customer ID` | 5-digit customer number (missing for many lines) |
| `Country` | customer's country |

## Verified facts (from the actual download)

| Check | Result |
|---|---|
| Archive | `online_retail_ii.zip`, 45,622,418 bytes |
| Archive SHA-256 | `572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb` |
| Workbook SHA-256 | `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980` |
| Sheet `Year 2009-2010` | 525,461 rows, 2009-12-01 07:45 → 2010-12-09 20:01 |
| Sheet `Year 2010-2011` | 541,910 rows, 2010-12-01 08:26 → 2011-12-09 12:50 |
| Total raw rows | 1,067,371 (matches the UCI listing) |
| Distinct customer IDs | 5,942 |
| Countries | 43 |
| Rows without customer ID | 243,007 |
| Cancellation rows (`C…`) | 19,494 |
| Negative-quantity rows | 22,950 |
| Zero or negative price rows | 6,207 |
| Invalid timestamps | 0 |

**Sheet overlap.** 1–9 December 2010 appears in *both* sheets. The two copies
were compared and are identical: 22,523 rows and 1,088 invoices each. The copy
in the second sheet is dropped.

## Acquisition process

`customerpulse acquire` (also the first step of `run-all`) does the following:

1. Downloads from the fixed official URL
   `https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip`. No
   user-supplied URL is ever accepted. If the archive is already in
   `data/raw/`, it is reused.
2. Alternatively, `--local-archive PATH` copies a previously downloaded archive.
   This is the offline fallback. Fabricated or substitute data is never used.
3. Computes the SHA-256 and compares it with the checksum recorded in
   `config.py`. A mismatch is logged and stored in the metadata
   (`zip_checksum_matches_recorded`). The manual analysis workflow fails on a
   mismatch.
4. Reads both sheets with explicit string types for identifiers, checks that
   all expected columns exist, and adds a `source_sheet` column.
5. Writes `data/interim/transactions_raw.parquet` and `dataset_metadata.json`
   (checksums, per-sheet rows and date ranges, acquisition time).

`customerpulse validate` then applies a Pandera schema (`ingestion/validate.py`).
It checks invoice code format, types, the customer ID range and sheet names.

## Reproducing from a clean checkout

```bash
cd backend
uv sync --frozen --extra analysis
cp ../.env.example ../.env       # then set CUSTOMERPULSE_PSEUDONYM_SECRET
uv run customerpulse run-all     # downloads, validates, cleans, models, writes the bundle
```

`data/`, `artifacts/`, `*.zip`, `*.xlsx` and `*.parquet` are git-ignored.

## Limitations to keep in mind

* **One retailer and one period.** The data comes from a single UK retailer
  between December 2009 and December 2011, and the customers are mostly
  business buyers. It does **not** represent current, Indian or global
  consumer behaviour.
* **Geography.** 90.1% of qualifying purchase lines come from UK customers.
* **Missing customers.** About 22% of raw lines have no customer ID and cannot
  be used for customer analytics.
* **Censoring.** History starts in December 2009, so tenure is left-censored:
  long-standing customers can look newer than they are.
* **Seasonality.** Revenue peaks strongly in Q4 every year (visible on the
  Data & Methodology page). This affects inactivity labels and revenue
  projections.
* **No interventions.** There is no marketing, campaign or contact data, so
  retention effects cannot be observed.
