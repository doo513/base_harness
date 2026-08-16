from __future__ import annotations

from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.failures import Failure, FailureKind, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.profiles.base import DomainProfile


class AdversarialRecoveryProfile(DomainProfile):
    name = "stage5-adversarial"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(goal="stage5 adversarial recovery", acceptance=["external oracle"])

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(False, "not complete"),
            name="stage5-adversarial-oracle",
        )


class ProposeForever:
    def decide(self, goal, state, context):
        return Decision("propose", {"key": f"candidate.{state.step}", "value": state.step})


def _runtime(tmp_path: Path, name: str, *, budget=None):
    workspace = tmp_path / f"{name}-workspace"
    workspace.mkdir()
    profile = AdversarialRecoveryProfile(workspace)
    return HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ProposeForever(),
        run_dir=tmp_path / name,
        workspace=workspace,
        budget=budget or Budget(hard_max_steps=10),
        task_revision=f"stage5-adversarial-{name}-v1",
    )


def test_failure_signature_preserves_semantically_meaningful_numbers():
    unauthorized = Failure(FailureKind.ENV_ERROR, "HTTP status 401 from verifier")
    server_error = Failure(FailureKind.ENV_ERROR, "HTTP status 500 from verifier")
    assert unauthorized.signature != server_error.signature

    first_attempt = Failure(
        FailureKind.ENV_ERROR,
        "request id 123 timed out",
        signature_key="oracle-timeout",
    )
    second_attempt = Failure(
        FailureKind.ENV_ERROR,
        "request id 999 timed out",
        signature_key="oracle-timeout",
    )
    assert first_attempt.signature == second_attempt.signature


def test_hard_budget_terminalization_does_not_overshoot_step_limit(tmp_path):
    runtime = _runtime(
        tmp_path,
        "budget",
        budget=Budget(hard_max_steps=1),
    )
    state = runtime.run()

    assert runtime.halted
    assert not state.completed
    assert state.step == 1
    assert state.recovery_halted
    assert state.recovery_history[-1].action == RecoveryAction.CHECKPOINT_STOP
    assert state.recovery_history[-1].failure_kind == FailureKind.BUDGET_EXCEEDED
    assert state.recovery_history[-1].details["step_consumed"] is False
    assert state.recovery_history[-1].details["budget_exhausted_at_apply"] is True


def test_failure_event_and_state_record_share_recovery_transition_id(tmp_path):
    runtime = _runtime(tmp_path, "audit")
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")

    runtime.fail(Failure(FailureKind.TOOL_ERROR, "tool exit 17", action="tool-a"))
    state_record = dict(runtime.state.failures[-1])
    records = runtime.events.verify_chain()
    failure_event = [record for record in records if record["kind"] == "failure"][-1]
    scheduled_event = [record for record in records if record["kind"] == "recovery.scheduled"][-1]

    assert failure_event["payload"] == state_record
    transition_id = state_record["recovery_transition_id"]
    assert scheduled_event["payload"]["transition"]["transition_id"] == transition_id
    assert scheduled_event["payload"]["failure_signature"] == state_record["signature"]
