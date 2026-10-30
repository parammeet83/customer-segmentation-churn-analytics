"""Command-line entry point: ``uv run customerpulse <command>``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="customerpulse", description="CustomerPulse analysis pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    acq = sub.add_parser("acquire", help="Download (official UCI URL) or load a local archive and cache it")
    acq.add_argument("--local-archive", type=Path, help="Path to a previously downloaded online_retail_ii.zip")
    acq.add_argument("--force", action="store_true", help="Rebuild the cached Parquet")

    for name, help_text in (
        ("validate", "Validate the raw table structure"),
        ("clean", "Apply cleaning rules and write the cleaning report"),
        ("features", "Build labelled monthly snapshots, scoring features and RFM"),
        ("segment", "K-Means segmentation with silhouette-based K selection"),
        ("churn", "Train, select (validation) and evaluate (test) churn models"),
        ("score", "Score current customers and project revenue"),
        ("explain", "Compute SHAP explanations for the selected model"),
        ("simulate", "Compute retention scenarios for the top-risk cohort"),
        ("bundle", "Assemble the results bundle for persistence"),
    ):
        sub.add_parser(name, help=help_text)

    run = sub.add_parser("run-all", help="Run every analysis stage in order")
    run.add_argument("--local-archive", type=Path)

    per = sub.add_parser("persist", help="Load the results bundle into PostgreSQL (writer role)")
    per.add_argument("--bundle", type=Path, default=None)

    sub.add_parser("setup-roles", help="Create/update least-privilege database roles (admin connection)")

    args = parser.parse_args(argv)
    from dotenv import load_dotenv

    from customerpulse.config import REPO_ROOT

    load_dotenv(REPO_ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.command == "persist":
        from customerpulse.database.persist import persist_bundle

        run_id = persist_bundle(args.bundle)
        print(json.dumps({"persisted_run_id": run_id}))
        return 0
    if args.command == "setup-roles":
        from customerpulse.database.roles import setup_roles

        setup_roles()
        return 0

    from customerpulse import pipeline

    if args.command == "acquire":
        from customerpulse.ingestion.acquire import acquire

        meta = acquire(local_archive=args.local_archive, force=args.force)
        print(json.dumps({k: meta[k] for k in ("raw_rows", "date_min", "date_max", "zip_sha256")}, indent=2))
        return 0
    if args.command == "run-all":
        manifest = pipeline.run_all(local_archive=args.local_archive)
        print(json.dumps({"run_id": manifest["run_id"]}))
        return 0
    result = pipeline.STAGES[args.command]()
    if isinstance(result, dict):
        print(json.dumps({k: v for k, v in result.items() if not isinstance(v, (list, dict))}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
