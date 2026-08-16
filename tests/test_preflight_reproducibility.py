from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.budget import Budget
from harness.core.controller import Decision, ScriptedController
from harness.core.contracts import GoalContract
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.core.sandbox import LocalProcessBackend
from harness.core.security import Capability, CapabilityPolicy, Principal
from harness.core.storage import ResumeConflict
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile
from harness.profiles.software import SoftwareProfile


def _software_runtime(
    tmp_path: Path,
    *,
    run_name: str,
    acceptance_commands: list[str],
    controller: ScriptedController,
    capability_policy: CapabilityPolicy | None = None,
    execution_backend=None,
    resume: bool = False,
):
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    profile = SoftwareProfile(
        workspace=workspace,
        acceptance_commands=acceptance_commands,
        execution_backend=execution_backend,
    )
    kwargs = dict(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / run_name,
        workspace=workspace,
        budget=Budget(hard_max_steps=5),
        task_revision="preflight-v1",
        capability_policy=capability_policy,
    )
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)


def test_resume_rejects_scripted_controller_decision_drift(tmp_path):
    first = _software_runtime(
        tmp_path,
        run_name="controller",
        acceptance_commands=["true"],
        controller=ScriptedController([Decision("complete", {"reason": "first"})]),
    )
    assert first.run().completed

    with pytest.raises(ResumeConflict, match="configuration"):
        _software_runtime(
            tmp_path,
            run_name="controller",
            acceptance_commands=["true"],
            controller=ScriptedController([Decision("complete", {"reason": "different"})]),
            resume=True,
        )


def test_resume_rejects_capability_policy_drift(tmp_path):
    first = _software_runtime(
        tmp_path,
        run_name="capability",
        acceptance_commands=["true"],
        controller=ScriptedController([Decision("complete", {"reason": "done"})]),
    )
    assert first.run().completed

    restricted = CapabilityPolicy(
        grants={
            Principal.ACTOR: frozenset({Capability.TOOL_READ}),
            Principal.VERIFIER: frozenset({Capability.VERIFY}),
            Principal.ORACLE: frozenset({Capability.ORACLE_EXECUTE}),
            Principal.KERNEL: frozenset({Capability.STATE_COMMIT, Capability.LEDGER_WRITE}),
        }
    )
    with pytest.raises(ResumeConflict, match="configuration"):
        _software_runtime(
            tmp_path,
            run_name="capability",
            acceptance_commands=["true"],
            controller=ScriptedController([Decision("complete", {"reason": "done"})]),
            capability_policy=restricted,
            resume=True,
        )


def test_resume_rejects_completion_oracle_command_drift(tmp_path):
    first = _software_runtime(
        tmp_path,
        run_name="oracle",
        acceptance_commands=["true"],
        controller=ScriptedController([Decision("complete", {"reason": "done"})]),
    )
    assert first.run().completed

    with pytest.raises(ResumeConflict, match="configuration"):
        _software_runtime(
            tmp_path,
            run_name="oracle",
            acceptance_commands=["printf changed"],
            controller=ScriptedController([Decision("complete", {"reason": "done"})]),
            resume=True,
        )


def test_resume_rejects_execution_backend_config_drift(tmp_path):
    first = _software_runtime(
        tmp_path,
        run_name="backend",
        acceptance_commands=["true"],
        controller=ScriptedController([Decision("complete", {"reason": "done"})]),
        execution_backend=LocalProcessBackend(inherit_env=False),
    )
    assert first.run().completed

    with pytest.raises(ResumeConflict, match="configuration"):
        _software_runtime(
            tmp_path,
            run_name="backend",
            acceptance_commands=["true"],
            controller=ScriptedController([Decision("complete", {"reason": "done"})]),
            execution_backend=LocalProcessBackend(inherit_env=True),
            resume=True,
        )


class PredicateProfile(DomainProfile):
    name = "predicate-preflight"

    def __init__(self, marker: str):
        self.marker = marker

    def default_goal(self):
        return GoalContract(goal="predicate provenance", acceptance=["predicate"])

    def completion_oracle(self):
        marker = self.marker

        def check(**_):
            return CompletionResult(marker == "A", f"marker={marker}")

        return PredicateCompletionOracle(check, name="predicate-preflight-oracle")


def test_resume_rejects_predicate_closure_drift(tmp_path):
    workspace = tmp_path / "predicate-workspace"
    workspace.mkdir()
    profile = PredicateProfile("A")
    first = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([Decision("complete", {"reason": "done"})]),
        run_dir=tmp_path / "predicate",
        workspace=workspace,
        budget=Budget(hard_max_steps=3),
        task_revision="predicate-v1",
    )
    assert first.run().completed

    changed = PredicateProfile("B")
    with pytest.raises(ResumeConflict, match="configuration"):
        HarnessRuntime.resume(
            goal=changed.default_goal(),
            profile=changed,
            controller=ScriptedController([Decision("complete", {"reason": "done"})]),
            run_dir=tmp_path / "predicate",
            workspace=workspace,
            budget=Budget(hard_max_steps=3),
            task_revision="predicate-v1",
        )


class ToolClosureProfile(DomainProfile):
    name = "tool-closure-preflight"

    def __init__(self, target: Path):
        self.target = target

    def default_goal(self):
        return GoalContract(goal="tool closure provenance", acceptance=["done"])

    def tools(self):
        target = self.target

        def write(value: str):
            target.write_text(value, encoding="utf-8")
            return value

        return {
            "write": ToolSpec(
                name="write",
                description="write configured target",
                handler=write,
                side_effect=SideEffect.WRITE,
                idempotent=True,
                provenance={"revision": "v1"},
            )
        }

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "done"),
            name="tool-closure-oracle",
        )


def test_resume_rejects_tool_handler_closure_drift(tmp_path):
    workspace = tmp_path / "tool-workspace"
    workspace.mkdir()
    first_profile = ToolClosureProfile(workspace / "a.txt")
    first = HarnessRuntime(
        goal=first_profile.default_goal(),
        profile=first_profile,
        controller=ScriptedController([Decision("complete", {"reason": "done"})]),
        run_dir=tmp_path / "tool",
        workspace=workspace,
        budget=Budget(hard_max_steps=3),
        task_revision="tool-v1",
    )
    assert first.run().completed

    changed_profile = ToolClosureProfile(workspace / "b.txt")
    with pytest.raises(ResumeConflict, match="configuration"):
        HarnessRuntime.resume(
            goal=changed_profile.default_goal(),
            profile=changed_profile,
            controller=ScriptedController([Decision("complete", {"reason": "done"})]),
            run_dir=tmp_path / "tool",
            workspace=workspace,
            budget=Budget(hard_max_steps=3),
            task_revision="tool-v1",
        )
