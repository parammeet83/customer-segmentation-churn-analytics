"""Dataset acquisition: download (fixed official URL only), verify, convert.

The Excel workbook is read once and cached as Parquet so later pipeline
stages are fast and deterministic. Metadata (checksums, row counts, date
coverage per sheet) is written next to the Parquet file.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from customerpulse.config import INTERIM_DIR, RAW_DIR, DatasetSource

logger = logging.getLogger(__name__)

RAW_PARQUET = "transactions_raw.parquet"
RAW_METADATA = "dataset_metadata.json"
EXPECTED_COLUMNS = [
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
]


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download_archive(source: DatasetSource, raw_dir: Path = RAW_DIR) -> Path:
    """Download the official archive unless it is already present locally."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / source.zip_filename
    if target.exists():
        logger.info("Using existing local archive %s", target)
        return target
    if not source.url.startswith("https://archive.ics.uci.edu/"):
        raise ValueError("Only the official UCI source URL is permitted")
    logger.info("Downloading %s", source.url)
    tmp = target.with_suffix(".part")
    with urllib.request.urlopen(source.url, timeout=120) as resp, tmp.open("wb") as fh:  # noqa: S310
        shutil.copyfileobj(resp, fh)
    tmp.replace(target)
    return target


def extract_workbook(archive: Path, source: DatasetSource) -> Path:
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        if source.xlsx_filename not in names:
            raise ValueError(f"Archive does not contain {source.xlsx_filename}: {names}")
        zf.extract(source.xlsx_filename, archive.parent)
    return archive.parent / source.xlsx_filename


def read_workbook(xlsx: Path, sheets: tuple[str, ...]) -> pd.DataFrame:
    frames = []
    for sheet in sheets:
        df = pd.read_excel(
            xlsx,
            sheet_name=sheet,
            dtype={"Invoice": str, "StockCode": str, "Description": str, "Country": str},
            engine="openpyxl",
        )
        missing = set(EXPECTED_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"Sheet {sheet!r} is missing columns {sorted(missing)}")
        df = df[EXPECTED_COLUMNS].copy()
        df["source_sheet"] = sheet
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def acquire(
    source: DatasetSource | None = None,
    raw_dir: Path = RAW_DIR,
    interim_dir: Path = INTERIM_DIR,
    local_archive: Path | None = None,
    force: bool = False,
) -> dict:
    """Acquire, verify and cache the dataset. Returns the metadata dict."""
    source = source or DatasetSource()
    interim_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = interim_dir / RAW_PARQUET
    meta_path = interim_dir / RAW_METADATA
    if parquet_path.exists() and meta_path.exists() and not force:
        logger.info("Cached raw parquet already present: %s", parquet_path)
        return json.loads(meta_path.read_text())

    if local_archive is not None:
        if not local_archive.is_file():
            raise FileNotFoundError(local_archive)
        raw_dir.mkdir(parents=True, exist_ok=True)
        archive = raw_dir / source.zip_filename
        if local_archive.resolve() != archive.resolve():
            shutil.copyfile(local_archive, archive)
    else:
        archive = download_archive(source, raw_dir)

    zip_sha = sha256_file(archive)
    checksum_matches = zip_sha == source.expected_zip_sha256
    if not checksum_matches:
        logger.warning(
            "Archive checksum %s differs from the recorded checksum %s; "
            "the source may have been re-packaged. Continuing, and recording the mismatch.",
            zip_sha,
            source.expected_zip_sha256,
        )
    xlsx = extract_workbook(archive, source)
    df = read_workbook(xlsx, source.sheets)
    df.to_parquet(parquet_path, index=False)

    per_sheet = {}
    for sheet, part in df.groupby("source_sheet"):
        per_sheet[str(sheet)] = {
            "rows": int(len(part)),
            "date_min": str(part["InvoiceDate"].min()),
            "date_max": str(part["InvoiceDate"].max()),
        }
    meta = {
        "source_name": source.name,
        "source_url": source.url,
        "landing_page": source.landing_page,
        "doi": source.doi,
        "licence": source.licence,
        "citation": source.citation,
        "zip_sha256": zip_sha,
        "zip_checksum_matches_recorded": checksum_matches,
        "xlsx_sha256": sha256_file(xlsx),
        "raw_rows": int(len(df)),
        "columns": EXPECTED_COLUMNS,
        "sheets": per_sheet,
        "date_min": str(df["InvoiceDate"].min()),
        "date_max": str(df["InvoiceDate"].max()),
        "acquired_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def load_raw(interim_dir: Path = INTERIM_DIR) -> pd.DataFrame:
    path = interim_dir / RAW_PARQUET
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `customerpulse acquire` first.")
    return pd.read_parquet(path)
