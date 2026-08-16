from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.failures import Failure, FailureKind, FailureRouter, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.profiles.base import DomainProfile


class StrategyProfile(DomainProfile):
    name = "stage5-strategy-generation-test"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(goal="strategy generation test", acceptance=["external oracle"])

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(False, "not complete"),
            name="stage5-strategy-generation-oracle",
        )


class CompleteController:
    def decide(self, goal, state, context):
        return Decision("complete", {"reason": "unused"})


def test_repeat_count_resets_after_strategy_generation_switch(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = StrategyProfile(workspace)
    runtime = HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=CompleteController(),
        run_dir=tmp_path / "run",
        workspace=workspace,
        budget=Budget(hard_max_steps=20),
        failure_router=FailureRouter(repeat_limit=3),
        task_revision="stage5-strategy-generation-v1",
    )
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")

    failure = Failure(FailureKind.TOOL_ERROR, "same failure", action="tool-a")
    for _ in range(3):
        runtime.fail(failure)
        runtime._apply_pending_recovery()

    assert runtime.state.strategy_generation == 1
    assert runtime.state.recovery_history[-1].action == RecoveryAction.SWITCH_STRATEGY
    assert [f["strategy_generation"] for f in runtime.state.failures] == [0, 0, 0]
    assert [f["repeat_count"] for f in runtime.state.failures] == [1, 2, 3]

    runtime.fail(failure)
    pending = runtime.state.pending_recovery
    assert pending is not None
    assert pending.strategy_generation == 1
    assert pending.repeat_count == 1
    assert pending.action == RecoveryAction.REPAIR
    assert runtime.state.failures[-1]["strategy_generation"] == 1
    assert runtime.state.failures[-1]["repeat_count"] == 1

    runtime._apply_pending_recovery()
    assert runtime.state.strategy_generation == 1
    assert runtime.state.recovery_history[-1].action == RecoveryAction.REPAIR
