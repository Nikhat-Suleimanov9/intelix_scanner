"""
logger.py - Centralised logging configuration for the Intelix Scanner.

Sets up a single root logger that writes to:
  - Standard output  (always, level INFO and above)
  - A log file       (always, level DEBUG and above – full detail)

Usage (call once at program startup, before any other module logs):

    from logger import setup_logging
    setup_logging()          # log file → logs/intelix_scanner.log
    setup_logging(log_dir="custom/path", debug_console=True)

All other modules simply do:

    import logging
    logger = logging.getLogger(__name__)

and they will automatically use the handlers configured here.
"""

import logging
import os
import sys


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_LOG_DIR = "logs"
_LOG_FILENAME = "intelix_scanner.log"

_CONSOLE_FORMAT = "%(asctime)s %(levelname)-8s %(message)s"
_FILE_FORMAT = "%(asctime)s  %(levelname)-8s  [%(name)s:%(lineno)d]  %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_logging(
    log_dir: str = _DEFAULT_LOG_DIR,
    debug_console: bool = False,
) -> str:
    """
    Configure the root logger with a stdout handler and a file handler.

    Should be called **once** at application startup, before any logging occurs.

    Args:
        log_dir:       Directory where the log file will be written.
                       Created automatically if it does not exist.
        debug_console: If True, the console handler emits DEBUG messages too.
                       Defaults to False (INFO and above on console).

    Returns:
        The absolute path to the log file.
    """
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, _LOG_FILENAME)

    root_logger = logging.getLogger()
    
    root_logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers if setup_logging is accidentally called twice
    if root_logger.handlers:
        return os.path.abspath(log_path)

    # ---- Console handler (stdout) ----
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if debug_console else logging.INFO)
    console_handler.setFormatter(_build_formatter(_CONSOLE_FORMAT))

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_build_formatter(_FILE_FORMAT))

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Silence overly chatty third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    root_logger.info("Logging initialised. Log file: %s", os.path.abspath(log_path))

    return os.path.abspath(log_path)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_formatter(fmt: str) -> logging.Formatter:
    return logging.Formatter(fmt=fmt, datefmt=_DATE_FORMAT)
