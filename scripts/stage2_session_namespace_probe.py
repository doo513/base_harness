from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

from harness.core.sandbox import LinuxNamespaceSandboxBackend, NetworkPolicy
from harness.core.tools import ActionRuntime, ToolCall, make_session_tool


def _decode(output: dict, field: str) -> bytes:
    return base64.b64decode(output[field])


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-session-probe-") as td:
        root = Path(td)
        workspace = root / "workspace"
        private = root / "private"
        workspace.mkdir()
        private.mkdir()
        secret = private / "secret.txt"
        secret.write_text("PRIVATE_SESSION_CANARY", encoding="utf-8")

        backend = LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY)
        att = backend.isolation_attestation(workspace=workspace)
        if att.source != "runtime_probe":
            raise RuntimeError(f"live namespace attestation unavailable: {att.evidence}")

        runtime = ActionRuntime(
            {"session": make_session_tool(workspace, backend=backend)},
            strict_isolation=True,
            network_policy=NetworkPolicy.DENY,
        )

        # Regression shape: startup output becomes readable before the response.
        # Old read semantics returned after the first readable byte and could
        # therefore return only "ready". The bounded observation window must
        # accumulate the delayed response in the same read call.
        delayed_echo_script = (
            'printf "ready\\n"; '
            'while IFS= read -r line; do sleep 0.15; printf "E:%s\\n" "$line"; done'
        )
        created = runtime.execute(ToolCall("session", {
            "op": "create",
            "argv": ["/bin/sh", "-c", delayed_echo_script],
        }))
        assert created.ok, created.error
        assert created.isolation and created.isolation["source"] == "runtime_probe"
        sid = created.output["session_id"]
        sent = runtime.execute(ToolCall("session", {
            "op": "send",
            "session_id": sid,
            "data_b64": base64.b64encode(b"ping\n").decode("ascii"),
        }))
        assert sent.ok, sent.error
        observed = runtime.execute(ToolCall("session", {
            "op": "read",
            "session_id": sid,
            "wait_seconds": 0.5,
        }))
        assert observed.ok, observed.error
        echoed = _decode(observed.output, "stdout_b64")
        assert b"ready" in echoed, echoed
        assert b"E:ping" in echoed, echoed
        closed = runtime.execute(ToolCall("session", {"op": "close", "session_id": sid}))
        assert closed.ok, closed.error

        escape = runtime.execute(ToolCall("session", {
            "op": "create",
            "argv": ["/bin/sh", "-c", f"cat {secret}; sleep 0.1"],
        }))
        assert escape.ok, escape.error
        sid2 = escape.output["session_id"]
        escaped = runtime.execute(ToolCall("session", {
            "op": "read",
            "session_id": sid2,
            "wait_seconds": 1.0,
        }))
        assert escaped.ok, escaped.error
        runtime.execute(ToolCall("session", {"op": "close", "session_id": sid2}))
        escape_stdout = _decode(escaped.output, "stdout_b64")
        escape_stderr = _decode(escaped.output, "stderr_b64")
        assert b"PRIVATE_SESSION_CANARY" not in escape_stdout
        assert escaped.output["returncode"] != 0 or escape_stderr

        print(json.dumps({
            "probe": "stage2-persistent-session-live-namespace",
            "summary": {
                "all_passed": True,
                "attestation_source": att.source,
                "interactive_io": True,
                "bounded_wait_accumulates_delayed_response": True,
                "outside_workspace_read_blocked": True,
                "network_policy": NetworkPolicy.DENY.value,
            },
            "evidence": att.evidence,
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
