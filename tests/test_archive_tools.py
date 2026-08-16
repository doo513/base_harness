from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from harness.tools.archive_tools import inspect_archive, safe_list_archive


class ArchiveToolTests(unittest.TestCase):
    def test_safe_list_archive_when_zip_contains_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "unsafe.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../escape.txt", "bad")
                archive.writestr("safe.txt", "ok")

            result = safe_list_archive(path)

        self.assertTrue(result["has_path_traversal"])
        self.assertEqual(result["file_count"], 2)

    def test_inspect_archive_when_entry_count_exceeds_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "many.zip"
            with zipfile.ZipFile(path, "w") as archive:
                for index in range(5):
                    archive.writestr(f"{index}.txt", "x")

            result = inspect_archive(path, budget={"max_archive_list_entries": 3})

        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["entries"]), 3)


if __name__ == "__main__":
    unittest.main()
