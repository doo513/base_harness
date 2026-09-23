"""Unit tests for DataRedactor and proxy sanitization."""

from __future__ import annotations

import unittest

from workbench import DataRedactor, sanitize_proxy_url


class TestDataRedaction(unittest.TestCase):
    def test_redact_bearer_token(self) -> None:
        raw = "Authorization: Bearer ya29.a0AfH6SMDxyz_123456"
        redacted = DataRedactor.redact(raw)
        self.assertNotIn("ya29.a0AfH6SMDxyz_123456", redacted)
        self.assertIn("Bearer ***REDACTED***", redacted)

    def test_redact_api_keys(self) -> None:
        raw_sk = "export OPENAI_API_KEY=sk-abcdef1234567890"
        redacted_sk = DataRedactor.redact(raw_sk)
        self.assertNotIn("sk-abcdef1234567890", redacted_sk)
        self.assertIn("***REDACTED_KEY***", redacted_sk)

        raw_aiza = "key is AIzaSyD987654321abcdefghijk"
        redacted_aiza = DataRedactor.redact(raw_aiza)
        self.assertNotIn("AIzaSyD987654321abcdefghijk", redacted_aiza)
        self.assertIn("***REDACTED_KEY***", redacted_aiza)

    def test_redact_cli_flags(self) -> None:
        cmd = "run --password=SuperSecret123 --token my-auth-token --api-key=secret-key"
        redacted = DataRedactor.redact(cmd)
        self.assertNotIn("SuperSecret123", redacted)
        self.assertNotIn("my-auth-token", redacted)
        self.assertNotIn("secret-key", redacted)

    def test_redact_object(self) -> None:
        data = {
            "name": "harness_run",
            "token": "secret-session-token",
            "api_key": "secret-api-key",
            "nested": {
                "password": "mypassword",
                "normal_field": "public_data",
                "details": ["Bearer token123", "harmless string"],
            },
        }
        redacted = DataRedactor.redact_object(data)
        self.assertEqual(redacted["token"], "***REDACTED***")
        self.assertEqual(redacted["api_key"], "***REDACTED***")
        self.assertEqual(redacted["nested"]["password"], "***REDACTED***")
        self.assertEqual(redacted["nested"]["normal_field"], "public_data")
        self.assertNotIn("token123", redacted["nested"]["details"][0])
        self.assertEqual(redacted["nested"]["details"][1], "harmless string")

    def test_sanitize_proxy_url_with_password(self) -> None:
        proxy_with_auth = "http://myuser:secretPass123@proxy.internal.corp:8080"
        sanitized = sanitize_proxy_url(proxy_with_auth)
        self.assertNotIn("secretPass123", sanitized)
        self.assertIn("myuser:***REDACTED***@proxy.internal.corp:8080", sanitized)

    def test_sanitize_proxy_url_without_password(self) -> None:
        clean_proxy = "http://127.0.0.1:8080"
        self.assertEqual(sanitize_proxy_url(clean_proxy), "http://127.0.0.1:8080")


if __name__ == "__main__":
    unittest.main()
