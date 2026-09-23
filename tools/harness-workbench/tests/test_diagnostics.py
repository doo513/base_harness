"""Unit tests for environment diagnostics, clock, and TLS reachability."""

from __future__ import annotations

import socket
import ssl
import unittest
from unittest.mock import MagicMock, patch

from workbench import (
    check_tls_reachability,
    detect_os_identity,
    diagnose_environment,
)


class TestDiagnostics(unittest.TestCase):
    def test_detect_os_identity(self) -> None:
        ident = detect_os_identity()
        self.assertIn("os_type", ident)
        self.assertIn("os_name", ident)
        self.assertIn("is_windows", ident)
        self.assertIn("is_wsl", ident)
        self.assertIn("architecture", ident)
        self.assertIn(ident["os_type"], {"wsl", "windows", "linux", "darwin", "unknown"})

    @patch("workbench.socket.create_connection")
    @patch("workbench.ssl.create_default_context")
    def test_check_tls_reachability_success(
        self, mock_ssl_context: MagicMock, mock_create_conn: MagicMock
    ) -> None:
        mock_sock = MagicMock()
        mock_create_conn.return_value = mock_sock

        mock_ssock = MagicMock()
        mock_ssock.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)
        mock_ctx = MagicMock()
        mock_ctx.wrap_socket.return_value = mock_ssock
        mock_ssl_context.return_value = mock_ctx

        res = check_tls_reachability(host="oauth2.googleapis.com", port=443)
        self.assertTrue(res["reachable"])
        self.assertEqual(res["status"], "connected")
        self.assertEqual(res["host"], "oauth2.googleapis.com")
        self.assertEqual(res["port"], 443)
        self.assertIn("TLS_AES_256_GCM_SHA384", res["cipher"])
        self.assertIsNone(res["error"])
        mock_ssock.close.assert_called_once()

    @patch("workbench.socket.create_connection")
    def test_check_tls_reachability_network_failure(self, mock_create_conn: MagicMock) -> None:
        mock_create_conn.side_effect = socket.gaierror(-3, "Temporary failure in name resolution")
        res = check_tls_reachability(host="oauth2.googleapis.com", port=443)
        self.assertFalse(res["reachable"])
        self.assertEqual(res["status"], "unreachable")
        self.assertIn("gaierror", res["error"])

    def test_diagnose_environment_structure(self) -> None:
        diag = diagnose_environment(skip_tls=True)
        self.assertEqual(diag["schemaVersion"], "harness-workbench-v1")
        self.assertIn("diagnosedAt", diag)
        self.assertIn("os", diag)
        self.assertIn("python", diag)
        self.assertIn("bun", diag)
        self.assertIn("agy", diag)
        self.assertIn("harness", diag)
        self.assertIn("boundary", diag)
        self.assertIn("proxies", diag)
        self.assertIn("clock", diag)
        self.assertIn("tlsReachability", diag)
        self.assertEqual(diag["tlsReachability"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
