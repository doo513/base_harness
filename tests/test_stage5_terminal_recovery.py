from __future__ import annotations

from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.failures import FailureKind, RecoveryAction, RecoveryStatus
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile


class TerminalProfile(DomainProfile):
    name = "stage5-terminal-test"

    def __init__(self, workspace: Path, effect_file: Path, *, fail_tool: bool = False):
        self.workspace = workspace
        self.effect_file = effect_file
        self.fail_tool = fail_tool
        self.handler_calls = 0

    def default_goal(self):
        return GoalContract(goal="exercise terminal recovery", acceptance=["external oracle"])

    def tools(self):
        profile = self

        if self.fail_tool:
            def handler():
                profile.handler_calls += 1
                raise RuntimeError("same tool failure")

            return {
                "external": ToolSpec(
                    name="external",
                    description="failing idempotent test tool",
                    handler=handler,
                    side_effect=SideEffect.NONE,
                    idempotent=True,
                    provenance={"revision": "stage5-terminal-fail-v1"},
                )
            }

        effect_file = self.effect_file

        def handler(value: str):
            profile.handler_calls += 1
            effect_file.write_text(value, encoding="utf-8")
            return value

        return {
            "external": ToolSpec(
                name="external",
                description="non-idempotent external effect",
                handler=handler,
                side_effect=SideEffect.EXTERNAL,
                idempotent=False,
                provenance={"revision": "stage5-terminal-external-v1"},
            )
        }

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(False, "not complete"),
            name="stage5-terminal-oracle",
        )


class ExternalController:
    def __init__(self, *, with_value: bool):
        self.with_value = with_value
        self.calls = 0

    def decide(self, goal, state, context):
        self.calls += 1
        args = {"value": "ONCE"} if self.with_value else {}
        return Decision("tool", {"tool": "external", "args": args})


def test_prepared_only_receipt_reaches_durable_terminal_recovery_without_effect(tmp_path):
    workspace = tmp_path / "ambiguous-workspace"
    workspace.mkdir()
    effect_file = tmp_path / "ambiguous-effect.txt"
    profile = TerminalProfile(workspace, effect_file)
    controller = ExternalController(with_value=True)
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / "ambiguous-run",
        workspace=workspace,
        budget=Budget(hard_max_steps=5),
        task_revision="stage5-terminal-ambiguous-v1",
    )
    action_id = runtime.receipts.action_id(
        run_id=runtime.run_id,
        step=0,
        tool="external",
        args={"value": "ONCE"},
    )
    runtime.receipts.prepare(
        action_id=action_id,
        run_id=runtime.run_id,
        step=0,
        tool="external",
        args={"value": "ONCE"},
    )

    state = runtime.run()

    assert runtime.halted
    assert state.recovery_halted
    assert not state.completed
    assert controller.calls == 1
    assert profile.handler_calls == 0
    assert not effect_file.exists()
    assert state.pending_recovery is None
    terminal = state.recovery_history[-1]
    assert terminal.action == RecoveryAction.CHECKPOINT_STOP
    assert terminal.failure_kind == FailureKind.PERSISTENCE_ERROR
    assert terminal.status == RecoveryStatus.APPLIED


def test_hard_budget_supersedes_pending_nonterminal_recovery_without_retry(tmp_path):
    workspace = tmp_path / "supersede-workspace"
    workspace.mkdir()
    profile = TerminalProfile(
        workspace,
        tmp_path / "unused-effect.txt",
        fail_tool=True,
    )
    controller = ExternalController(with_value=False)
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / "supersede-run",
        workspace=workspace,
        budget=Budget(hard_max_steps=1),
        task_revision="stage5-terminal-supersede-v1",
    )

    state = runtime.run()

    assert runtime.halted
    assert state.step == 1
    assert controller.calls == 1
    assert profile.handler_calls == 1
    assert len(state.recovery_history) >= 2
    superseded = state.recovery_history[-2]
    terminal = state.recovery_history[-1]
    assert superseded.action == RecoveryAction.REPAIR
    assert superseded.status == RecoveryStatus.SUPERSEDED
    assert terminal.action == RecoveryAction.CHECKPOINT_STOP
    assert terminal.failure_kind == FailureKind.BUDGET_EXCEEDED
    assert terminal.status == RecoveryStatus.APPLIED
    assert terminal.details["step_consumed"] is False
