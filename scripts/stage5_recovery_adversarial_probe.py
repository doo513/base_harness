from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.failures import Failure, FailureKind, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.profiles.base import DomainProfile


class ProbeProfile(DomainProfile):
    name = "stage5-adversarial-probe"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(goal="probe stage5 edge cases", acceptance=["external oracle"])

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(False, "not complete"),
            name="stage5-adversarial-probe-oracle",
        )


class ProposeForever:
    def decide(self, goal, state, context):
        return Decision("propose", {"key": f"probe.{state.step}", "value": state.step})


def make(root: Path, name: str, *, budget=None):
    workspace = root / f"{name}-workspace"
    workspace.mkdir()
    profile = ProbeProfile(workspace)
    return HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ProposeForever(),
        run_dir=root / name,
        workspace=workspace,
        budget=budget or Budget(hard_max_steps=10),
        task_revision=f"stage5-adversarial-probe-{name}-v1",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-stage5-adv-") as td:
        root = Path(td)

        sig_401 = Failure(FailureKind.ENV_ERROR, "HTTP status 401 from verifier").signature
        sig_500 = Failure(FailureKind.ENV_ERROR, "HTTP status 500 from verifier").signature
        signature_case = {
            "passed": sig_401 != sig_500,
            "distinct": sig_401 != sig_500,
        }

        budget_runtime = make(root, "budget", budget=Budget(hard_max_steps=1))
        budget_state = budget_runtime.run()
        budget_transition = budget_state.recovery_history[-1]
        budget_case = {
            "passed": (
                budget_runtime.halted
                and budget_state.step == 1
                and budget_transition.action == RecoveryAction.CHECKPOINT_STOP
                and budget_transition.details.get("step_consumed") is False
            ),
            "hard_max_steps": 1,
            "persisted_step": budget_state.step,
            "action": budget_transition.action.value,
            "step_consumed": budget_transition.details.get("step_consumed"),
        }

        audit_runtime = make(root, "audit")
        audit_runtime.log("run.start", {"run_id": audit_runtime.run_id})
        audit_runtime._persist_state("probe.start")
        audit_runtime.fail(Failure(FailureKind.TOOL_ERROR, "tool exit 17", action="tool-a"))
        state_failure = dict(audit_runtime.state.failures[-1])
        records = audit_runtime.events.verify_chain()
        failure_event = [x for x in records if x["kind"] == "failure"][-1]
        scheduled_event = [x for x in records if x["kind"] == "recovery.scheduled"][-1]
        linked = state_failure["recovery_transition_id"]
        audit_case = {
            "passed": (
                failure_event["payload"] == state_failure
                and scheduled_event["payload"]["transition"]["transition_id"] == linked
            ),
            "failure_payload_matches_state": failure_event["payload"] == state_failure,
            "transition_link_matches": scheduled_event["payload"]["transition"]["transition_id"] == linked,
        }

        outcomes = {
            "meaningful_numeric_failure_identity": signature_case,
            "hard_budget_no_step_overshoot": budget_case,
            "failure_recovery_audit_link": audit_case,
        }
        all_passed = all(case["passed"] for case in outcomes.values())
        result = {
            "stage": "05",
            "probe": "adversarial-rc3",
            "outcomes": outcomes,
            "summary": {
                "all_passed": all_passed,
                "scenario_count": len(outcomes),
                "step_overshoot": max(0, budget_state.step - 1),
                "audit_link_mismatches": 0 if audit_case["passed"] else 1,
                "numeric_signature_collisions": 0 if signature_case["passed"] else 1,
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
