from __future__ import annotations

import unittest

from harness.core.benchmark import BenchmarkRecord, compare_modes, summarize_benchmarks


class BenchmarkMetaTests(unittest.TestCase):
    def test_compare_baseline_and_harness(self) -> None:
        records = [
            BenchmarkRecord(task_id="t1", mode="baseline", success=False, elapsed_ms=1000),
            BenchmarkRecord(task_id="t1", mode="harness", success=True, elapsed_ms=800, final_result_valid=True),
        ]
        summary = summarize_benchmarks(records)
        self.assertEqual(summary["baseline"]["runs"], 1)
        comparison = compare_modes(records)
        self.assertTrue(comparison["comparable"])
        self.assertEqual(comparison["success_rate_delta"], 1.0)
        self.assertEqual(comparison["elapsed_ms_delta"], -200.0)


if __name__ == "__main__":
    unittest.main()
