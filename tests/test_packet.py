from __future__ import annotations

import unittest

from harness.core.packet import build_context_packet


class PacketTests(unittest.TestCase):
    def test_build_context_packet_when_tool_output_contains_raw_text(self) -> None:
        result = build_context_packet(
            "file_analysis",
            "Find format",
            [
                {
                    "summary": "Read problem statement",
                    "source_refs": [{"source": "problem.md", "location": "lines 1-4"}],
                    "content": "x" * 200,
                }
            ],
            budget={"max_tool_result_chars": 80},
        )

        self.assertEqual(result["task"], "file_analysis")
        self.assertTrue(result["truncated"])
        self.assertEqual(result["source_refs"][0]["source"], "problem.md")
        self.assertLessEqual(len(result["snippets"][0]["text"]), 80)

    def test_build_context_packet_when_multiple_outputs_exceed_packet_limits(self) -> None:
        result = build_context_packet(
            "file_analysis",
            "Find format",
            [
                {
                    "summary": f"output {index}",
                    "source_refs": [{"source": f"{index}.txt", "location": "line 1"}],
                    "stdout": f"raw output {index}",
                    "matches": [{"line": "needle"}],
                }
                for index in range(5)
            ],
            budget={"max_packet_snippets": 2, "max_source_refs": 3, "max_tool_result_chars": 20},
        )

        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["snippets"]), 2)
        self.assertEqual(len(result["source_refs"]), 3)
        self.assertNotIn("tool_outputs", result)
        self.assertNotIn("matches", result["snippets"][0])


if __name__ == "__main__":
    unittest.main()
