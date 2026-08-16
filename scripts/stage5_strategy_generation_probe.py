from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.failures import Failure, FailureKind, FailureRouter, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.profiles.base import DomainProfile


class Profile(DomainProfile):
    name = "stage5-strategy-generation-probe"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(goal="probe strategy generation", acceptance=["external oracle"])

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(False, "not complete"),
            name="stage5-strategy-generation-probe-oracle",
        )


class Controller:
    def decide(self, goal, state, context):
        return Decision("complete", {"reason": "unused"})


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-stage5-generation-") as td:
        root = Path(td)
        workspace = root / "workspace"
        workspace.mkdir()
        profile = Profile(workspace)
        runtime = HarnessRuntime(
            goal=profile.default_goal(), profile=profile, controller=Controller(),
            run_dir=root / "run", workspace=workspace,
            budget=Budget(hard_max_steps=20), failure_router=FailureRouter(repeat_limit=3),
            task_revision="stage5-strategy-generation-probe-v1",
        )
        runtime.log("run.start", {"run_id": runtime.run_id})
        runtime._persist_state("probe.start")

        failure = Failure(FailureKind.TOOL_ERROR, "same failure", action="tool-a")
        for _ in range(3):
            runtime.fail(failure)
            runtime._apply_pending_recovery()

        switched = (
            runtime.state.strategy_generation == 1
            and runtime.state.recovery_history[-1].action == RecoveryAction.SWITCH_STRATEGY
        )
        runtime.fail(failure)
        pending = runtime.state.pending_recovery
        reset = (
            pending is not None
            and pending.strategy_generation == 1
            and pending.repeat_count == 1
            and pending.action == RecoveryAction.REPAIR
            and runtime.state.failures[-1]["strategy_generation"] == 1
            and runtime.state.failures[-1]["repeat_count"] == 1
        )
        if pending is not None:
            runtime._apply_pending_recovery()

        result = {
            "stage": "05",
            "probe": "strategy-generation-rc6",
            "outcomes": {
                "switch_at_threshold": {
                    "passed": switched,
                    "strategy_generation": runtime.state.strategy_generation,
                },
                "repeat_scope_resets_in_new_generation": {
                    "passed": reset,
                    "latest_action": runtime.state.recovery_history[-1].action.value,
                    "latest_failure_repeat_count": runtime.state.failures[-1]["repeat_count"],
                    "latest_failure_generation": runtime.state.failures[-1]["strategy_generation"],
                },
            },
            "summary": {
                "all_passed": switched and reset,
                "consecutive_switches_after_one_new_failure": 0 if reset else 1,
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
