from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.sandbox import LinuxNamespaceSandboxBackend, NetworkPolicy
from harness.core.tools import ActionRuntime, ToolCall, make_shell_tool


@pytest.fixture(scope="module")
def production_backend(tmp_path_factory):
    probe_workspace = tmp_path_factory.mktemp("linuxns-probe")
    backend = LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY)
    att = backend.isolation_attestation(workspace=probe_workspace)
    if att.source != "runtime_probe":
        pytest.skip(f"Linux namespace sandbox unavailable: {att.evidence}")
    assert att.filesystem_isolated is True
    assert att.network_isolated is True
    assert att.environment_sanitized is True
    return backend


def test_production_backend_allows_workspace_write_but_hides_outside(tmp_path, production_backend):
    workspace = tmp_path / "workspace"
    private = tmp_path / "private"
    workspace.mkdir()
    private.mkdir()
    secret = private / "secret.txt"
    secret.write_text("PRIVATE", encoding="utf-8")

    result = production_backend.run_shell(
        workspace=workspace,
        command=f"printf ok > inside.txt; cat inside.txt; cat {secret}",
        timeout_seconds=10,
    )

    assert (workspace / "inside.txt").read_text(encoding="utf-8") == "ok"
    assert "PRIVATE" not in result.stdout
    assert result.returncode != 0


def test_production_backend_is_accepted_by_strict_action_runtime(tmp_path, production_backend):
    tool = make_shell_tool(tmp_path, backend=production_backend)
    runtime = ActionRuntime(
        {"shell": tool},
        strict_isolation=True,
        network_policy=NetworkPolicy.DENY,
    )
    result = runtime.execute(ToolCall("shell", {"command": "printf strict-ok > strict.txt"}))
    assert result.ok is True
    assert (tmp_path / "strict.txt").read_text(encoding="utf-8") == "strict-ok"
    assert result.isolation["source"] == "runtime_probe"


def test_read_only_namespace_backend_blocks_verifier_workspace_mutation(tmp_path, production_backend):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "candidate.txt").write_text("candidate", encoding="utf-8")
    backend = LinuxNamespaceSandboxBackend(
        network_policy=NetworkPolicy.DENY,
        workspace_writable=False,
    )
    result = backend.run_shell(
        workspace=workspace,
        command=(
            "printf scratch > $TMPDIR/scratch.txt; "
            "cat $TMPDIR/scratch.txt; "
            "printf changed > candidate.txt"
        ),
        timeout_seconds=10,
    )
    assert result.returncode != 0
    assert "scratch" in result.stdout
    assert (workspace / "candidate.txt").read_text(encoding="utf-8") == "candidate"


def test_oracle_namespace_exposes_sealed_assets_read_only_and_actor_cannot_see_them(
    tmp_path, production_backend
):
    workspace = tmp_path / "workspace"
    sealed = tmp_path / "sealed"
    workspace.mkdir()
    sealed.mkdir()
    asset = sealed / "acceptance.txt"
    asset.write_text("SEALED", encoding="utf-8")

    actor_read = production_backend.run_shell(
        workspace=workspace,
        command=f"cat {asset}",
        timeout_seconds=10,
    )
    assert actor_read.returncode != 0
    assert "SEALED" not in actor_read.stdout

    oracle = LinuxNamespaceSandboxBackend(
        network_policy=NetworkPolicy.DENY,
        workspace_writable=False,
        read_only_paths=[sealed],
    )
    oracle_read = oracle.run_shell(
        workspace=workspace,
        command=f"cat {asset}",
        timeout_seconds=10,
    )
    assert oracle_read.returncode == 0
    assert oracle_read.stdout.strip() == "SEALED"

    oracle_write = oracle.run_shell(
        workspace=workspace,
        command=f"printf tamper >> {asset}",
        timeout_seconds=10,
    )
    assert oracle_write.returncode != 0
    assert asset.read_text(encoding="utf-8") == "SEALED"


def test_linux_namespace_rejects_workspace_unix_socket(tmp_path):
    import socket

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sock_path = workspace / "host.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(sock_path))
    try:
        backend = LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY)
        result = backend.run_shell(
            workspace=workspace,
            command="echo must-not-run",
            timeout_seconds=5,
        )
        assert result.returncode == 126
        assert "unsafe workspace special file" in result.stderr
    finally:
        listener.close()


def test_linux_namespace_rejects_external_hardlink(tmp_path):
    outside = tmp_path / "outside-secret.txt"
    outside.write_text("HARDLINK_CANARY", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    linked = workspace / "linked-secret.txt"
    linked.hardlink_to(outside)

    backend = LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY)
    result = backend.run_shell(
        workspace=workspace,
        command="cat linked-secret.txt",
        timeout_seconds=5,
    )
    assert result.returncode == 126
    assert "hard links outside the workspace" in result.stderr
    assert "HARDLINK_CANARY" not in result.stdout


def test_software_profile_sealed_oracle_uses_separate_read_only_namespace(tmp_path):
    from harness.profiles.software import SoftwareProfile

    workspace = tmp_path / "workspace"
    sealed = tmp_path / "sealed"
    workspace.mkdir()
    sealed.mkdir()
    (workspace / "candidate.txt").write_text("candidate", encoding="utf-8")
    (sealed / "expected.txt").write_text("expected", encoding="utf-8")

    actor_backend = LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY)
    oracle_backend = LinuxNamespaceSandboxBackend(
        network_policy=NetworkPolicy.DENY,
        workspace_writable=False,
        read_only_paths=[sealed],
    )
    att = actor_backend.isolation_attestation(workspace=workspace)
    if att.source != "runtime_probe":
        pytest.skip(f"Linux namespace sandbox unavailable: {att.evidence}")

    profile = SoftwareProfile(
        workspace=workspace,
        acceptance_commands=[
            'test "$(cat {workspace}/candidate.txt)" = candidate && '
            'test "$(cat {sealed_root}/expected.txt)" = expected && '
            'printf scratch > $TMPDIR/oracle-scratch.txt'
        ],
        execution_backend=actor_backend,
        oracle_backend=oracle_backend,
        sealed_oracle_root=sealed,
        require_oracle_isolation=True,
    )

    result = profile.completion_oracle().evaluate(
        goal=profile.default_goal(),
        state=None,
        workspace=workspace,
    )
    assert result.accepted is True
    assert result.independence_level == "sealed_integrity_and_filesystem_isolation"
    assert (workspace / "candidate.txt").read_text(encoding="utf-8") == "candidate"
    assert (sealed / "expected.txt").read_text(encoding="utf-8") == "expected"
