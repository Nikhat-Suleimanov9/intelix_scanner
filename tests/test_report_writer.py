"""
tests/test_report_writer.py - Unit tests for src/report_writer.py.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from report_writer import save_report


class TestSaveReport(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def test_creates_file_with_correct_name(self):
        result = {"status": "complete", "score": 0}
        path = save_report(result, "samples/sample.exe", self.tmp_dir)
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(path.endswith("sample_exe_report.txt"))

    def test_saved_content_is_valid_json(self):
        result = {"status": "complete", "details": {"verdict": "clean"}}
        path = save_report(result, "file.pdf", self.tmp_dir)
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        self.assertEqual(loaded["status"], "complete")

    def test_creates_output_dir_if_missing(self):
        nested_dir = os.path.join(self.tmp_dir, "nested", "reports")
        result = {"score": 1}
        save_report(result, "doc.docx", nested_dir)
        self.assertTrue(os.path.isdir(nested_dir))

    def test_report_is_pretty_printed(self):
        """The report file must be human-readable (indented), not a single line."""
        result = {"a": 1, "b": 2}
        path = save_report(result, "sample.exe", self.tmp_dir)
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("\n", content)

    def test_returns_absolute_path(self):
        result = {"score": 0}
        path = save_report(result, "sample.exe", self.tmp_dir)
        self.assertTrue(os.path.isabs(path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
