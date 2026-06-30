from __future__ import annotations

import unittest

from harness.core.context_budget import limit_items, truncate_text


class ContextBudgetTests(unittest.TestCase):
    def test_truncate_text_when_text_exceeds_budget(self) -> None:
        result = truncate_text("abcdefghijklmnopqrstuvwxyz", 12)

        self.assertTrue(result["truncated"])
        self.assertEqual(result["original_count_or_length"], 26)
        self.assertLessEqual(result["returned_count_or_length"], 12)
        self.assertIn("[Truncated:", result["value"])

    def test_limit_items_when_items_exceed_budget(self) -> None:
        result = limit_items(list(range(10)), 5)

        self.assertTrue(result["truncated"])
        self.assertEqual(result["original_count_or_length"], 10)
        self.assertEqual(result["returned_count_or_length"], 5)
        self.assertEqual(result["value"][0], 0)
        self.assertEqual(result["value"][-1], 9)


if __name__ == "__main__":
    unittest.main()
