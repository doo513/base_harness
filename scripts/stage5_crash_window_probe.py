from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.failures import Failure, FailureKind, RecoveryAction, RecoveryStatus
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.profiles.base import DomainProfile


class ProbeProfile(DomainProfile):
    name = "stage5-crash-window-probe"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(goal="probe recovery durability", acceptance=["external oracle"])

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "done"),
            name="stage5-crash-window-oracle",
        )


class CompleteController:
    def __init__(self):
        self.calls = 0

    def decide(self, goal, state, context):
        self.calls += 1
        return Decision("complete", {"reason": "done"})


def make(root: Path, name: str, *, resume=False, controller=None, budget=None):
    workspace = root / f"{name}-workspace"
    workspace.mkdir(exist_ok=True)
    profile = ProbeProfile(workspace)
    controller = controller or CompleteController()
    kwargs = dict(
        goal=profile.default_goal(), profile=profile, controller=controller,
        run_dir=root / name, workspace=workspace,
        budget=budget or Budget(hard_max_steps=10),
        task_revision=f"stage5-crash-window-{name}-v1",
    )
    runtime = HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)
    return runtime, controller


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-stage5-crash-") as td:
        root = Path(td)
        outcomes = {}

        first, _ = make(root, "scheduled")
        first.log("run.start", {"run_id": first.run_id, "manifest_hash": first.manifest_hash})
        first._persist_state("probe.start")
        first.fail(Failure(FailureKind.MISSING_INFO, "need observation", action="claim.x"))
        transition_id = first.state.pending_recovery.transition_id

        resumed_controller = CompleteController()
        resumed, _ = make(root, "scheduled", resume=True, controller=resumed_controller)
        pending_survived = (
            resumed.state.pending_recovery is not None
            and resumed.state.pending_recovery.transition_id == transition_id
            and resumed.state.failures[-1].get("recovery_transition_id") == transition_id
        )
        resumed_state = resumed.run()
        applied_once = sum(
            1 for item in resumed_state.recovery_history
            if item.transition_id == transition_id and item.status == RecoveryStatus.APPLIED
        ) == 1
        outcomes["scheduled_recovery_survives_crash_boundary"] = {
            "passed": pending_survived and applied_once and resumed_state.completed and resumed_controller.calls == 1,
            "pending_survived": pending_survived,
            "applied_once": applied_once,
            "actor_calls_after_resume": resumed_controller.calls,
        }

        race, _ = make(root, "budget-race", budget=Budget(hard_max_steps=1))
        race.log("run.start", {"run_id": race.run_id, "manifest_hash": race.manifest_hash})
        race._persist_state("probe.start")
        race.state.step = 1
        race.fail(Failure(FailureKind.TOOL_ERROR, "repair candidate", action="tool-a"))
        original_id = race.state.pending_recovery.transition_id
        race._apply_pending_recovery()
        superseded = [x for x in race.state.recovery_history if x.transition_id == original_id][0]
        terminal = race.state.recovery_history[-1]
        outcomes["budget_expiry_at_apply_supersedes_recovery"] = {
            "passed": (
                race.halted
                and race.state.recovery_halted
                and race.state.step == 1
                and superseded.status == RecoveryStatus.SUPERSEDED
                and superseded.action == RecoveryAction.REPAIR
                and terminal.status == RecoveryStatus.APPLIED
                and terminal.action == RecoveryAction.CHECKPOINT_STOP
                and terminal.failure_kind == FailureKind.BUDGET_EXCEEDED
                and terminal.details.get("step_consumed") is False
            ),
            "persisted_step": race.state.step,
            "superseded_status": superseded.status.value,
            "terminal_action": terminal.action.value,
            "terminal_failure": terminal.failure_kind.value,
            "terminal_step_consumed": terminal.details.get("step_consumed"),
        }

        all_passed = all(item["passed"] for item in outcomes.values())
        result = {
            "stage": "05",
            "probe": "crash-window-rc5",
            "outcomes": outcomes,
            "summary": {
                "all_passed": all_passed,
                "scenario_count": len(outcomes),
                "lost_scheduled_recoveries": 0 if outcomes["scheduled_recovery_survives_crash_boundary"]["passed"] else 1,
                "budget_boundary_nonterminal_applies": 0 if outcomes["budget_expiry_at_apply_supersedes_recovery"]["passed"] else 1,
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
