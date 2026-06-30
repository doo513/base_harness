from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.core.trace import append_trace, read_trace


class TraceTests(unittest.TestCase):
    def test_append_trace_and_read_trace_when_limit_is_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"
            append_trace(path, {"tool": "list_files", "truncated": False})
            append_trace(path, {"tool": "grep_files", "truncated": True})

            result = read_trace(path, limit=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tool"], "grep_files")

    def test_append_trace_when_record_has_metadata_and_large_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trace.jsonl"
            append_trace(
                path,
                {
                    "tool": "read_file_range",
                    "ok": True,
                    "duration_ms": 7,
                    "warnings": ["budget applied"],
                    "lines": [{"text": "x" * 1000}],
                    "stdout": "x" * 1000,
                },
            )

            result = read_trace(path)

        self.assertEqual(result[0]["ok"], True)
        self.assertEqual(result[0]["duration_ms"], 7)
        self.assertEqual(result[0]["warnings"], ["budget applied"])
        self.assertNotIn("lines", result[0])
        self.assertNotIn("stdout", result[0])


if __name__ == "__main__":
    unittest.main()
