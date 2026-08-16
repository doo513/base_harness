from __future__ import annotations

from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision, ScriptedController
from harness.core.failures import FailureKind, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.progress import ProgressPolicy
from harness.core.runtime import HarnessRuntime
from harness.core.state import Authority, Claim, ClaimStatus
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile


class Profile(DomainProfile):
    name = "stage6-rc2"

    def __init__(self, workspace: Path, tools=None):
        self.workspace = workspace
        self._tools = dict(tools or {})

    def default_goal(self):
        return GoalContract(goal="stage6 rc2", acceptance=["done"])

    def tools(self):
        return dict(self._tools)

    def completion_oracle(self):
        def accept(**_):
            return CompletionResult(True, "done")
        return PredicateCompletionOracle(accept, name="stage6-rc2-oracle")


def make_runtime(tmp_path, name, profile, controller, policy=None):
    return HarnessRuntime(
        goal=profile.default_goal(), profile=profile, controller=controller,
        run_dir=tmp_path / name, workspace=profile.workspace,
        progress_policy=policy or ProgressPolicy(),
        budget=Budget(hard_max_steps=60), task_revision=f"stage6-rc2-{name}",
    )


def test_verified_fact_evidence_ref_churn_is_not_progress_content(tmp_path):
    ws = tmp_path / "facts-ws"; ws.mkdir()
    runtime = make_runtime(
        tmp_path, "facts", Profile(ws),
        ScriptedController([Decision("complete", {"reason": "done"})]),
    )
    runtime.state.commit_verified(Claim(
        "answer", {"value": "alpha   beta"}, status=ClaimStatus.VERIFIED,
        authority=Authority.ENVIRONMENT, evidence_refs=["artifact://first"],
    ))
    first = runtime._progress_facts_hash()
    runtime.state.commit_verified(Claim(
        "answer", {"value": "alpha beta"}, status=ClaimStatus.VERIFIED,
        authority=Authority.ENVIRONMENT, evidence_refs=["artifact://second"],
    ))
    assert runtime._progress_facts_hash() == first
    runtime.state.commit_verified(Claim(
        "answer", {"value": "different"}, status=ClaimStatus.VERIFIED,
        authority=Authority.ENVIRONMENT, evidence_refs=["artifact://third"],
    ))
    assert runtime._progress_facts_hash() != first


def test_global_no_progress_triggers_share_repeat_identity_across_families(tmp_path):
    ws = tmp_path / "global-ws"; ws.mkdir()
    decisions = []
    for key in ("a", "b", "c", "d", "e", "f"):
        decisions.append(Decision("propose", {"key": key, "value": key}))
    decisions.append(Decision("complete", {"reason": "done"}))
    runtime = make_runtime(
        tmp_path, "global", Profile(ws), ScriptedController(decisions),
        ProgressPolicy(
            family_repeat_limit=10,
            no_progress_streak_limit=2,
            max_strategy_generations_without_progress=5,
        ),
    )
    state = runtime.run()
    global_failures = [
        f for f in state.failures
        if f["kind"] == FailureKind.NO_PROGRESS.value
        and f["target"] == "stage6:global_no_progress"
    ]
    assert state.completed
    assert [f["repeat_count"] for f in global_failures] == [1, 2, 3]
    assert [x.action for x in state.recovery_history[:3]] == [
        RecoveryAction.REPLAN, RecoveryAction.REPLAN, RecoveryAction.SWITCH_STRATEGY,
    ]
    assert state.strategy_generation == 1


def test_historical_success_artifact_tamper_becomes_terminal_before_next_actor(tmp_path):
    ws = tmp_path / "historical-ws"; ws.mkdir()
    tool = ToolSpec(
        name="observe", description="read", handler=lambda: {"stable": True},
        side_effect=SideEffect.NONE, idempotent=True,
        provenance={"revision": "stage6-rc2"},
    )
    controller = ScriptedController([
        Decision("tool", {"tool": "observe", "args": {}}),
        Decision("complete", {"reason": "must not run"}),
    ])
    runtime = make_runtime(tmp_path, "historical", Profile(ws, {"observe": tool}), controller)
    runtime.log("run.start", {"run_id": runtime.run_id})
    runtime._persist_state("manual.start")

    assert runtime.step_once() is False
    runtime.state.step += 1
    runtime._persist_state("manual.first-actor")
    assert controller.index == 1
    ref = runtime.state.observations[-1].artifact_ref
    runtime.artifacts.resolve(ref).write_text("tampered historical bytes", encoding="utf-8")

    assert runtime.step_once() is False
    assert controller.index == 1
    assert runtime.state.pending_recovery is not None
    assert runtime.state.pending_recovery.failure_kind == FailureKind.PERSISTENCE_ERROR
    assert runtime.step_once() is True
    assert runtime.halted
    assert runtime.state.recovery_history[-1].action == RecoveryAction.CHECKPOINT_STOP


def test_observation_fingerprint_ignores_cosmetic_json_key_order_and_whitespace(tmp_path):
    ws = tmp_path / "fingerprint-ws"; ws.mkdir()
    runtime = make_runtime(
        tmp_path, "fingerprint", Profile(ws),
        ScriptedController([Decision("complete", {"reason": "done"})]),
    )
    first = runtime.artifacts.put_json("first.json", {
        "ok": True, "output": {"a": "alpha   beta", "b": 2}, "error": None,
    })
    second = runtime.artifacts.put_json("second.json", {
        "error": None, "output": {"b": 2, "a": "alpha beta"}, "ok": True,
    })
    assert first != second
    assert runtime._verified_observation_fingerprint(first) == runtime._verified_observation_fingerprint(second)
