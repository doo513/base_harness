from __future__ import annotations

from pathlib import Path

from harness.core.sandbox import ExecutionResult, IsolationAttestation, NetworkPolicy, RecordingIsolatedTestBackend
from harness.core.security import Principal
from harness.core.tools import (
    ActionRuntime,
    SandboxedCommandToolSpec,
    SideEffect,
    ToolCall,
    ToolSpec,
    make_shell_tool,
)


def test_strict_generic_write_tool_cannot_borrow_backend_attestation(tmp_path):
    workspace = tmp_path / "workspace"
    private = tmp_path / "private"
    workspace.mkdir(); private.mkdir()
    canary = private / "canary.txt"
    canary.write_text("ORIGINAL", encoding="utf-8")
    backend = RecordingIsolatedTestBackend()
    called = {"n": 0}

    def unsafe_handler():
        called["n"] += 1
        canary.write_text("ESCAPED", encoding="utf-8")
        return "done"

    spec = ToolSpec(
        name="unsafe",
        description="unsafe",
        handler=unsafe_handler,
        side_effect=SideEffect.WRITE,
        execution_backend=backend,
        execution_workspace=workspace,
    )
    runtime = ActionRuntime(
        {"unsafe": spec},
        principal=Principal.ACTOR,
        strict_isolation=True,
        network_policy=NetworkPolicy.DENY,
        allow_test_attestation=True,
    )
    result = runtime.execute(ToolCall("unsafe", {}))

    assert result.ok is False
    assert result.security_violation is True
    assert "SandboxedCommandToolSpec" in result.error
    assert called["n"] == 0
    assert backend.calls == []
    assert canary.read_text(encoding="utf-8") == "ORIGINAL"


def test_strict_sandboxed_command_uses_attested_backend(tmp_path):
    backend = RecordingIsolatedTestBackend({
        "printf hi": ExecutionResult(0, "hi", "")
    })
    spec = make_shell_tool(tmp_path, backend=backend)
    runtime = ActionRuntime(
        {"shell": spec},
        strict_isolation=True,
        network_policy=NetworkPolicy.DENY,
        allow_test_attestation=True,
    )

    result = runtime.execute(ToolCall("shell", {"command": "printf hi"}))
    assert result.ok is True
    assert result.output["stdout"] == "hi"
    assert len(backend.calls) == 1


def test_attestation_and_execution_use_same_backend_object(tmp_path):
    class IdentityBackend:
        name = "identity_backend"
        def __init__(self):
            self.attested_ids = []
            self.executed_ids = []
        def isolation_attestation(self, *, workspace):
            self.attested_ids.append(id(self))
            return IsolationAttestation(
                filesystem_isolated=True,
                network_isolated=True,
                environment_sanitized=True,
                source="test_fixture",
            )
        def run_shell(self, *, workspace, command, timeout_seconds, env=None):
            self.executed_ids.append(id(self))
            return ExecutionResult(0, "ok", "")

    backend = IdentityBackend()
    spec = SandboxedCommandToolSpec(
        name="cmd",
        description="cmd",
        execution_backend=backend,
        execution_workspace=tmp_path,
    )
    runtime = ActionRuntime(
        {"cmd": spec},
        strict_isolation=True,
        network_policy=NetworkPolicy.DENY,
        allow_test_attestation=True,
    )
    result = runtime.execute(ToolCall("cmd", {"command": "true"}))

    assert result.ok is True
    assert backend.attested_ids == [id(backend)]
    assert backend.executed_ids == [id(backend)]


def test_sandboxed_command_nonzero_preserves_failure_semantics(tmp_path):
    backend = RecordingIsolatedTestBackend({
        "false": ExecutionResult(7, "", "bad", False)
    })
    spec = make_shell_tool(tmp_path, backend=backend)
    runtime = ActionRuntime({"shell": spec}, allow_test_attestation=True)
    result = runtime.execute(ToolCall("shell", {"command": "false"}))
    assert result.ok is False
    assert result.output["returncode"] == 7
    assert result.error == "postcondition failed"


def test_nonstrict_legacy_inprocess_tool_remains_compatible():
    spec = ToolSpec(
        name="pure",
        description="pure",
        handler=lambda value: value + 1,
        side_effect=SideEffect.NONE,
    )
    result = ActionRuntime({"pure": spec}).execute(ToolCall("pure", {"value": 4}))
    assert result.ok is True
    assert result.output == 5


def test_sandboxed_execution_semantics_are_provenance_bound(tmp_path):
    backend = RecordingIsolatedTestBackend()
    spec = SandboxedCommandToolSpec(
        name="cmd",
        description="cmd",
        execution_backend=backend,
        execution_workspace=Path(tmp_path),
        timeout_seconds=12.5,
        command_arg="command",
        require_zero_exit=False,
        provenance={"source": "test"},
    )
    assert spec.provenance["execution_kind"] == "sandboxed_command"
    assert spec.provenance["timeout_seconds"] == "12.5"
    assert spec.provenance["command_arg"] == "command"
    assert spec.provenance["require_zero_exit"] == "false"
