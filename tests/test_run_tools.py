from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.tools.run_tools import run_command, run_python


class RunToolTests(unittest.TestCase):
    def test_run_command_when_command_is_destructive(self) -> None:
        result = run_command(["rm", "-rf", "/"])

        self.assertFalse(result["executed"])
        self.assertEqual(result["status"], "blocked")

    def test_run_python_when_script_prints_large_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            script = Path(temp_dir) / "script.py"
            script.write_text("print('x' * 100)", encoding="utf-8")

            result = run_python(script, timeout=5, budget={"max_tool_result_chars": 50})

        self.assertTrue(result["executed"])
        self.assertEqual(result["returncode"], 0)
        self.assertTrue(result["stdout_truncated"])

    def test_run_python_when_script_times_out_after_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            script = Path(temp_dir) / "script.py"
            script.write_text(
                "import time\nprint('started', flush=True)\ntime.sleep(10)\n",
                encoding="utf-8",
            )

            result = run_python(script, timeout=2)

        self.assertTrue(result["executed"])
        self.assertEqual(result["status"], "timeout")
        self.assertIn("started", result["stdout"])


if __name__ == "__main__":
    unittest.main()
