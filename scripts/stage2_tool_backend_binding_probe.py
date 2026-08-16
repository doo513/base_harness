from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.sandbox import RecordingIsolatedTestBackend, NetworkPolicy
from harness.core.security import Principal
from harness.core.tools import ActionRuntime, SideEffect, ToolCall, ToolSpec


def run_probe() -> dict:
    with tempfile.TemporaryDirectory(prefix="vsh-tool-binding-") as td:
        base = Path(td)
        workspace = base / "workspace"
        private = base / "private"
        workspace.mkdir()
        private.mkdir()
        canary = private / "canary.txt"
        canary.write_text("ORIGINAL", encoding="utf-8")

        backend = RecordingIsolatedTestBackend()
        handler_calls = {"n": 0}

        def unsafe_handler(value: str) -> dict:
            handler_calls["n"] += 1
            canary.write_text(value, encoding="utf-8")
            return {"written": value}

        spec = ToolSpec(
            name="unsafe_write",
            description="attested backend metadata paired with host-side handler",
            handler=unsafe_handler,
            side_effect=SideEffect.WRITE,
            idempotent=False,
            execution_backend=backend,
            execution_workspace=workspace,
            provenance={"probe": "backend-binding"},
        )
        runtime = ActionRuntime(
            {"unsafe_write": spec},
            principal=Principal.ACTOR,
            strict_isolation=True,
            network_policy=NetworkPolicy.DENY,
            allow_test_attestation=True,
        )
        result = runtime.execute(ToolCall("unsafe_write", {"value": "ESCAPED"}))

        canary_changed = canary.read_text(encoding="utf-8") == "ESCAPED"
        mismatch_executed = handler_calls["n"] > 0 and len(backend.calls) == 0
        blocked = result.ok is False and result.security_violation and not canary_changed

        report = {
            "stage": "02-remediation",
            "probe": "tool-backend-attestation-execution-binding",
            "result": {
                "ok": result.ok,
                "security_violation": result.security_violation,
                "error": result.error,
            },
            "effects": {
                "unsafe_handler_calls": handler_calls["n"],
                "attested_backend_execution_calls": len(backend.calls),
                "private_canary_changed": canary_changed,
                "attestation_execution_mismatch_observed": mismatch_executed,
            },
            "summary": {
                "unsafe_path_blocked": blocked,
                "all_passed": blocked,
            },
        }
        return report


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
