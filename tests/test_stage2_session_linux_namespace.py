from __future__ import annotations

import base64

import pytest

from harness.core.sandbox import LinuxNamespaceSandboxBackend, NetworkPolicy
from harness.core.tools import ActionRuntime, ToolCall, make_session_tool


def test_production_namespace_persistent_session_isolation_and_io(tmp_path):
    workspace = tmp_path / "workspace"
    private = tmp_path / "private"
    workspace.mkdir(); private.mkdir()
    secret = private / "secret.txt"
    secret.write_text("PRIVATE_SESSION_CANARY", encoding="utf-8")

    backend = LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY)
    att = backend.isolation_attestation(workspace=workspace)
    if att.source != "runtime_probe":
        pytest.skip(f"Linux namespace sandbox unavailable: {att.evidence}")

    runtime = ActionRuntime(
        {"session": make_session_tool(workspace, backend=backend)},
        strict_isolation=True,
        network_policy=NetworkPolicy.DENY,
    )
    script = 'while IFS= read -r line; do printf "E:%s\\n" "$line"; done'
    created = runtime.execute(ToolCall("session", {
        "op":"create", "argv":["/bin/sh", "-c", script]
    }))
    assert created.ok is True
    assert created.isolation["source"] == "runtime_probe"
    sid = created.output["session_id"]

    payload = f"ping:{secret}\n".encode()
    sent = runtime.execute(ToolCall("session", {
        "op":"send", "session_id":sid,
        "data_b64":base64.b64encode(payload).decode(),
    }))
    assert sent.ok is True
    observed = runtime.execute(ToolCall("session", {
        "op":"read", "session_id":sid, "wait_seconds":1.0,
    }))
    closed = runtime.execute(ToolCall("session", {"op":"close", "session_id":sid}))
    assert observed.ok is True and closed.ok is True
    out = base64.b64decode(observed.output["stdout_b64"])
    assert b"E:ping:" in out
    assert b"PRIVATE_SESSION_CANARY" not in out


def test_production_namespace_session_cannot_read_outside_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    private = tmp_path / "private"
    workspace.mkdir(); private.mkdir()
    secret = private / "secret.txt"
    secret.write_text("HIDDEN_SESSION_CANARY", encoding="utf-8")

    backend = LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY)
    att = backend.isolation_attestation(workspace=workspace)
    if att.source != "runtime_probe":
        pytest.skip(f"Linux namespace sandbox unavailable: {att.evidence}")

    runtime = ActionRuntime(
        {"session": make_session_tool(workspace, backend=backend)},
        strict_isolation=True,
        network_policy=NetworkPolicy.DENY,
    )
    created = runtime.execute(ToolCall("session", {
        "op":"create", "argv":["/bin/sh", "-c", f"cat {secret}; sleep 0.2"]
    }))
    assert created.ok is True
    sid = created.output["session_id"]
    observed = runtime.execute(ToolCall("session", {
        "op":"read", "session_id":sid, "wait_seconds":1.0,
    }))
    runtime.execute(ToolCall("session", {"op":"close", "session_id":sid}))
    stdout = base64.b64decode(observed.output["stdout_b64"])
    stderr = base64.b64decode(observed.output["stderr_b64"])
    assert b"HIDDEN_SESSION_CANARY" not in stdout
    assert observed.output["returncode"] != 0 or stderr
