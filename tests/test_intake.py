from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.core.intake import intake_request
from harness.core.task_classifier import classify_task


class IntakeTests(unittest.TestCase):
    def test_classify_task_when_request_mentions_csv_and_zip(self) -> None:
        labels = classify_task("Inspect input.csv inside archive.zip")

        self.assertIn("data_inspection", labels)
        self.assertIn("archive_inspection", labels)

    def test_classify_task_when_request_mentions_find(self) -> None:
        labels = classify_task("Find alpha marker and run an experiment")

        self.assertIn("file_analysis", labels)
        self.assertIn("experiment", labels)

    def test_intake_request_when_files_are_provided(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "problem.pdf"
            file_path.write_bytes(b"%PDF-1.4\n")

            result = intake_request(
                "Find the input format",
                workspace_path=temp_dir,
                provided_files=[str(file_path)],
            )

        self.assertEqual(result["objective"], "Find the input format")
        self.assertIn("pdf_analysis", result["likely_tasks"])
        self.assertEqual(result["provided_files"][0]["extension"], ".pdf")
        self.assertIn("inspect_pdf", result["recommended_first_tools"])


if __name__ == "__main__":
    unittest.main()
