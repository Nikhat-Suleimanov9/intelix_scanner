# SophosLabs Intelix Static File Scanner

A clean, minimal Python tool that submits files to the
[SophosLabs Intelix] Static File Analysis API,
waits for the analysis to complete, and saves each JSON report as a `.txt` file.

---

## Project Structure

```
intelix_scanner/
├── src/
│   ├── main.py           # Entry point – CLI parsing, auth, summary, exit code
│   ├── client.py         # HTTP layer – auth, file upload, result fetch
│   ├── pipeline.py       # Scanning pipeline – submit, poll, concurrent orchestration
│   ├── report_writer.py  # Saves JSON reports to .txt files
│   ├── config.py         # Runtime configuration – credentials from env, rest from CLI
│   └── logger.py         # Logging setup – stdout + log file
├── tests/
│   ├── test_client.py        # Unit tests for client.py
│   ├── test_pipeline.py      # Unit tests for pipeline.py
│   └── test_report_writer.py # Unit tests for report_writer.py
├── requirements.txt
└── README.md
```

### Module responsibilities

| Module | Responsibility |
|---|---|
| `client.py` | Talks to the Intelix API — token, upload, fetch result, region validation |
| `pipeline.py` | Drives the full workflow — submit, poll, isolate per-file failures, run concurrently |
| `report_writer.py` | Serialises the result dict and writes it to a `.txt` file |
| `config.py` | Holds all runtime config — credentials from environment, rest from CLI arguments |
| `logger.py` | Configures the root logger once at startup (stdout + file) |
| `main.py` | Thin entry point — CLI args, auth, forwards execution to `pipeline.run_all`, summary |

---

## Prerequisites

- Python 3.10+
- A free SophosLabs Intelix account with API credentials

---

## Setup

```bash
# 1. Clone / download the repository
cd intelix_scanner

# 2. Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv/Scripts/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Export your Intelix credentials (only these come from the environment)
export INTELIX_CLIENT_ID=<your-client-id>
export INTELIX_CLIENT_SECRET=<your-client-secret>
```

---

## Usage

```bash
cd src
python main.py [OPTIONS] FILE [FILE ...]
```

### Options

| Argument | Default | Description |
|---|---|---|
| `--region` | `de` | API region: `us-east`, `de` or `au` |
| `--reports-dir` | `reports` | Output directory for report files |


### Examples

```bash
# Scan multiple files
python main.py ../samples/sample.exe ../samples/sample.docx ../samples/sample.pdf

# Scan multiple files, different region
python main.py --region us-east  ../samples/sample.exe ../samples/sample.docx ../samples/sample.pdf
```

Activity is logged to **stdout** and to `logs/intelix_scanner.log`.
Reports are written to the `reports/` directory (or `--reports-dir`) — one `.txt` file per submitted file.

---

## Running the Tests

```bash
# From the project root
python -m unittest discover -s tests -v
```

All tests mock HTTP calls — no real API credentials are needed to run the test suite.

---

## Output

Each report file is named after the original file:

```
reports/
├── sample_exe_report.txt
├── sample_docx_report.txt
└── sample_pdf_report.txt
```

The content is the Intelix JSON response, pretty-printed for readability.

```
logs/
└── intelix_scanner.log
```

---

## Exit Codes

| Code | Meaning |
|------|-------------------------------------------|
| `0`  | All files analysed successfully           |
| `1`  | Fatal error (bad credentials or config)   |
| `2`  | One or more files failed (partial success)|

---

## Notes

- **Credentials** (`INTELIX_CLIENT_ID`, `INTELIX_CLIENT_SECRET`) are read exclusively from environment variables — never hard-code them in source files.
- All other settings (region, reports directory) are passed as CLI arguments.
- **Region validation** is performed once at startup before any files are submitted or authentication is attempted.
- Files are scanned **concurrently** — `asyncio.gather` runs all files simultaneously, with blocking HTTP calls offloaded via asyncio.to_thread to avoid blocking the event loop.
- One file failing does not stop the others — each file is isolated and failures are logged individually.
- **Retry behaviour** — file submission and result fetching retry automatically on 429 (rate limit) and 5xx (server error), up to 5 attempts. For 429 the delay comes from the `X-Rate-Limit-End` response header; for 5xx linear backoff applies (`min(60 × attempt, 300)` seconds). Token requests are not retried — a failure there indicates a configuration problem.
