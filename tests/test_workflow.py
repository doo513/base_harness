from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.core.trace import read_trace
from harness.core.workflow import run_intake_workflow


class WorkflowTests(unittest.TestCase):
    def test_run_intake_workflow_when_problem_folder_has_statement_and_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            statement = workspace / "problem.md"
            data_file = workspace / "input.jsonl"
            statement.write_text("Find the input format.\nRows are JSON objects.\n", encoding="utf-8")
            data_file.write_text('{"id": 1}\n{"id": 2}\n{"id": 3}\n', encoding="utf-8")

            result = run_intake_workflow(
                "Inspect the problem statement and JSONL input format",
                workspace_path=workspace,
                provided_files=[statement, data_file],
            )
            trace_records = read_trace(result["trace_path"])

        self.assertIn("file_analysis", result["tasks"])
        self.assertIn("data_inspection", result["tasks"])
        self.assertIn("read_file_range", result["selected_tools"])
        self.assertEqual(result["packet"]["objective"], "Inspect the problem statement and JSONL input format")
        self.assertLessEqual(len(result["packet"]["snippets"]), result["budget"]["max_packet_snippets"])
        self.assertGreaterEqual(len(result["packet"]["source_refs"]), 2)
        self.assertGreaterEqual(len(trace_records), 3)
        self.assertTrue(all("ok" in record for record in trace_records))

    def test_run_intake_workflow_when_request_has_search_term(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            note = workspace / "notes.txt"
            note.write_text("alpha marker is here\n", encoding="utf-8")

            result = run_intake_workflow("Find alpha marker in source files", workspace_path=workspace)
            trace_records = read_trace(result["trace_path"])

        tools = [record.get("tool") for record in trace_records]
        self.assertIn("grep_files", tools)
        self.assertIn("Searched workspace text for request terms", result["packet"]["summary"])

    def test_run_intake_workflow_when_request_mentions_experiment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)

            result = run_intake_workflow("Run an experiment for this approach", workspace_path=workspace)
            trace_records = read_trace(result["trace_path"])

        tools = [record.get("tool") for record in trace_records]
        self.assertIn("run_python", result["selected_tools"])
        self.assertNotIn("run_python", tools)
        self.assertNotIn("run_command", tools)


if __name__ == "__main__":
    unittest.main()
