import os
from pathlib import Path
import tomllib

from harness.config import load_harness_config
from harness.core.oracles import CommandCompletionOracle
from harness.core.sandbox import ExecutionResult, LocalProcessBackend, RecordingIsolatedTestBackend
from harness.profiles.software import SoftwareProfile
from harness.tui import RunLaunchSpec
from harness.tui_config import (
    default_config_path,
    initial_workspace,
    load_tui_settings,
    persist_tui_settings,
)


def test_initial_workspace_uses_invocation_directory_then_home(tmp_path):
    invocation = tmp_path / "invocation"
    home = tmp_path / "home"
    invocation.mkdir()
    home.mkdir()
    assert initial_workspace(invocation_dir=invocation, home_dir=home) == invocation.resolve()
    invocation.rmdir()
    assert initial_workspace(invocation_dir=invocation, home_dir=home) == home.resolve()


def test_default_config_prefers_local_file_then_user_home(tmp_path, monkeypatch):
    monkeypatch.delenv("HARNESS_CONFIG", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    invocation = tmp_path / "project"
    home = tmp_path / "home"
    invocation.mkdir()
    home.mkdir()
    expected = default_config_path(invocation_dir=invocation, home_dir=home)
    if os.name == "nt":
        assert expected == (home / "AppData" / "Roaming" / "base_harness" / "harness.toml").resolve()
    else:
        assert expected == (home / ".config" / "base_harness" / "harness.toml").resolve()
    local = invocation / "harness.toml"
    local.write_text('profile = "software"\n', encoding="utf-8")
    assert default_config_path(invocation_dir=invocation, home_dir=home) == local.resolve()


def test_tui_settings_persist_into_shared_toml_and_core_config(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config = tmp_path / "config" / "harness.toml"
    persist_tui_settings(
        config,
        workspace=workspace,
        profile="ctf",
        acceptance_commands=("python -m pytest -q",),
        security={
            "execution_backend": "linux-namespace",
            "strict_layout": True,
            "strict_tool_isolation": True,
            "network_policy": "deny",
            "require_sealed_oracle": False,
            "require_oracle_isolation": True,
        },
    )
    raw = tomllib.loads(config.read_text(encoding="utf-8"))
    assert raw["workspace"]["root"] == str(workspace.resolve())
    assert raw["profile"] == "ctf"
    assert raw["security"]["execution_backend"] == "linux-namespace"
    loaded = load_harness_config(config)
    assert loaded.acceptance_commands == ("python -m pytest -q",)
    settings = load_tui_settings(config)
    assert settings.profile == "ctf"
    assert settings.require_oracle_isolation is True


def test_tui_launch_spec_does_not_override_toml_security_when_unspecified(tmp_path):
    command = RunLaunchSpec(
        config=str(tmp_path / "harness.toml"),
        workspace=str(tmp_path),
        run_dir=str(tmp_path / "run"),
    ).command(python_executable="python-test")
    assert "--execution-backend" not in command
    assert "--network-policy" not in command
    assert "--strict-layout" not in command
    assert "--no-strict-layout" not in command
    assert "--require-oracle-isolation" not in command
    assert "--no-require-oracle-isolation" not in command


def test_command_oracle_executes_through_supplied_backend(tmp_path):
    backend = RecordingIsolatedTestBackend({"check": ExecutionResult(0, "passed", "")})
    oracle = CommandCompletionOracle(["check"], backend=backend, allow_test_attestation=True)
    result = oracle.evaluate(goal=None, state=None, workspace=tmp_path)
    assert result.accepted is True
    assert backend.calls[0]["command"] == "check"
    assert result.independence_level == "operator_fixed_unsealed_and_filesystem_isolation"
    assert result.evidence[0]["sandbox"]["backend"] == backend.name


def test_command_oracle_rejects_local_backend_before_execution_when_isolation_required(tmp_path):
    oracle = CommandCompletionOracle(
        ["python -c 'raise SystemExit(99)'"],
        backend=LocalProcessBackend(inherit_env=False),
        require_filesystem_isolation=True,
    )
    result = oracle.evaluate(goal=None, state=None, workspace=tmp_path)
    assert result.accepted is False
    assert "requires filesystem-isolated backend" in result.reason
    assert result.evidence[0]["sandbox"]["filesystem_isolated"] is False


def test_software_profile_binds_unsealed_oracle_to_explicit_backend(tmp_path):
    backend = RecordingIsolatedTestBackend({"check": ExecutionResult(0, "", "")})
    profile = SoftwareProfile(
        workspace=tmp_path,
        acceptance_commands=["check"],
        execution_backend=LocalProcessBackend(inherit_env=False),
        oracle_backend=backend,
        require_oracle_isolation=True,
    )
    result = profile.completion_oracle().evaluate(goal=None, state=None, workspace=tmp_path)
    assert result.accepted is False
    assert backend.calls == []
