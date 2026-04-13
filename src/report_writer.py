"""
report_writer.py - Saves Intelix JSON analysis results to .txt files.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)


def save_report(result: dict, file_path: str, output_dir: str) -> str:
    """
    Serialise *result* as indented JSON and write it to a .txt file inside *output_dir*.

    The output filename is derived from the original file's stem, e.g.:
        sample.exe  →  sample_exe_report.txt

    Args:
        result:     The analysis result dict from the Intelix API.
        file_path:  Path of the file that was analysed (used only to derive the output name).
        output_dir: Directory where the report should be saved.

    Returns:
        The absolute path to the saved report file.
    """
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.basename(file_path)
    # Replace dots so the stem is safe to use as part of the filename
    safe_stem = base_name.replace(".", "_")
    report_filename = f"{safe_stem}_report.txt"
    report_path = os.path.abspath(os.path.join(output_dir, report_filename))

    logger.info("Saving report for '%s' -> %s", base_name, report_path)

    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False)

    logger.info("Report saved: %s (%d bytes)", report_path, os.path.getsize(report_path))
    return report_path
