"""Unit tests for data.py tables and rules."""

from __future__ import annotations

import unittest

from data import (
    ACTOR_LABELS,
    BOUNDARY_MODES,
    DEFAULT_BACKEND,
    DEFAULT_DOMAIN,
    DEFAULT_MODEL,
    DEFAULT_STALE_AFTER,
    DOMAIN_LABELS,
    DOMAINS,
    EVENT_TYPES,
    KNOWN_BACKENDS,
    KNOWN_MODELS,
    PHASE_TO_STAGE,
    ROLE_RULES,
    SAFETY_PRINCIPLES,
    SENSITIVE_KEYS,
    STAGE_BY_ID,
    STAGES,
    TERMINAL_PHASES,
    WORKBENCH_SCHEMA,
)


class TestDataDefinitions(unittest.TestCase):
    def test_workbench_schema(self) -> None:
        self.assertEqual(WORKBENCH_SCHEMA, "harness-workbench-v1")

    def test_stages_and_mapping(self) -> None:
        stage_ids = {s["id"] for s in STAGES}
        self.assertEqual(stage_ids, {"prepare", "explore", "execute", "verify"})
        self.assertEqual(len(STAGES), 4)

        for phase, stage in PHASE_TO_STAGE.items():
            self.assertIn(stage, stage_ids | {"idle"}, f"Phase '{phase}' maps to unknown stage '{stage}'")

    def test_default_model_and_backend(self) -> None:
        self.assertEqual(DEFAULT_MODEL, "gemini-3.8-flash-high")
        self.assertEqual(DEFAULT_BACKEND, "antigravity-cli")
        self.assertIn(DEFAULT_MODEL, KNOWN_MODELS)
        self.assertIn(DEFAULT_BACKEND, KNOWN_BACKENDS)

    def test_domains(self) -> None:
        self.assertIn("develop", DOMAINS)
        self.assertIn("general", DOMAINS)
        self.assertIn("develop", DOMAIN_LABELS)
        self.assertIn("general", DOMAIN_LABELS)

    def test_boundary_modes_table(self) -> None:
        required_keys = {"wsl_native", "windows_native", "mismatch_wsl_host_windows_agy", "mismatch_windows_host_wsl_agy"}
        for k in required_keys:
            self.assertIn(k, BOUNDARY_MODES)
            mode = BOUNDARY_MODES[k]
            self.assertIn("id", mode)
            self.assertIn("status", mode)
            self.assertIn("label", mode)
            self.assertIn("description", mode)

    def test_safety_principles(self) -> None:
        titles = {p["title"] for p in SAFETY_PRINCIPLES}
        self.assertIn("No Kill / No Terminate", titles)
        self.assertIn("No Automatic Retry Loop", titles)
        self.assertIn("Evidence-Only Semantics", titles)
        self.assertIn("Strict Credential Redaction", titles)

    def test_sensitive_keys(self) -> None:
        for expected in ("password", "secret", "token", "api_key", "cookie", "authorization"):
            self.assertIn(expected, SENSITIVE_KEYS)


if __name__ == "__main__":
    unittest.main()
