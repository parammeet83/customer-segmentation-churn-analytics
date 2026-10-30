# data/ (git-ignored)

Raw, interim and processed datasets live here and are never committed.

* `raw/` - `online_retail_ii.zip` and the extracted workbook from the UCI
  Machine Learning Repository (Chen, D. (2012). Online Retail II.
  https://doi.org/10.24432/C5CG6D, CC BY 4.0).
* `interim/` - `transactions_raw.parquet` + `dataset_metadata.json` (checksums).
* `processed/` - cleaned purchases/returns, snapshots, features and reports.

Recreate everything with `cd backend && uv run --extra analysis customerpulse run-all`.
See `docs/DATASET.md`.
