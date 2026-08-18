from pathlib import Path

import pytest

from harness.core.controller import ScriptedController
from harness.core.runtime import HarnessRuntime
from harness.core.workspace import WorkspaceContract, WorkspaceContractError
from harness.profiles.software import SoftwareProfile


def test_workspace_contract_uses_selected_directory_as_root(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    contract = WorkspaceContract.build(
        root,
        temp_dir=".harness-tmp",
        build_dir="build",
        cache_dir=".cache/harness",
    )
    assert contract.root == root.resolve()
    assert contract.temp_dir == (root / ".harness-tmp").resolve()
    assert contract.build_dir == (root / "build").resolve()
    assert contract.cache_dir == (root / ".cache/harness").resolve()
    contract.ensure_managed_dirs()
    assert contract.temp_dir.is_dir()
    assert contract.build_dir.is_dir()
    assert contract.cache_dir.is_dir()


def test_workspace_contract_rejects_missing_root_and_escape(tmp_path):
    with pytest.raises(WorkspaceContractError):
        WorkspaceContract.build(tmp_path / "missing")

    root = tmp_path / "repo"
    root.mkdir()
    contract = WorkspaceContract.build(root)
    with pytest.raises(WorkspaceContractError):
        contract.resolve_actor_path("../outside.txt")
    with pytest.raises(WorkspaceContractError):
        WorkspaceContract.build(root, cache_dir=tmp_path / "outside-cache")


def test_runtime_rejects_profile_tool_workspace_outside_selected_root(tmp_path):
    selected = tmp_path / "selected"
    profile_root = tmp_path / "other"
    selected.mkdir()
    profile_root.mkdir()
    profile = SoftwareProfile(workspace=profile_root, acceptance_commands=["false"])

    with pytest.raises(WorkspaceContractError):
        HarnessRuntime(
            goal=profile.default_goal(),
            profile=profile,
            controller=ScriptedController([]),
            run_dir=tmp_path / "run",
            workspace=selected,
        )


def test_runtime_records_workspace_contract_in_semantic_config(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    contract = WorkspaceContract.build(root, cache_dir=".cache/harness")
    profile = SoftwareProfile(workspace=root, acceptance_commands=["false"])
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=tmp_path / "run",
        workspace_contract=contract,
    )
    descriptor = runtime._config_descriptor()
    assert descriptor["workspace"] == str(root.resolve())
    assert descriptor["workspace_contract"] == contract.descriptor()
