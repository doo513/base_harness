from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.controller import Decision
from harness.core.contracts import GoalContract
from harness.core.failures import Failure, FailureKind, FailureRouter, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.core.state import Authority, Claim, ClaimStatus
from harness.profiles.base import DomainProfile


class ProbeProfile(DomainProfile):
    name = "stage5-probe"

    def __init__(self, workspace):
        self.workspace = Path(workspace)

    def default_goal(self):
        return GoalContract(goal="probe recovery", acceptance=["probe completes"])

    def completion_oracle(self):
        def accept(**_):
            return CompletionResult(True, "probe complete")
        return PredicateCompletionOracle(accept, name="stage5-probe-oracle")


class CompleteController:
    def decide(self, goal, state, context):
        return Decision("complete", {"reason": "probe done"})


def make(root: Path, name: str, *, resume=False, router=None):
    workspace = root / f"{name}-workspace"
    workspace.mkdir(exist_ok=True)
    profile = ProbeProfile(workspace)
    kwargs = dict(
        goal=profile.default_goal(), profile=profile, controller=CompleteController(),
        run_dir=root / name, workspace=workspace, budget=Budget(hard_max_steps=20),
        task_revision=f"stage5-probe-{name}-v1", failure_router=router,
    )
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)


def initialize(runtime):
    runtime.log("run.start", {"run_id": runtime.run_id, "manifest_hash": runtime.manifest_hash})
    runtime._persist_state("probe.start")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vsh-stage5-") as td:
        root = Path(td)
        outcomes = {}

        repair = make(root, "repair")
        initialize(repair)
        step_before = repair.state.step
        repair.fail(Failure(FailureKind.TOOL_ERROR, "probe tool failure", action="probe-tool"))
        repair._apply_pending_recovery()
        repair_transition = repair.state.recovery_history[-1]
        outcomes["repair_control_only"] = {
            "passed": (
                repair_transition.action == RecoveryAction.REPAIR
                and repair.metrics["tool_calls"] == 0
                and repair.state.step == step_before + 1
            ),
            "action": repair_transition.action.value,
            "tool_calls": repair.metrics["tool_calls"],
            "step_delta": repair.state.step - step_before,
        }

        switch = make(root, "switch", router=FailureRouter(repeat_limit=3))
        initialize(switch)
        trusted = Claim(
            "trusted", 42, status=ClaimStatus.VERIFIED,
            authority=Authority.ENVIRONMENT,
        )
        switch.state.commit_verified(trusted)
        fact_before = switch.state.facts["trusted"].dump()
        failure = Failure(FailureKind.TOOL_ERROR, "same failure 777", action="same")
        for _ in range(3):
            switch.fail(failure)
            switch._apply_pending_recovery()
        fact_after = switch.state.facts["trusted"].dump()
        outcomes["strategy_switch_and_fact_integrity"] = {
            "passed": (
                switch.state.strategy_generation == 1
                and switch.state.recovery_history[-1].action == RecoveryAction.SWITCH_STRATEGY
                and fact_before == fact_after
            ),
            "strategy_generation": switch.state.strategy_generation,
            "last_action": switch.state.recovery_history[-1].action.value,
            "fact_unchanged": fact_before == fact_after,
        }

        security = make(root, "security")
        initialize(security)
        security.fail(Failure(FailureKind.SECURITY_VIOLATION, "policy blocked", action="tool"))
        security._apply_pending_recovery()
        outcomes["security_fail_closed"] = {
            "passed": (
                security.state.recovery_halted
                and security.state.recovery_history[-1].action == RecoveryAction.CHECKPOINT_STOP
                and security.metrics["tool_calls"] == 0
            ),
            "halted": security.state.recovery_halted,
            "action": security.state.recovery_history[-1].action.value,
            "tool_calls": security.metrics["tool_calls"],
        }

        pending = make(root, "resume")
        initialize(pending)
        pending.fail(Failure(FailureKind.MISSING_INFO, "need observation", action="x"))
        pending._persist_state("probe.pending")
        resumed = make(root, "resume", resume=True)
        resumed_state = resumed.run()
        kinds = [record["kind"] for record in resumed.events.verify_chain()]
        resume_i = kinds.index("run.resume")
        recovery_i = kinds.index("recovery.transition", resume_i)
        decision_i = kinds.index("decision", recovery_i)
        outcomes["resume_orders_recovery_before_actor"] = {
            "passed": resumed_state.completed and resume_i < recovery_i < decision_i,
            "completed": resumed_state.completed,
            "event_order": [resume_i, recovery_i, decision_i],
        }

        unsafe_retries = sum(
            1 for value in outcomes.values()
            if value.get("action") == RecoveryAction.RETRY.value
        )
        verified_fact_mutations = 0 if outcomes["strategy_switch_and_fact_integrity"]["fact_unchanged"] else 1
        all_passed = all(bool(value["passed"]) for value in outcomes.values())
        summary = {
            "stage": "05",
            "outcomes": outcomes,
            "summary": {
                "all_passed": all_passed,
                "scenario_count": len(outcomes),
                "unsafe_retries": unsafe_retries,
                "verified_fact_mutations": verified_fact_mutations,
                "resume_recovery_divergence": 0 if outcomes["resume_orders_recovery_before_actor"]["passed"] else 1,
            },
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if all_passed and unsafe_retries == 0 and verified_fact_mutations == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
