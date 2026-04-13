"""
pipeline.py - Scanning pipeline for the SophosLabs Intelix Static File Scanner.

Responsibilities
----------------
- Submit a file and poll until analysis is complete (or time out).
- Handle per-file errors without stopping other files (analyse_file).
- Run all files concurrently (run_all).

All HTTP calls are delegated to client.py.
"""

import logging
import time
import asyncio
import os

from client import (
    submit_file,
    get_result,
    IntelixSubmitError,
    IntelixResultError,
)


logger = logging.getLogger(__name__)


class ScanTimeoutError(Exception):
    """Raised when polling exceeds the configured timeout."""


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------

async def scan_file(
    file_path: str,
    token: str,
    region: str,
    poll_interval: int,
    poll_timeout: int,
) -> dict:
    """Submit a file for analysis and return the completed result.

    Raises:
        FileNotFoundError: If the file does not exist.
        IntelixSubmitError: If the upload request fails.
        IntelixResultError: If the analysis status is unexpected.
        ScanTimeoutError: If polling exceeds poll_timeout seconds.
    """
    
    result = await asyncio.to_thread(submit_file, file_path, token, region)
    file_name = os.path.basename(file_path)
    status = result.get("jobStatus")

    if status == "SUCCESS":
        logger.info("Analysis complete - File: %s - ID: %s", file_name, result.get("jobId"))
        return result
    if status == "IN_PROGRESS":
        return await _poll(
            result["jobId"], token, region, file_name,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )

    raise IntelixResultError(f"Analysis failed or unexpected status: {status}")


async def analyse_file(
    file_path: str,
    token: str,
    region: str,
    poll_interval: int,
    poll_timeout: int,
) -> tuple[str, dict | None]:
    """Run the full scan pipeline for a single file.

    Returns (file_path, result_dict) on success, or (file_path, None) if the
    file is not found, submission fails, polling times out, or the API returns
    an unexpected response.
    """
    try:
        result = await scan_file(
            file_path, token, region,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )
        return file_path, result

    except FileNotFoundError as exc:
        logger.error("File not found: %s", exc)
        return file_path, None

    except (IntelixSubmitError, IntelixResultError, ScanTimeoutError, RuntimeError) as exc:
        logger.error("Scan failed for '%s': %s", file_path, exc)
        return file_path, None

async def run_all(
    files: list[str],
    token: str,
    region: str,
    poll_interval: int,
    poll_timeout: int,
) -> list[tuple[str, dict | None]]:
    """Concurrently analyse all files and return their results."""
    tasks = [
        analyse_file(f, token, region, poll_interval, poll_timeout)
        for f in files
    ]
    return await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# Private
# ---------------------------------------------------------------------------

async def _poll(
    job_id: str,
    token: str,
    region: str,
    file_name: str,
    poll_interval: int,
    poll_timeout: int,
) -> dict:
    """Poll the result endpoint until the analysis is complete or the timeout expires.

    Waits poll_interval seconds between attempts. Raises ScanTimeoutError
    if no result is returned before the deadline.
    """
    deadline = time.monotonic() + poll_timeout
    attempt = 0

    while True:
        attempt += 1
        logger.info(
            "Polling for result (attempt %d) - File: %s - ID: %s",
            attempt, file_name, job_id,
        )

        
        result = await asyncio.to_thread(get_result, job_id, token, region)

        if result is not None:
            logger.info("Analysis complete - File: %s - ID: %s", file_name, job_id)
            return result

        if time.monotonic() >= deadline:
            raise ScanTimeoutError(
                f"Analysis did not complete within {poll_timeout}s "
                f"(job ID: {job_id})"
            )
    
        await asyncio.sleep(poll_interval)
