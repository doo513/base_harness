from __future__ import annotations

from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.failures import Failure, FailureKind, RecoveryAction, RecoveryStatus
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.profiles.base import DomainProfile


class DurabilityProfile(DomainProfile):
    name = "stage5-durability-test"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(goal="exercise recovery durability", acceptance=["external oracle"])

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "done"),
            name="stage5-durability-oracle",
        )


class CompleteController:
    def __init__(self):
        self.calls = 0

    def decide(self, goal, state, context):
        self.calls += 1
        return Decision("complete", {"reason": "done"})


def _make(tmp_path: Path, name: str, *, resume=False, budget=None, controller=None):
    workspace = tmp_path / f"{name}-workspace"
    workspace.mkdir(exist_ok=True)
    profile = DurabilityProfile(workspace)
    controller = controller or CompleteController()
    kwargs = dict(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / name,
        workspace=workspace,
        budget=budget or Budget(hard_max_steps=10),
        task_revision=f"stage5-durability-{name}-v1",
    )
    runtime = HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)
    return runtime, controller


def test_failure_schedule_is_checkpointed_before_outer_loop_snapshot(tmp_path):
    runtime, _ = _make(tmp_path, "scheduled")
    runtime.log("run.start", {"run_id": runtime.run_id, "manifest_hash": runtime.manifest_hash})
    runtime._persist_state("manual.start")

    runtime.fail(Failure(FailureKind.MISSING_INFO, "need observation", action="claim.x"))
    transition_id = runtime.state.pending_recovery.transition_id

    # Simulate process loss immediately after fail() returns: do not execute the
    # ordinary outer-loop transition snapshot. A fresh runtime must still see
    # the scheduled recovery from the fail() commit point.
    resumed_controller = CompleteController()
    resumed, _ = _make(
        tmp_path,
        "scheduled",
        resume=True,
        controller=resumed_controller,
    )

    assert resumed.state.pending_recovery is not None
    assert resumed.state.pending_recovery.transition_id == transition_id
    assert resumed.state.pending_recovery.action == RecoveryAction.OBSERVE
    assert resumed.state.failures[-1]["recovery_transition_id"] == transition_id

    state = resumed.run()
    assert state.completed
    assert state.recovery_history[0].transition_id == transition_id
    assert state.recovery_history[0].status == RecoveryStatus.APPLIED
    assert resumed_controller.calls == 1


def test_budget_expiry_at_recovery_boundary_supersedes_nonterminal_transition(tmp_path):
    runtime, _ = _make(
        tmp_path,
        "budget-race",
        budget=Budget(hard_max_steps=1),
    )
    runtime.log("run.start", {"run_id": runtime.run_id, "manifest_hash": runtime.manifest_hash})
    runtime._persist_state("manual.start")

    # Model the boundary race directly: the failure was classified, but by the
    # moment recovery is about to mutate state the hard step budget is exhausted.
    runtime.state.step = 1
    runtime.fail(Failure(FailureKind.TOOL_ERROR, "repair candidate", action="tool-a"))
    original_id = runtime.state.pending_recovery.transition_id

    assert runtime._apply_pending_recovery() is True
    assert runtime.halted
    assert runtime.state.recovery_halted
    assert runtime.state.step == 1
    assert runtime.state.pending_recovery is None

    superseded = [x for x in runtime.state.recovery_history if x.transition_id == original_id][0]
    terminal = runtime.state.recovery_history[-1]
    assert superseded.status == RecoveryStatus.SUPERSEDED
    assert superseded.action == RecoveryAction.REPAIR
    assert terminal.status == RecoveryStatus.APPLIED
    assert terminal.action == RecoveryAction.CHECKPOINT_STOP
    assert terminal.failure_kind == FailureKind.BUDGET_EXCEEDED
    assert terminal.details["step_consumed"] is False
