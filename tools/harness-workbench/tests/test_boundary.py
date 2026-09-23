"""Unit tests for backend boundary warning and OS/binary classification."""

from __future__ import annotations

import unittest

from workbench import classify_binary_path, evaluate_backend_boundary


class TestBackendBoundary(unittest.TestCase):
    def test_classify_binary_path_windows(self) -> None:
        windows_paths = [
            r"C:\Users\testuser\AppData\Local\Programs\Antigravity\Antigravity.exe",
            "C:/Users/testuser/bin/agy.cmd",
            r"D:\tools\harness.bat",
            "/mnt/c/Users/testuser/AppData/Local/Programs/Antigravity/Antigravity.exe",
            "/mnt/c/tools/agy.exe",
        ]
        for p in windows_paths:
            self.assertEqual(
                classify_binary_path(p),
                "windows",
                f"Expected '{p}' to be classified as windows",
            )

    def test_classify_binary_path_wsl(self) -> None:
        wsl_paths = [
            "/usr/bin/agy",
            "/usr/local/bin/agy",
            "/home/testuser/.local/bin/agy",
            "/home/testuser/.bun/bin/bun",
            "/bin/bash",
        ]
        for p in wsl_paths:
            self.assertEqual(
                classify_binary_path(p),
                "wsl",
                f"Expected '{p}' to be classified as wsl",
            )

    def test_wsl_host_wsl_agy_matched(self) -> None:
        result = evaluate_backend_boundary("wsl", "/home/testuser/.local/bin/agy")
        self.assertTrue(result["is_matched"])
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["rule_id"], "WSL_HARNESS_WSL_AGY")
        self.assertIsNone(result["warning"])

    def test_windows_host_windows_agy_matched(self) -> None:
        result = evaluate_backend_boundary(
            "windows",
            r"C:\Users\testuser\AppData\Local\Programs\Antigravity\Antigravity.exe",
        )
        self.assertTrue(result["is_matched"])
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["rule_id"], "WINDOWS_HARNESS_WINDOWS_AGY")
        self.assertIsNone(result["warning"])

    def test_mismatch_wsl_host_windows_agy(self) -> None:
        # User in WSL points to a Windows binary or /mnt/c/
        result = evaluate_backend_boundary(
            "wsl",
            r"C:\Users\testuser\AppData\Local\Programs\Antigravity\Antigravity.exe",
        )
        self.assertFalse(result["is_matched"])
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["rule_id"], "MISMATCH_WSL_HOST_WINDOWS_AGY")
        self.assertIsNotNone(result["warning"])
        self.assertIn("WSL", result["warning"])

    def test_mismatch_wsl_host_mnt_c_windows_agy(self) -> None:
        result = evaluate_backend_boundary(
            "wsl",
            "/mnt/c/Users/testuser/AppData/Local/Programs/Antigravity/Antigravity.exe",
        )
        self.assertFalse(result["is_matched"])
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["rule_id"], "MISMATCH_WSL_HOST_WINDOWS_AGY")

    def test_mismatch_windows_host_wsl_agy(self) -> None:
        # User in Windows points to /home/... or /usr/...
        result = evaluate_backend_boundary("windows", "/home/testuser/.local/bin/agy")
        self.assertFalse(result["is_matched"])
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["rule_id"], "MISMATCH_WINDOWS_HOST_WSL_AGY")
        self.assertIsNotNone(result["warning"])


if __name__ == "__main__":
    unittest.main()
