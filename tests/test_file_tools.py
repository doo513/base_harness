from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.tools.file_tools import grep_files, inspect_file, list_files, read_file_range


class FileToolTests(unittest.TestCase):
    def test_list_files_when_depth_and_ignore_are_set(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")
            (root / "ignored.log").write_text("skip\n", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "b.txt").write_text("beta\n", encoding="utf-8")

            result = list_files(root, max_depth=2, ignore=["*.log"])

        paths = [entry["path"] for entry in result["files"]]
        self.assertFalse(result["truncated"])
        self.assertTrue(any(path.endswith("a.txt") for path in paths))
        self.assertTrue(any(path.endswith("nested/b.txt") for path in paths))
        self.assertFalse(any(path.endswith("ignored.log") for path in paths))

    def test_inspect_file_when_file_is_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blob.bin"
            path.write_bytes(b"\x00\x01\x02")

            result = inspect_file(path)

        self.assertEqual(result["type_hint"], "binary")
        self.assertEqual(result["extension"], ".bin")

    def test_grep_files_when_results_exceed_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "log.txt"
            path.write_text("\n".join(f"needle {i}" for i in range(8)), encoding="utf-8")

            result = grep_files("needle", temp_dir, max_results=3, context_lines=0)

        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["matches"]), 3)
        self.assertEqual(result["matches"][0]["line_number"], 1)

    def test_grep_files_when_default_ignored_dirs_contain_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("needle\n", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("needle\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "pkg.js").write_text("needle\n", encoding="utf-8")

            result = grep_files("needle", root, context_lines=0)

        paths = [match["path"] for match in result["matches"]]
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].endswith("src/main.py"))

    def test_grep_files_when_custom_ignore_matches_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "keep.txt").write_text("needle\n", encoding="utf-8")
            (root / "skip.log").write_text("needle\n", encoding="utf-8")

            result = grep_files("needle", root, context_lines=0, ignore=["*.log"])

        paths = [match["path"] for match in result["matches"]]
        self.assertEqual(len(paths), 1)
        self.assertTrue(paths[0].endswith("keep.txt"))

    def test_read_file_range_when_line_request_exceeds_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "long.txt"
            path.write_text("\n".join(str(i) for i in range(10)), encoding="utf-8")

            result = read_file_range(path, 1, 10, budget={"max_file_read_lines": 4})

        self.assertTrue(result["truncated"])
        self.assertTrue(result["truncated_by_budget"])
        self.assertFalse(result["end_of_file_reached"])
        self.assertEqual(len(result["lines"]), 4)
        self.assertEqual(result["lines"][0]["line_number"], 1)

    def test_read_file_range_when_request_runs_past_end_of_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "short.txt"
            path.write_text("a\nb\n", encoding="utf-8")

            result = read_file_range(path, 1, 5, budget={"max_file_read_lines": 10})

        self.assertTrue(result["truncated"])
        self.assertFalse(result["truncated_by_budget"])
        self.assertTrue(result["end_of_file_reached"])
        self.assertEqual(len(result["lines"]), 2)


if __name__ == "__main__":
    unittest.main()
