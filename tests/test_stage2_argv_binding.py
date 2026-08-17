from __future__ import annotations

import sys

from harness.core.sandbox import ExecutionResult, IsolationAttestation, LocalProcessBackend, NetworkPolicy, RecordingIsolatedTestBackend
from harness.core.tools import ActionRuntime, SandboxedArgvToolSpec, ToolCall, make_argv_tool


def test_local_process_argv_does_not_interpret_shell_metacharacters(tmp_path):
    marker = tmp_path / "SHOULD_NOT_EXIST"
    payload = f"hello;touch {marker}"
    backend = LocalProcessBackend(inherit_env=False)
    result = backend.run_argv(
        workspace=tmp_path,
        argv=[sys.executable, "-c", "import sys; print(sys.argv[1])", payload],
        timeout_seconds=5,
    )
    assert result.returncode == 0
    assert payload in result.stdout
    assert marker.exists() is False


def test_strict_argv_tool_uses_attested_backend_with_exact_argv(tmp_path):
    argv = ["printf", "%s", "x; touch never"]
    backend = RecordingIsolatedTestBackend({tuple(argv): ExecutionResult(0, "x; touch never", "")})
    spec = make_argv_tool(tmp_path, backend=backend)
    runtime = ActionRuntime(
        {"argv": spec},
        strict_isolation=True,
        network_policy=NetworkPolicy.DENY,
        allow_test_attestation=True,
    )
    result = runtime.execute(ToolCall("argv", {"argv": argv}))
    assert result.ok is True
    assert result.output["stdout"] == "x; touch never"
    assert backend.calls == [{
        "workspace": str(tmp_path.resolve()),
        "argv": argv,
        "timeout_seconds": 60.0,
    }]


def test_argv_attestation_and_execution_use_same_backend_object(tmp_path):
    class IdentityBackend:
        name = "identity_argv_backend"
        def __init__(self):
            self.attested_ids = []
            self.executed_ids = []
        def isolation_attestation(self, *, workspace):
            self.attested_ids.append(id(self))
            return IsolationAttestation(True, True, True, "test_fixture")
        def run_argv(self, *, workspace, argv, timeout_seconds, env=None):
            self.executed_ids.append(id(self))
            return ExecutionResult(0, "ok", "")
        def run_shell(self, *, workspace, command, timeout_seconds, env=None):
            raise AssertionError("structured argv path must not call run_shell")

    backend = IdentityBackend()
    spec = SandboxedArgvToolSpec("argv", "argv", backend, tmp_path)
    runtime = ActionRuntime(
        {"argv": spec}, strict_isolation=True,
        network_policy=NetworkPolicy.DENY, allow_test_attestation=True,
    )
    result = runtime.execute(ToolCall("argv", {"argv": ["true"]}))
    assert result.ok is True
    assert backend.attested_ids == [id(backend)]
    assert backend.executed_ids == [id(backend)]


def test_argv_spec_rejects_extra_args_and_nul(tmp_path):
    backend = RecordingIsolatedTestBackend()
    runtime = ActionRuntime({"argv": make_argv_tool(tmp_path, backend=backend)}, allow_test_attestation=True)
    extra = runtime.execute(ToolCall("argv", {"argv": ["true"], "command": "false"}))
    nul = runtime.execute(ToolCall("argv", {"argv": ["bad\x00arg"]}))
    assert extra.ok is False
    assert nul.ok is False
    assert backend.calls == []


def test_argv_execution_semantics_are_provenance_bound(tmp_path):
    spec = SandboxedArgvToolSpec(
        name="argv", description="argv", execution_backend=RecordingIsolatedTestBackend(),
        execution_workspace=tmp_path, timeout_seconds=12.5, argv_arg="argv",
        require_zero_exit=False, provenance={"source":"test"},
    )
    assert spec.provenance["execution_kind"] == "sandboxed_argv"
    assert spec.provenance["timeout_seconds"] == "12.5"
    assert spec.provenance["argv_arg"] == "argv"
    assert spec.provenance["require_zero_exit"] == "false"
