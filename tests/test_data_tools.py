from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness.tools.data_tools import inspect_csv, inspect_json, sample_rows


class DataToolTests(unittest.TestCase):
    def test_inspect_csv_when_rows_exceed_sample_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "items.csv"
            path.write_text("id,name\n1,A\n2,B\n3,C\n", encoding="utf-8")

            result = inspect_csv(path, budget={"max_csv_sample_rows": 2})

        self.assertTrue(result["truncated"])
        self.assertEqual(result["columns"], ["id", "name"])
        self.assertEqual(len(result["sample_rows"]), 2)

    def test_sample_rows_when_n_exceeds_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "items.csv"
            path.write_text("id\n1\n2\n3\n", encoding="utf-8")

            result = sample_rows(path, n=10, budget={"max_csv_sample_rows": 2})

        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["rows"]), 2)

    def test_inspect_json_when_top_level_is_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data.json"
            path.write_text(json.dumps({"items": [1, 2], "name": "x"}), encoding="utf-8")

            result = inspect_json(path)

        self.assertEqual(result["top_level_type"], "object")
        self.assertEqual(result["keys"], ["items", "name"])
        self.assertFalse(result["partial"])

    def test_inspect_json_when_file_exceeds_full_load_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "large.json"
            path.write_text(json.dumps({"items": list(range(200)), "name": "x"}), encoding="utf-8")

            result = inspect_json(path, budget={"max_tool_result_chars": 40, "max_csv_sample_rows": 3})

        self.assertEqual(result["top_level_type"], "object")
        self.assertTrue(result["partial"])
        self.assertTrue(result["truncated"])
        self.assertIn("items", result["keys"])

    def test_inspect_json_when_file_is_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "events.jsonl"
            path.write_text('{"id": 1}\n{"id": 2, "ok": true}\n{"id": 3}\n', encoding="utf-8")

            result = inspect_json(path, budget={"max_csv_sample_rows": 2})

        self.assertEqual(result["top_level_type"], "jsonl")
        self.assertTrue(result["partial"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["line_count_sample"], 2)
        self.assertEqual(result["element_types"], ["object"])


if __name__ == "__main__":
    unittest.main()
