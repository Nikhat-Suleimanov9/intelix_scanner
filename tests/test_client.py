"""
tests/test_client.py - Unit tests for src/client.py.

All HTTP calls are mocked - no real network access required.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from client import (
    get_token,
    submit_file,
    get_result,
    validate_region,
    _guess_mime_type,
    IntelixAuthError,
    IntelixSubmitError,
    IntelixResultError,
)


class _FakeResponse:
    def __init__(self, status_code: int, body: dict, headers: dict | None = None) -> None:
        self.status_code = status_code
        self.text = json.dumps(body)
        self._body = body
        self.headers = headers or {}

    def json(self) -> dict:
        return self._body


def _mock_response(status_code: int, body: dict, headers: dict | None = None) -> _FakeResponse:
    return _FakeResponse(status_code, body, headers)


# ---------------------------------------------------------------------------
# get_token
# ---------------------------------------------------------------------------

class TestGetToken(unittest.TestCase):

    @patch("client.requests.post")
    def test_returns_token_on_success(self, mock_post):
        mock_post.return_value = _mock_response(200, {"access_token": "tok123"})
        self.assertEqual(get_token("id", "secret"), "tok123")

    @patch("client.requests.post")
    def test_raises_on_non_200(self, mock_post):
        mock_post.return_value = _mock_response(401, {"error": "unauthorized"})
        with self.assertRaises(IntelixAuthError):
            get_token("id", "bad_secret")

    @patch("client.requests.post")
    def test_raises_when_token_missing_in_response(self, mock_post):
        mock_post.return_value = _mock_response(200, {"other": "value"})
        with self.assertRaises(IntelixAuthError):
            get_token("id", "secret")


# ---------------------------------------------------------------------------
# Validate Region
# ---------------------------------------------------------------------------

class TestValidateRegion(unittest.TestCase):

    def test_raises_on_unknown_region(self):
        with self.assertRaises(ValueError):
            validate_region("mars")

    def test_does_not_raise_on_valid_regions(self):
        for region in ("us-east", "de", "au"):
            validate_region(region) 


# ---------------------------------------------------------------------------
# submit_file
# ---------------------------------------------------------------------------

class TestSubmitFile(unittest.TestCase):

    def _tmp(self, suffix: str) -> str:
        f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        f.write(b"data")
        f.close()
        return f.name

    @patch("client.requests.post")
    def test_returns_response_dict_on_success(self, mock_post):
        body = {"jobId": "job-1", "jobStatus": "IN_PROGRESS"}
        mock_post.return_value = _mock_response(202, body)
        path = self._tmp(".exe")
        try:
            result = submit_file(path, "token", region="de")
            self.assertIsInstance(result, dict)
            self.assertEqual(result["jobId"], "job-1")
        finally:
            os.unlink(path)

    def test_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            submit_file("/no/such/file.exe", "token", region="de")

    @patch("client.time.sleep")
    @patch("client.requests.post")
    def test_raises_on_http_error(self, mock_post, _sleep):
        mock_post.return_value = _mock_response(500, {"error": "server error"})
        path = self._tmp(".pdf")
        try:
            with self.assertRaises(IntelixSubmitError):
                submit_file(path, "token", region="de")
        finally:
            os.unlink(path)

    @patch("client.requests.post")
    def test_accepts_all_success_status_codes(self, mock_post):
        """200 and 202 are valid submission responses per the API docs."""
        body = {"jobId": "job-1", "jobStatus": "IN_PROGRESS"}
        path = self._tmp(".docx")
        try:
            for status in (200, 202):
                mock_post.return_value = _mock_response(status, body)
                result = submit_file(path, "token", region="de")
                self.assertIsInstance(result, dict)
        finally:
            os.unlink(path)

    @patch("client.requests.post")
    def test_raises_with_message_on_400(self, mock_post):
        mock_post.return_value = _mock_response(400, {})
        path = self._tmp(".exe")
        try:
            with self.assertRaises(IntelixSubmitError) as ctx:
                submit_file(path, "token", region="de")
            self.assertIn("Malformed", str(ctx.exception))
        finally:
            os.unlink(path)

    @patch("client.requests.post")
    def test_raises_with_message_on_401(self, mock_post):
        mock_post.return_value = _mock_response(401, {})
        path = self._tmp(".exe")
        try:
            with self.assertRaises(IntelixSubmitError) as ctx:
                submit_file(path, "token", region="de")
            self.assertIn("Unauthorised", str(ctx.exception))
        finally:
            os.unlink(path)

    @patch("client.requests.post")
    def test_raises_with_message_on_404(self, mock_post):
        mock_post.return_value = _mock_response(404, {})
        path = self._tmp(".exe")
        try:
            with self.assertRaises(IntelixSubmitError) as ctx:
                submit_file(path, "token", region="de")
            self.assertIn("Endpoint not found", str(ctx.exception))
        finally:
            os.unlink(path)

    @patch("client.requests.post")
    def test_raises_with_message_on_405(self, mock_post):
        mock_post.return_value = _mock_response(405, {})
        path = self._tmp(".exe")
        try:
            with self.assertRaises(IntelixSubmitError) as ctx:
                submit_file(path, "token", region="de")
            self.assertIn("Method not allowed", str(ctx.exception))
        finally:
            os.unlink(path)

    @patch("client.requests.post")
    def test_raises_with_message_on_415(self, mock_post):
        mock_post.return_value = _mock_response(415, {})
        path = self._tmp(".exe")
        try:
            with self.assertRaises(IntelixSubmitError) as ctx:
                submit_file(path, "token", region="de")
            self.assertIn("Unsupported media type", str(ctx.exception))
        finally:
            os.unlink(path)

    @patch("client.time.sleep")
    @patch("client.requests.post")
    def test_retries_on_429_then_succeeds(self, mock_post, _sleep):
        """429 responses are retried; eventual 202 succeeds."""
        body = {"jobId": "job-1", "jobStatus": "IN_PROGRESS"}
        mock_post.side_effect = [
            _mock_response(429, {}, headers={"X-Rate-Limit-End": "5.0"}),
            _mock_response(429, {}, headers={"X-Rate-Limit-End": "5.0"}),
            _mock_response(202, body),
        ]
        path = self._tmp(".exe")
        try:
            result = submit_file(path, "token", region="de")
            self.assertEqual(mock_post.call_count, 3)
            self.assertEqual(result["jobId"], "job-1")
        finally:
            os.unlink(path)

    @patch("client.time.sleep")
    @patch("client.requests.post")
    def test_retries_on_500_then_succeeds(self, mock_post, _sleep):
        """5xx responses are retried; eventual 202 succeeds."""
        body = {"jobId": "job-1", "jobStatus": "IN_PROGRESS"}
        mock_post.side_effect = [
            _mock_response(500, {}),
            _mock_response(202, body),
        ]
        path = self._tmp(".exe")
        try:
            result = submit_file(path, "token", region="de")
            self.assertEqual(mock_post.call_count, 2)
            self.assertEqual(result["jobId"], "job-1")
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# get_result
# ---------------------------------------------------------------------------

class TestGetResult(unittest.TestCase):

    @patch("client.requests.get")
    def test_returns_dict_on_200(self, mock_get):
        mock_get.return_value = _mock_response(200, {"score": 0})
        result = get_result("job-1", "token", region="de")
        self.assertEqual(result, {"score": 0})

    @patch("client.requests.get")
    def test_returns_none_when_still_in_progress(self, mock_get):
        """HTTP 202 means the analysis is not yet complete."""
        mock_get.return_value = _mock_response(202, {})
        self.assertIsNone(get_result("job-1", "token", region="de"))

    @patch("client.time.sleep")
    @patch("client.requests.get")
    def test_raises_on_unexpected_status(self, mock_get, _sleep):
        mock_get.return_value = _mock_response(503, {"error": "unavailable"})
        with self.assertRaises(IntelixResultError):
            get_result("job-1", "token", region="de")

    @patch("client.requests.get")
    def test_raises_with_message_on_400(self, mock_get):
        mock_get.return_value = _mock_response(400, {})
        with self.assertRaises(IntelixResultError) as ctx:
            get_result("job-1", "token", region="de")
        self.assertIn("Malformed", str(ctx.exception))

    @patch("client.requests.get")
    def test_raises_with_message_on_401(self, mock_get):
        mock_get.return_value = _mock_response(401, {})
        with self.assertRaises(IntelixResultError) as ctx:
            get_result("job-1", "token", region="de")
        self.assertIn("Unauthorised", str(ctx.exception))

    @patch("client.requests.get")
    def test_raises_with_message_on_404(self, mock_get):
        mock_get.return_value = _mock_response(404, {})
        with self.assertRaises(IntelixResultError) as ctx:
            get_result("job-1", "token", region="de")
        self.assertIn("Job ID not found", str(ctx.exception))

    @patch("client.requests.get")
    def test_raises_with_message_on_405(self, mock_get):
        mock_get.return_value = _mock_response(405, {})
        with self.assertRaises(IntelixResultError) as ctx:
            get_result("job-1", "token", region="de")
        self.assertIn("Method not allowed", str(ctx.exception))

    @patch("client.time.sleep")
    @patch("client.requests.get")
    def test_retries_on_429_then_succeeds(self, mock_get, _sleep):
        """429 responses are retried; eventual 200 succeeds."""
        mock_get.side_effect = [
            _mock_response(429, {}, headers={"X-Rate-Limit-End": "5.0"}),
            _mock_response(200, {"score": 0}),
        ]
        result = get_result("job-1", "token", region="de")
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(result["score"], 0)

    @patch("client.time.sleep")
    @patch("client.requests.get")
    def test_retries_on_500_then_succeeds(self, mock_get, _sleep):
        """5xx responses are retried; eventual 200 succeeds."""
        mock_get.side_effect = [
            _mock_response(500, {}),
            _mock_response(200, {"score": 0}),
        ]
        result = get_result("job-1", "token", region="de")
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(result["score"], 0)


# ---------------------------------------------------------------------------
# _guess_mime_type
# ---------------------------------------------------------------------------

class TestGuessMimeType(unittest.TestCase):

    def test_exe(self):
        mime = _guess_mime_type("setup.exe")
        self.assertTrue("msdownload" in mime or "msdos" in mime)

    def test_docx(self):
        self.assertIn("wordprocessingml", _guess_mime_type("report.docx"))

    def test_pdf(self):
        self.assertEqual(_guess_mime_type("doc.pdf"), "application/pdf")

    def test_unknown_falls_back_to_octet_stream(self):
        self.assertEqual(_guess_mime_type("file.xyz_unknown"), "application/octet-stream")


if __name__ == "__main__":
    unittest.main(verbosity=2)
