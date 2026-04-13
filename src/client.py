import base64
import logging
import mimetypes
import os
import time
 
import requests
 
logger = logging.getLogger(__name__)
 
# ---------------------------------------------------------------------------
# API constants
# ---------------------------------------------------------------------------
 
# The OAuth2 token endpoint lives on the shared, non-regional host.
_AUTH_BASE_URL = "https://api.labs.sophos.com"
 
REGION_ENDPOINTS = {
    "us-east": "https://us.api.labs.sophos.com",
    "de":      "https://de.api.labs.sophos.com",
    "au":      "https://au.api.labs.sophos.com",
}
 
_TOKEN_PATH  = "/oauth2/token"
_SUBMIT_PATH = "/analysis/file/static/v1"
_RESULT_PATH = "/analysis/file/static/v1/reports/{job_id}"

 # Polling constants prescribed by the Intelix API documentation.
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS  = 900  # 15 minutes

# Retry strategy (the Intelix documentation recommendation).
# 5xx responses and 429 (rate limit) are retried; 4xx (except 429) are not.
_MAX_RETRY_ATTEMPTS = 5
_LINEAR_BACKOFF_BASE = 60   # seconds — as recommended in the Intelix docs
_MAX_BACKOFF = 300          # seconds — cap for linear backoff
 
# Human-readable messages for documented 4xx codes, keyed by status code.
# 429 and 5xx are handled separately by the retry logic and never reach these.
_SUBMIT_ERRORS = {
    400: "Malformed request - check file type and parameters.",
    401: "Unauthorised - the access token is missing, expired, or not valid for this service.",
    404: "Endpoint not found - check the region and API path.",
    405: "Method not allowed - the endpoint does not support the HTTP method used.",
    415: "Unsupported media type - the request was not assembled correctly.",
}
 
_RESULT_ERRORS = {
    400: "Malformed request - check that the job ID format is valid.",
    401: "Unauthorised - the access token is missing, expired, or not valid for this service.",
    404: "Job ID not found - the ID is invalid or the result has expired.",
    405: "Method not allowed - the endpoint does not support the HTTP method used.",
}
 
# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
 
class IntelixAuthError(Exception):
    """Raised when OAuth2 token acquisition fails."""
 
class IntelixSubmitError(Exception):
    """Raised when file submission fails."""
 
class IntelixResultError(Exception):
    """Raised when fetching an analysis result fails."""

# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_token(client_id: str, client_secret: str) -> str:
    """
    Request an OAuth2 bearer token using client credentials.

    The Intelix auth endpoint uses HTTP Basic Auth:
        Authorization: Basic Base64(<client_id>:<client_secret>)

    Only ``grant_type=client_credentials`` goes in the request body;
    the credentials themselves must NOT appear there.

    Returns:
        The access token string.

    Raises:
        IntelixAuthError: On HTTP error or missing token in response.
    """
       
    url = _AUTH_BASE_URL + _TOKEN_PATH
    logger.info("Requesting access token from %s", url)

    # Build the Basic Auth header: Base64("<client_id>:<client_secret>")
    raw_credentials = f"{client_id}:{client_secret}".encode("utf-8")
    encoded = base64.b64encode(raw_credentials).decode("ascii")

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Basic {encoded}",
                "Content-Type":  "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
    except requests.exceptions.Timeout:
        raise IntelixAuthError("Token request timed out.")
    except requests.exceptions.RequestException as exc:
        raise IntelixAuthError(f"Token request failed: {exc}")
    if response.status_code == 400:
        raise IntelixAuthError(
        "Token request rejected (400) — invalid request or invalid client credentials. "
        "Check grant type, client ID, and client secret."
    )

    if response.status_code != 200:
        raise IntelixAuthError(
            f"Token request failed: HTTP {response.status_code} - {response.text}"
        )

    data = _safe_json(response)
    token = data.get("access_token")
    if not token:
        raise IntelixAuthError("Token response did not contain 'access_token'.")

    logger.info("Access token obtained.")
    return token

def validate_region(region: str) -> None:
    """Raise ValueError if *region* is not a recognised region string."""
    _base_url(region)    


def submit_file(file_path: str, token: str, region: str) -> dict:
    """
    Upload a file for static analysis.
 
    Returns:
        The full API response dict (contains jobId, jobStatus, etc.).
 
    Raises:
        FileNotFoundError:  If *file_path* does not exist.
        IntelixSubmitError: On HTTP error.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
 
    filename  = os.path.basename(file_path)
    mime_type = _guess_mime_type(filename)
    url       = _base_url(region) + _SUBMIT_PATH
 
    logger.info("Submitting '%s' (MIME: %s)", filename, mime_type)
 
    def _make_request():
        # Re-open the file on every attempt so the handle is at position 0
        # even after a failed attempt consumed (part of) the stream.
        with open(file_path, "rb") as fh:
            return requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (filename, fh, mime_type)},
                timeout=60,
            )
 
    try:
        response = _retryable_request(_make_request, label=f"Submit '{filename}'")
    except requests.exceptions.Timeout:
        raise IntelixSubmitError(f"Submission of '{filename}' timed out.")
    except requests.exceptions.RequestException as exc:
        raise IntelixSubmitError(f"Submission of '{filename}' failed: {exc}")
 
    if response.status_code in (200, 202):
        data = _safe_json(response)
        logger.info("Submitted '%s' successfully.", filename)
        logger.debug("Full response: %s", data)
        return data
 
    status = response.status_code
    message = _SUBMIT_ERRORS.get(status, f"Unexpected error — HTTP {status}.")

    raise IntelixSubmitError(f"{message} (file='{filename}')")
 
 
def get_result(job_id: str, token: str, region: str) -> dict | None:
    """
    Fetch the analysis result for *job_id*.
 
    Returns:
        The result dict if the analysis is complete, or ``None`` if it is
        still in progress (HTTP 202).
 
    Raises:
        IntelixResultError: On any unexpected HTTP status code.
    """
    url = (_base_url(region) + _RESULT_PATH).format(job_id=job_id)
 
    def _make_request():
        return requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
 
    try:
        response = _retryable_request(_make_request, label=f"Result fetch for {job_id}")
    except requests.exceptions.Timeout:
        raise IntelixResultError(f"Result fetch timed out for job {job_id}.")
    except requests.exceptions.RequestException as exc:
        raise IntelixResultError(f"Result fetch failed for job {job_id}: {exc}")
 
    if response.status_code == 202:
        logger.debug("Result not ready yet for %s.", job_id)
        return None
    if response.status_code == 200:
        return _safe_json(response)
    
 
    # 429 and 5xx are already handled by _retryable_request before we get here.
    status = response.status_code
    message = _RESULT_ERRORS.get(status, f"Unexpected error — HTTP {status}.")

    raise IntelixResultError(f"{message} (job_id={job_id})")
 
 
# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------
 
def _base_url(region: str) -> str:
    url = REGION_ENDPOINTS.get(region)
    if url is None:
        raise ValueError(
            f"Unknown region '{region}'. Choose from: {list(REGION_ENDPOINTS)}"
        )
    return url
 
 
def _guess_mime_type(filename: str) -> str:
    """Return a best-effort MIME type for *filename*."""
    mime, _ = mimetypes.guess_type(filename)
    if mime:
        return mime
 
    fallbacks = {
        ".exe":  "application/x-msdownload",
        ".doc":  "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pdf":  "application/pdf",
    }
    ext = os.path.splitext(filename)[1].lower()
    return fallbacks.get(ext, "application/octet-stream")
 
 
def _retryable_request(make_request, label: str = "Request"):
    """Execute *make_request()* and retry on 429 or 5xx responses.
 
    Retryable conditions (per the Intelix retry-strategy documentation):
      - 429 Too Many Requests: delay taken from the ``X-Rate-Limit-End``
        response header when present; otherwise falls back to linear backoff.
      - 5xx Server Error: linear backoff.
 
    All other status codes are returned immediately without retrying — 4xx
    errors (except 429) indicate a caller mistake that a retry would not fix.
 
    Args:
        make_request: Zero-argument callable that performs the HTTP request
                      and returns a ``requests.Response``.
        label:        Human-readable name used in log messages.
 
    Returns:
        The last ``requests.Response`` received (whether success or not).
 
    Raises:
        Any exception raised by *make_request* itself (e.g. Timeout,
        ConnectionError) propagates unchanged
    """
    for attempt in range(1, _MAX_RETRY_ATTEMPTS + 1):
        response = make_request()
        status = response.status_code
 
        if status == 429:
            if attempt >= _MAX_RETRY_ATTEMPTS:
                logger.warning(
                    "%s: rate limited (429) — no retries left.", label
                )
                return response
            delay = _rate_limit_delay(response, attempt)
            logger.warning(
                "%s: rate limited (429). Retrying in %.1fs (attempt %d/%d).",
                label, delay, attempt, _MAX_RETRY_ATTEMPTS,
            )
            time.sleep(delay)
            continue
 
        if 500 <= status < 600:
            if attempt >= _MAX_RETRY_ATTEMPTS:
                logger.warning(
                    "%s: server error (%d) — no retries left.", label, status
                )
                return response
            delay = _linear_backoff(attempt)
            logger.warning(
                "%s: server error (%d). Retrying in %.1fs (attempt %d/%d).",
                label, status, delay, attempt, _MAX_RETRY_ATTEMPTS,
            )
            time.sleep(delay)
            continue
 
        
        return response
 
    return response  
 
 
def _linear_backoff(attempt: int) -> float:
    """Return the recommended linear backoff delay for *attempt* (1-based).
 
    Formula from the Intelix documentation:
    seconds = min(b * attempt + r, MAX_BACKOFF)
    where b = 60, MAX_BACKOFF = 300 and 0 <= r <= 1(optional)
    """
    return float(min(_LINEAR_BACKOFF_BASE * attempt, _MAX_BACKOFF))
 
 
def _rate_limit_delay(response, attempt: int) -> float:
    """Return how long to wait after a 429 response.
 
    Prefers the ``X-Rate-Limit-End`` header (seconds until the next allowed
    request, as a fractional number).  Falls back to linear backoff when the
    header is absent or unparseable.
    """
    header_value = response.headers.get("X-Rate-Limit-End")
    if header_value is not None:
        try:
            delay = float(header_value)
            if delay > 0:
                return delay
        except ValueError:
            pass
    return _linear_backoff(attempt)
 
 
def _safe_json(response):
    try:
        return response.json()
    except ValueError:
        logger.error(
            "Invalid JSON response (status %s): %.200s",
            response.status_code, response.text,
        )
        raise RuntimeError("Invalid JSON response from Intelix API")