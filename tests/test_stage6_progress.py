from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision, ScriptedController
from harness.core.failures import Failure, FailureKind, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.progress import ProgressPolicy, decision_progress_signatures
from harness.core.runtime import HarnessRuntime
from harness.core.state import Authority, Claim, ClaimStatus
from harness.core.storage import IntegrityError, ResumeConflict
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile


class ProgressProfile(DomainProfile):
    name = "stage6-progress-test"

    def __init__(self, workspace: Path, tools=None, *, accept_completion=True):
        self.workspace = workspace
        self._tools = dict(tools or {})
        self.accept_completion = bool(accept_completion)

    def default_goal(self):
        return GoalContract(goal="exercise deterministic progress control", acceptance=["test done"])

    def tools(self):
        return dict(self._tools)

    def completion_oracle(self):
        accepted = self.accept_completion

        def decide(**_):
            return CompletionResult(accepted, "accepted" if accepted else "rejected")

        return PredicateCompletionOracle(decide, name="stage6-progress-oracle")


def workspace(tmp_path: Path, name: str) -> Path:
    path = tmp_path / f"{name}-workspace"
    path.mkdir()
    return path


def make_runtime(tmp_path: Path, *, name: str, profile, controller, progress_policy=None, resume=False, budget=None):
    kwargs = dict(
        goal=profile.default_goal(), profile=profile, controller=controller,
        run_dir=tmp_path / name, workspace=profile.workspace,
        progress_policy=progress_policy or ProgressPolicy(),
        budget=budget or Budget(hard_max_steps=40), task_revision=f"stage6-{name}-v1",
    )
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)


def constant_tool(value="same"):
    return ToolSpec(
        name="observe", description="deterministic read", handler=lambda: value,
        side_effect=SideEffect.NONE, idempotent=True,
        provenance={"revision": "stage6-test-v1"},
    )


def test_decision_signatures_resist_cosmetic_evasion():
    a = Decision("tool", {"tool": "observe", "args": {"query": "  alpha   beta ", "n": 1}})
    b = Decision("tool", {"args": {"n": 1, "query": "alpha beta"}, "tool": "observe"})
    assert decision_progress_signatures(a) == decision_progress_signatures(b)
    c = Decision("tool", {"tool": "observe", "args": {"query": "different", "n": 2}})
    assert decision_progress_signatures(c)[0] == decision_progress_signatures(a)[0]
    assert decision_progress_signatures(c)[1] != decision_progress_signatures(a)[1]
    assert decision_progress_signatures(Decision("complete", {"reason": "a"})) == decision_progress_signatures(Decision("complete", {"reason": "b"}))
    assert decision_progress_signatures(Decision("refute", {"key": "x", "reason": "a"})) == decision_progress_signatures(Decision("refute", {"key": "x", "reason": "b"}))


def test_successful_observation_novelty_is_activity_not_progress(tmp_path):
    ws = workspace(tmp_path, "activity")
    calls = {"n": 0}

    def changing():
        calls["n"] += 1
        return {"timestamp_like": calls["n"]}

    tool = ToolSpec(
        name="observe", description="changing read", handler=changing,
        side_effect=SideEffect.NONE, idempotent=True,
        provenance={"revision": "stage6-changing-v2"},
    )
    profile = ProgressProfile(ws, {"observe": tool})
    controller = ScriptedController([
        Decision("tool", {"tool": "observe", "args": {}}),
        Decision("tool", {"tool": "observe", "args": {}}),
        Decision("tool", {"tool": "observe", "args": {}}),
        Decision("complete", {"reason": "done"}),
    ])
    runtime = make_runtime(
        tmp_path, name="activity", profile=profile, controller=controller,
        progress_policy=ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=4),
    )
    state = runtime.run()
    assert state.completed
    assert state.progress.progress_events == 0
    assert state.progress.activity_events >= 3
    assert state.progress.epistemic_events == 0
    assert any(f["kind"] == FailureKind.NO_PROGRESS.value for f in state.failures)


def test_duplicate_successful_bytes_are_activity_only_once_then_no_progress(tmp_path):
    ws = workspace(tmp_path, "duplicate")
    profile = ProgressProfile(ws, {"observe": constant_tool()})
    controller = ScriptedController([
        Decision("tool", {"tool": "observe", "args": {}}),
        Decision("tool", {"tool": "observe", "args": {}}),
        Decision("tool", {"tool": "observe", "args": {}}),
        Decision("complete", {"reason": "finish"}),
    ])
    runtime = make_runtime(
        tmp_path, name="duplicate", profile=profile, controller=controller,
        progress_policy=ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=5),
    )
    state = runtime.run()
    assert state.completed
    assert state.progress.progress_events == 0
    assert state.progress.activity_events == 1
    assert any(f["kind"] == FailureKind.NO_PROGRESS.value for f in state.failures)
    assert any(x.action == RecoveryAction.REPLAN for x in state.recovery_history)


def test_verified_fact_transition_is_epistemic_progress(tmp_path):
    ws = workspace(tmp_path, "verified")
    profile = ProgressProfile(ws)
    decision = Decision("propose", {"key": "x", "value": 1})
    runtime = make_runtime(tmp_path, name="verified", profile=profile, controller=ScriptedController([decision]))
    baseline = runtime._progress_baseline()
    claim = Claim("verified.x", 1, status=ClaimStatus.VERIFIED, authority=Authority.SUPPORTED)
    runtime.state.commit_verified(claim)
    result = runtime._evaluate_actor_progress(decision, baseline, allow_trigger=True)
    assert result["made_progress"] is True
    assert result["max_credit"] == 1.0
    assert runtime.state.progress.progress_events == 1
    assert runtime.state.progress.epistemic_events == 1
    assert runtime.state.progress.activity_events == 0


def test_speculative_churn_does_not_self_promote_progress(tmp_path):
    ws = workspace(tmp_path, "speculative")
    profile = ProgressProfile(ws)
    controller = ScriptedController([
        Decision("propose", {"key": "guess", "value": "a"}),
        Decision("propose", {"key": "guess", "value": "b"}),
        Decision("complete", {"reason": "done"}),
    ])
    runtime = make_runtime(
        tmp_path, name="speculative", profile=profile, controller=controller,
        progress_policy=ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=5),
    )
    state = runtime.run()
    assert state.completed
    assert state.progress.progress_events == 0
    assert any(f["kind"] == FailureKind.NO_PROGRESS.value for f in state.failures)


def test_alternating_unproductive_families_hit_global_streak(tmp_path):
    ws = workspace(tmp_path, "alternating")
    profile = ProgressProfile(ws)
    controller = ScriptedController([
        Decision("propose", {"key": "a", "value": 1}),
        Decision("propose", {"key": "b", "value": 2}),
        Decision("propose", {"key": "a", "value": 3}),
        Decision("complete", {"reason": "done"}),
    ])
    runtime = make_runtime(
        tmp_path, name="alternating", profile=profile, controller=controller,
        progress_policy=ProgressPolicy(family_repeat_limit=5, no_progress_streak_limit=3),
    )
    state = runtime.run()
    no_progress = [f for f in state.failures if f["kind"] == FailureKind.NO_PROGRESS.value]
    assert state.completed and len(no_progress) == 1
    assert "consecutive Actor decisions" in no_progress[0]["message"]


def test_specific_tool_failure_is_not_superseded_by_generic_no_progress(tmp_path):
    ws = workspace(tmp_path, "specific")

    def fail_tool():
        raise RuntimeError("specific boom")

    tool = ToolSpec(
        name="fail", description="fails", handler=fail_tool,
        side_effect=SideEffect.NONE, idempotent=True,
        provenance={"revision": "stage6-specific-v1"},
    )
    profile = ProgressProfile(ws, {"fail": tool})
    controller = ScriptedController([
        Decision("tool", {"tool": "fail", "args": {}}),
        Decision("complete", {"reason": "after recovery"}),
    ])
    runtime = make_runtime(
        tmp_path, name="specific", profile=profile, controller=controller,
        progress_policy=ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=2),
    )
    state = runtime.run()
    kinds = [f["kind"] for f in state.failures]
    assert state.completed
    assert kinds.count(FailureKind.TOOL_ERROR.value) == 1
    assert FailureKind.NO_PROGRESS.value not in kinds
    assert state.recovery_history[0].action == RecoveryAction.REPAIR


def test_recovery_transition_is_not_actor_progress_sample(tmp_path):
    ws = workspace(tmp_path, "recovery-sample")
    profile = ProgressProfile(ws)
    runtime = make_runtime(tmp_path, name="recovery-sample", profile=profile, controller=ScriptedController([Decision("complete", {"reason": "done"})]))
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")
    before = runtime.state.progress.evaluations
    runtime.fail(Failure(FailureKind.MISSING_INFO, "need x", action="x"))
    assert runtime.step_once() is True
    assert runtime.state.progress.evaluations == before


def test_strategy_generation_reset_is_not_itself_progress(tmp_path):
    ws = workspace(tmp_path, "generation")
    profile = ProgressProfile(ws)
    runtime = make_runtime(tmp_path, name="generation", profile=profile, controller=ScriptedController([Decision("complete", {"reason": "done"})]))
    runtime.state.progress.no_progress_streak = 4
    runtime.state.progress.last_family_signature = "propose:x"
    runtime.state.progress.family_repeat_count = 4
    runtime.state.strategy_generation = 1
    before_events = runtime.state.progress.progress_events
    assert runtime._sync_progress_generation() is True
    assert runtime.state.progress.no_progress_streak == 0
    assert runtime.state.progress.family_repeat_count == 0
    assert runtime.state.progress.progress_events == before_events
    assert runtime.state.progress.last_progress_generation == 0


def test_progress_state_survives_resume_and_policy_drift_fails_closed(tmp_path):
    ws = workspace(tmp_path, "resume")
    profile = ProgressProfile(ws)
    script = [Decision("propose", {"key": "x", "value": 1})]
    policy = ProgressPolicy(family_repeat_limit=3, no_progress_streak_limit=4)
    runtime = make_runtime(tmp_path, name="resume", profile=profile, controller=ScriptedController(script), progress_policy=policy)
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime.state.progress.no_progress_streak = 2
    runtime.state.progress.last_family_signature = "propose:x"
    runtime.state.progress.family_repeat_count = 2
    runtime.state.progress.evaluations = 7
    runtime.state.progress.activity_events = 3
    runtime._persist_state("manual.progress")

    resumed = make_runtime(tmp_path, name="resume", profile=ProgressProfile(ws), controller=ScriptedController(script), progress_policy=policy, resume=True)
    assert resumed.state.progress.no_progress_streak == 2
    assert resumed.state.progress.family_repeat_count == 2
    assert resumed.state.progress.evaluations == 7
    assert resumed.state.progress.activity_events == 3

    with pytest.raises(ResumeConflict):
        make_runtime(
            tmp_path, name="resume", profile=ProgressProfile(ws), controller=ScriptedController(script),
            progress_policy=ProgressPolicy(family_repeat_limit=4, no_progress_streak_limit=4), resume=True,
        )


def test_tampered_new_artifact_is_never_accepted_as_activity_or_progress(tmp_path):
    ws = workspace(tmp_path, "tamper")
    profile = ProgressProfile(ws, {"observe": constant_tool("original")})
    decision = Decision("tool", {"tool": "observe", "args": {}})
    runtime = make_runtime(tmp_path, name="tamper", profile=profile, controller=ScriptedController([decision]))
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")
    baseline = runtime._progress_baseline()
    runtime._dispatch_decision(decision)
    ref = runtime.state.observations[-1].artifact_ref
    runtime.artifacts.resolve(ref).write_text("tampered", encoding="utf-8")
    with pytest.raises(IntegrityError):
        runtime._evaluate_actor_progress(decision, baseline, allow_trigger=True)
    assert runtime.state.progress.progress_events == 0
    assert runtime.state.progress.activity_events == 0


def test_strategy_exhaustion_routes_to_terminal_escalate(tmp_path):
    ws = workspace(tmp_path, "exhaust")
    profile = ProgressProfile(ws)
    decision = Decision("propose", {"key": "x", "value": 1})
    runtime = make_runtime(
        tmp_path, name="exhaust", profile=profile, controller=ScriptedController([decision]),
        progress_policy=ProgressPolicy(family_repeat_limit=5, no_progress_streak_limit=5, max_strategy_generations_without_progress=1),
    )
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")
    runtime.state.strategy_generation = 1
    baseline = runtime._progress_baseline()
    runtime._dispatch_decision(decision)
    result = runtime._evaluate_actor_progress(decision, baseline, allow_trigger=True)
    assert result["trigger"] == "strategy_exhausted"
    assert runtime.state.pending_recovery is not None
    assert runtime.state.pending_recovery.failure_kind == FailureKind.STRATEGY_EXHAUSTED
    assert runtime._apply_pending_recovery() is True
    assert runtime.halted and runtime.state.recovery_halted
    assert runtime.state.recovery_history[-1].action == RecoveryAction.ESCALATE
