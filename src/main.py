"""
main.py - Entry point for the SophosLabs Intelix Static File Scanner.

Usage
-----
1. Export credentials (only these come from the environment):
    export INTELIX_CLIENT_ID=<your-client-id>
    export INTELIX_CLIENT_SECRET=<your-client-secret>

2. Run with files and optional arguments:
    python main.py samples/sample.exe samples/sample.docx samples/sample.pdf
    python main.py --region us-east --reports-dir out samples/sample.exe samples/sample.docx samples/sample.pdf

Activity and errors are logged to stdout and to logs/intelix_scanner.log.
Each analysis report is saved as a .txt file in the reports/ directory
(configurable via --reports-dir).
"""

import argparse
import logging
import sys
import asyncio

from logger import setup_logging
from config import load_config
from client import get_token, IntelixAuthError, validate_region, POLL_INTERVAL_SECONDS, POLL_TIMEOUT_SECONDS
from pipeline import run_all
from report_writer import save_report

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Submit files to the SophosLabs Intelix Static File Analysis API "
            "and save the JSON reports as .txt files."
        )
    )
    parser.add_argument("files", nargs="+", help="Files to scan")

    parser.add_argument("--region", default="de", choices=["us-east", "de", "au"])
    parser.add_argument("--reports-dir", default="reports")


    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """
    Orchestrate authentication and per-file analysis.

    Returns:
        0  - all files analysed successfully.
        1  - configuration or authentication error (fatal).
        2  - one or more files failed analysis (partial success possible).
    """
    log_file = setup_logging()
    args = _build_arg_parser().parse_args()

    # client_id and client_secret come from environment variables only
    try:
        config = load_config(args)
    except EnvironmentError as exc:
        logger.error("Configuration error: %s", exc)
        return 1

    logger.info("Intelix Static File Scanner started.")
    logger.info("Region: %s | Reports: %s | Log: %s", config.region, config.reports_dir, log_file)
    logger.info("Files to analyse: %d", len(args.files))

    try:
        validate_region(config.region)
        token = get_token(config.client_id, config.client_secret)
    except ValueError as exc:
        logger.error("Invalid region: %s", exc)
        return 1
    except IntelixAuthError as exc:
        logger.error("Authentication failed: %s", exc)
        return 1

    try:
        results = asyncio.run(
            run_all(args.files, token, config.region, POLL_INTERVAL_SECONDS, POLL_TIMEOUT_SECONDS)
        )
    except Exception as exc:
        logger.error("Unexpected error during analysis: %s", exc)
        return 1

    successes = []
    failures = []

    for file_path, result in results:
        if result is None:
            failures.append(file_path)
            continue

        try:
            report_path = save_report(result, file_path, output_dir=config.reports_dir)
            successes.append((file_path, report_path))
        except Exception as exc:
            logger.error("Failed to save report for '%s': %s", file_path, exc)
            failures.append(file_path)

    # ---- Summary ----
    logger.info("=" * 60)
    logger.info("SUMMARY  -  OK: %d  |  Failed: %d", len(successes), len(failures))
    for original, report in successes:
        logger.info("  OK  %s  ->  %s", original, report)
    for f in failures:
        logger.info("  FAILED  %s", f)
    logger.info("=" * 60)

    exit_code = 0 if not failures else 2
    logger.info("Exiting with code %d", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
