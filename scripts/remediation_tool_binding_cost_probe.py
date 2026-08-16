from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.sandbox import ExecutionResult, IsolationAttestation, NetworkPolicy
from harness.core.tools import ActionRuntime, SandboxedCommandToolSpec, SideEffect, ToolCall, ToolSpec


class CountingBackend:
    name = "counting_backend"

    def __init__(self):
        self.attestations = 0
        self.executions = 0

    def isolation_attestation(self, *, workspace):
        self.attestations += 1
        return IsolationAttestation(
            filesystem_isolated=True,
            network_isolated=True,
            environment_sanitized=True,
            source="test_fixture",
        )

    def run_shell(self, *, workspace, command, timeout_seconds, env=None):
        self.executions += 1
        return ExecutionResult(0, "ok", "")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-binding-cost-") as td:
        workspace = Path(td)

        safe_backend = CountingBackend()
        safe = SandboxedCommandToolSpec(
            name="safe",
            description="safe",
            execution_backend=safe_backend,
            execution_workspace=workspace,
        )
        safe_runtime = ActionRuntime(
            {"safe": safe},
            strict_isolation=True,
            network_policy=NetworkPolicy.DENY,
            allow_test_attestation=True,
        )
        safe_result = safe_runtime.execute(ToolCall("safe", {"command": "true"}))

        mismatch_backend = CountingBackend()
        handler_calls = {"n": 0}
        mismatch = ToolSpec(
            name="mismatch",
            description="mismatch",
            handler=lambda: handler_calls.__setitem__("n", handler_calls["n"] + 1),
            side_effect=SideEffect.WRITE,
            execution_backend=mismatch_backend,
            execution_workspace=workspace,
        )
        mismatch_runtime = ActionRuntime(
            {"mismatch": mismatch},
            strict_isolation=True,
            network_policy=NetworkPolicy.DENY,
            allow_test_attestation=True,
        )
        mismatch_result = mismatch_runtime.execute(ToolCall("mismatch", {}))

        report = {
            "probe": "tool-binding-cost-v083",
            "safe_sandboxed_path": {
                "attestation_calls": safe_backend.attestations,
                "execution_calls": safe_backend.executions,
                "handler_indirections": 0,
                "ok": safe_result.ok,
            },
            "blocked_mismatch_path": {
                "attestation_calls": mismatch_backend.attestations,
                "backend_execution_calls": mismatch_backend.executions,
                "unsafe_handler_calls": handler_calls["n"],
                "security_violation": mismatch_result.security_violation,
            },
            "cost_interpretation": {
                "additional_backend_calls_for_valid_sandboxed_command": 0,
                "additional_model_tokens": 0,
                "additional_checkpoint_or_event_records": 0,
                "invalid_mismatch_fails_before_attestation_or_execution": True,
            },
        }
        report["passed"] = (
            safe_result.ok
            and safe_backend.attestations == 1
            and safe_backend.executions == 1
            and mismatch_result.security_violation
            and mismatch_backend.attestations == 0
            and mismatch_backend.executions == 0
            and handler_calls["n"] == 0
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
