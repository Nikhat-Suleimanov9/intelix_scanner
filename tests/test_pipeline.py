"""
tests/test_pipeline.py - Unit tests for src/pipeline.py.

All HTTP calls are mocked - no real network access required.
Tests use asyncio.run() because all pipeline functions are async.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import scan_file, _poll, ScanTimeoutError
from client import IntelixSubmitError, IntelixResultError

INTERVAL = 1
TIMEOUT  = 30


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------

class TestScanFile(unittest.TestCase):

    @patch("pipeline.submit_file", return_value={"jobStatus": "SUCCESS", "jobId": "job-1"})
    def test_returns_result_immediately_when_already_complete(self, _submit):
        result = asyncio.run(scan_file("file.exe", "token", "de", INTERVAL, TIMEOUT))
        self.assertEqual(result["jobId"], "job-1")

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("pipeline.get_result", return_value={"jobId": "job-1", "score": 0})
    @patch("pipeline.submit_file", return_value={"jobStatus": "IN_PROGRESS", "jobId": "job-1"})
    def test_polls_when_in_progress(self, _submit, _result, _sleep):
        result = asyncio.run(scan_file("file.exe", "token", "de", INTERVAL, TIMEOUT))
        self.assertEqual(result["jobId"], "job-1")

    @patch("pipeline.submit_file", side_effect=IntelixSubmitError("rejected"))
    def test_propagates_submit_error(self, _submit):
        with self.assertRaises(IntelixSubmitError):
            asyncio.run(scan_file("file.exe", "token", "de", INTERVAL, TIMEOUT))

    @patch("pipeline.submit_file", side_effect=FileNotFoundError("missing"))
    def test_propagates_file_not_found(self, _submit):
        with self.assertRaises(FileNotFoundError):
            asyncio.run(scan_file("file.exe", "token", "de", INTERVAL, TIMEOUT))

    @patch("pipeline.submit_file", return_value={"jobStatus": "FAILED", "jobId": "job-1"})
    def test_raises_on_unexpected_status(self, _submit):
        with self.assertRaises(IntelixResultError):
            asyncio.run(scan_file("file.exe", "token", "de", INTERVAL, TIMEOUT))
    

# ---------------------------------------------------------------------------
# _poll
# ---------------------------------------------------------------------------

class TestPoll(unittest.TestCase):

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("pipeline.get_result")
    def test_retries_until_result_ready(self, mock_result, _sleep):
        mock_result.side_effect = [None, None, {"score": 5}]
        result = asyncio.run(_poll("job-1", "token", "de", "file.exe", INTERVAL, TIMEOUT))
        self.assertEqual(mock_result.call_count, 3)
        self.assertEqual(result["score"], 5)


    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("pipeline.get_result", return_value=None)
    def test_raises_scan_timeout_error(self, _result, _sleep):
        with self.assertRaises(ScanTimeoutError):
            asyncio.run(_poll("job-1", "token", "de", "file.exe", INTERVAL, poll_timeout=0))

    @patch("asyncio.sleep", new_callable=AsyncMock)
    @patch("pipeline.get_result", return_value={"score": 0})
    def test_returns_on_first_poll_if_ready(self, mock_result, _sleep):
        result = asyncio.run(_poll("job-1", "token", "de", "file.exe", INTERVAL, TIMEOUT))
        self.assertEqual(mock_result.call_count, 1)
        self.assertEqual(result["score"], 0)
        


if __name__ == "__main__":
    unittest.main(verbosity=2)
