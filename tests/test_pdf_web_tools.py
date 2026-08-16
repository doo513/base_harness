from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.tools.pdf_tools import inspect_pdf, read_pdf_pages, search_pdf
from harness.tools.web_tools import fetch_relevant_page, search_web


class PdfWebToolTests(unittest.TestCase):
    def test_pdf_tools_return_structured_unsupported_without_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.pdf"
            path.write_bytes(b"%PDF-1.4\n")

            inspect_result = inspect_pdf(path)
            search_result = search_pdf(path, "query")
            read_result = read_pdf_pages(path, [1, 2, 3, 4], budget={"max_pdf_pages_per_read": 2})

        self.assertIn("supported", inspect_result)
        self.assertIn("supported", search_result)
        self.assertIn("supported", read_result)
        self.assertLessEqual(len(read_result["pages"]), 2)

    def test_web_tools_return_structured_unsupported_by_default(self) -> None:
        search_result = search_web("codex harness")
        fetch_result = fetch_relevant_page("https://example.com", query="example")

        self.assertFalse(search_result["supported"])
        self.assertFalse(fetch_result["supported"])


if __name__ == "__main__":
    unittest.main()
