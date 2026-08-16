from __future__ import annotations

from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.failures import Failure, FailureKind, FailureRouter, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.core.security import Capability, CapabilityPolicy, Principal
from harness.core.state import Authority, Claim, ClaimStatus
from harness.core.tools import SideEffect, ToolSpec
from harness.core.verification import (
    EvidenceRefVerifier,
    ExistsVerifier,
    VerificationContract,
    VerificationLevel,
    VerificationRequirement,
)
from harness.profiles.base import DomainProfile


class RecoveryProfile(DomainProfile):
    name = "recovery-test"

    def __init__(self, workspace: Path, tools=None):
        self.workspace = workspace
        self._tools = dict(tools or {})

    def default_goal(self):
        return GoalContract(goal="exercise recovery", acceptance=["test oracle accepts"])

    def tools(self):
        return dict(self._tools)

    def completion_oracle(self):
        def accept(**_):
            return CompletionResult(True, "recovery test complete")
        return PredicateCompletionOracle(accept, name="recovery-test-oracle")


class EvidenceRecoveryProfile(RecoveryProfile):
    name = "recovery-evidence-test"

    def verifiers(self):
        return [ExistsVerifier(), EvidenceRefVerifier()]

    def minimum_verification_level(self):
        return VerificationLevel.STRUCTURAL

    def verification_contract(self):
        return VerificationContract(
            minimum_level=VerificationLevel.STRUCTURAL,
            requirements=(
                VerificationRequirement("candidate_exists", VerificationLevel.SCHEMA),
                VerificationRequirement("evidence_present", VerificationLevel.STRUCTURAL, require_evidence=True),
            ),
        )


class ToolFailThenComplete:
    def __init__(self, tool="fail"):
        self.tool = tool

    def decide(self, goal, state, context):
        if not context["recent_failures"]:
            return Decision("tool", {"tool": self.tool, "args": {}})
        return Decision("complete", {"reason": "after recovery"})


class MissingThenComplete:
    def decide(self, goal, state, context):
        if not context["recent_failures"]:
            return Decision("verify_claim", {"key": "missing.claim"})
        return Decision("complete", {"reason": "after observe"})


class VerificationFailThenComplete:
    def decide(self, goal, state, context):
        if context["recent_failures"]:
            return Decision("complete", {"reason": "after replan"})
        if "claim.x" not in state.hypotheses:
            return Decision("propose", {"key": "claim.x", "value": True})
        return Decision("verify_claim", {"key": "claim.x"})


class CountingComplete:
    def __init__(self):
        self.calls = 0

    def decide(self, goal, state, context):
        self.calls += 1
        return Decision("complete", {"reason": "done"})


class CountingTool:
    def __init__(self, tool="write"):
        self.tool = tool
        self.calls = 0

    def decide(self, goal, state, context):
        self.calls += 1
        return Decision("tool", {"tool": self.tool, "args": {}})


def make_runtime(
    tmp_path: Path,
    *,
    name: str,
    profile,
    controller,
    policy=None,
    router=None,
    resume=False,
    budget=None,
):
    kwargs = dict(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=tmp_path / name,
        workspace=profile.workspace,
        capability_policy=policy,
        failure_router=router,
        budget=budget or Budget(hard_max_steps=20),
        task_revision=f"stage5-{name}-v1",
    )
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)


def init_workspace(tmp_path: Path, name: str) -> Path:
    workspace = tmp_path / f"{name}-workspace"
    workspace.mkdir()
    return workspace


def test_tool_error_becomes_durable_repair_without_automatic_retry(tmp_path):
    workspace = init_workspace(tmp_path, "repair")
    calls = {"handler": 0}

    def fail_handler():
        calls["handler"] += 1
        raise RuntimeError("boom")

    profile = RecoveryProfile(workspace, {
        "fail": ToolSpec(
            name="fail", description="fails", handler=fail_handler,
            side_effect=SideEffect.NONE, idempotent=True,
            provenance={"revision": "stage5-test-v1"},
        )
    })
    runtime = make_runtime(
        tmp_path, name="repair", profile=profile,
        controller=ToolFailThenComplete(),
    )
    state = runtime.run()

    assert state.completed
    assert calls["handler"] == 1
    assert [x.action for x in state.recovery_history] == [RecoveryAction.REPAIR]
    assert runtime.metrics["recovery_transitions"] == 1
    assert state.recovery_directive is None


def test_missing_information_becomes_observe_transition(tmp_path):
    workspace = init_workspace(tmp_path, "observe")
    profile = RecoveryProfile(workspace)
    runtime = make_runtime(
        tmp_path, name="observe", profile=profile,
        controller=MissingThenComplete(),
    )
    state = runtime.run()
    assert state.completed
    assert state.recovery_history[0].action == RecoveryAction.OBSERVE
    assert state.recovery_history[0].failure_kind == FailureKind.MISSING_INFO


def test_verification_failure_becomes_replan_transition(tmp_path):
    workspace = init_workspace(tmp_path, "replan")
    profile = EvidenceRecoveryProfile(workspace)
    runtime = make_runtime(
        tmp_path, name="replan", profile=profile,
        controller=VerificationFailThenComplete(),
    )
    state = runtime.run()
    assert state.completed
    assert any(x.action == RecoveryAction.REPLAN for x in state.recovery_history)
    assert any(x.failure_kind == FailureKind.VERIFICATION_FAILED for x in state.recovery_history)


def test_logical_rollback_removes_only_targeted_untrusted_hypothesis(tmp_path):
    workspace = init_workspace(tmp_path, "rollback")
    profile = RecoveryProfile(workspace)
    runtime = make_runtime(
        tmp_path, name="rollback", profile=profile,
        controller=CountingComplete(),
    )
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")

    verified = Claim(
        "trusted.fact", 7,
        status=ClaimStatus.VERIFIED,
        authority=Authority.ENVIRONMENT,
        evidence_refs=["artifact://trusted"],
    )
    runtime.state.commit_verified(verified)
    runtime.state.propose(Claim("speculative", "wrong"))
    before = runtime.state.facts["trusted.fact"].dump()

    runtime.fail(Failure(
        FailureKind.HYPOTHESIS_REFUTED,
        "refuted path",
        action="speculative",
    ))
    assert runtime._apply_pending_recovery() is True

    assert "speculative" not in runtime.state.hypotheses
    assert runtime.state.facts["trusted.fact"].dump() == before
    transition = runtime.state.recovery_history[-1]
    assert transition.action == RecoveryAction.ROLLBACK
    assert transition.details["rollback_scope"] == "untrusted_hypothesis_only"


def test_repeat_threshold_switches_strategy_once(tmp_path):
    workspace = init_workspace(tmp_path, "switch")
    profile = RecoveryProfile(workspace)
    runtime = make_runtime(
        tmp_path, name="switch", profile=profile,
        controller=CountingComplete(),
        router=FailureRouter(repeat_limit=3),
    )
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")

    failure = Failure(FailureKind.TOOL_ERROR, "same failure 123", action="same-tool")
    for _ in range(3):
        runtime.fail(failure)
        runtime._apply_pending_recovery()

    actions = [x.action for x in runtime.state.recovery_history]
    assert actions == [RecoveryAction.REPAIR, RecoveryAction.REPAIR, RecoveryAction.SWITCH_STRATEGY]
    assert runtime.state.strategy_generation == 1
    assert runtime.metrics["strategy_switches"] == 1


def test_unsafe_environment_retry_is_downgraded_but_explicit_safe_retry_is_allowed():
    router = FailureRouter()
    unsafe = Failure(FailureKind.ENV_ERROR, "temporary environment issue", retry_safe=False)
    safe = Failure(FailureKind.ENV_ERROR, "temporary environment issue", retry_safe=True)
    assert router.route(unsafe, 1) == RecoveryAction.OBSERVE
    assert router.route(safe, 1) == RecoveryAction.RETRY


def test_security_violation_terminally_stops_before_actor_can_retry(tmp_path):
    workspace = init_workspace(tmp_path, "security")
    handler_calls = {"count": 0}

    def write_handler():
        handler_calls["count"] += 1
        return "should-not-run"

    profile = RecoveryProfile(workspace, {
        "write": ToolSpec(
            name="write", description="write", handler=write_handler,
            side_effect=SideEffect.WRITE, idempotent=True,
            provenance={"revision": "stage5-security-v1"},
        )
    })
    policy = CapabilityPolicy(grants={
        Principal.ACTOR: frozenset({Capability.TOOL_READ}),
        Principal.VERIFIER: frozenset({Capability.VERIFY}),
        Principal.ORACLE: frozenset({Capability.ORACLE_EXECUTE}),
        Principal.KERNEL: frozenset({Capability.STATE_COMMIT, Capability.LEDGER_WRITE}),
    })
    controller = CountingTool()
    runtime = make_runtime(
        tmp_path, name="security", profile=profile,
        controller=controller, policy=policy,
    )
    state = runtime.run()

    assert not state.completed
    assert runtime.halted
    assert state.recovery_halted
    assert controller.calls == 1
    assert handler_calls["count"] == 0
    assert any(f["kind"] == FailureKind.SECURITY_VIOLATION.value for f in state.failures)
    assert state.recovery_history[-1].action == RecoveryAction.CHECKPOINT_STOP


def test_pending_recovery_is_applied_before_actor_after_resume(tmp_path):
    workspace = init_workspace(tmp_path, "resume-pending")
    profile = RecoveryProfile(workspace)
    first_controller = CountingComplete()
    runtime = make_runtime(
        tmp_path, name="resume-pending", profile=profile,
        controller=first_controller,
    )
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")
    runtime.fail(Failure(FailureKind.MISSING_INFO, "need evidence", action="x"))
    runtime._persist_state("manual.pending-recovery")

    resumed_controller = CountingComplete()
    resumed_profile = RecoveryProfile(workspace)
    resumed = make_runtime(
        tmp_path, name="resume-pending", profile=resumed_profile,
        controller=resumed_controller, resume=True,
    )
    state = resumed.run()

    assert state.completed
    assert resumed_controller.calls == 1
    assert state.recovery_history[0].action == RecoveryAction.OBSERVE
    kinds = [record["kind"] for record in resumed.events.verify_chain()]
    resume_index = kinds.index("run.resume")
    recovery_index = kinds.index("recovery.transition", resume_index)
    decision_index = kinds.index("decision", recovery_index)
    assert resume_index < recovery_index < decision_index


def test_terminal_recovery_remains_halted_after_resume(tmp_path):
    workspace = init_workspace(tmp_path, "resume-terminal")
    profile = RecoveryProfile(workspace)
    runtime = make_runtime(
        tmp_path, name="resume-terminal", profile=profile,
        controller=CountingComplete(),
    )
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")
    runtime.fail(Failure(FailureKind.SECURITY_VIOLATION, "blocked", action="tool"))
    runtime._apply_pending_recovery()
    assert runtime.state.recovery_halted

    resumed_controller = CountingComplete()
    resumed = make_runtime(
        tmp_path, name="resume-terminal",
        profile=RecoveryProfile(workspace), controller=resumed_controller,
        resume=True,
    )
    state = resumed.run()
    assert resumed.halted
    assert state.recovery_halted
    assert resumed_controller.calls == 0


def test_recovery_transition_consumes_durable_harness_step(tmp_path):
    workspace = init_workspace(tmp_path, "step")
    profile = RecoveryProfile(workspace)
    runtime = make_runtime(
        tmp_path, name="step", profile=profile,
        controller=CountingComplete(),
    )
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")
    initial = runtime.state.step
    runtime.fail(Failure(FailureKind.TOOL_ERROR, "repair me", action="x"))
    runtime._apply_pending_recovery()
    assert runtime.state.step == initial + 1
    assert runtime.state.recovery_history[-1].applied_step == runtime.state.step
