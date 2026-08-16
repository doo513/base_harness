from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision, ScriptedController
from harness.core.failures import Failure, FailureKind, RecoveryAction
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.progress import ProgressPolicy
from harness.core.runtime import HarnessRuntime
from harness.core.state import Authority, Claim, ClaimStatus
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile


class ProbeProfile(DomainProfile):
    name = "stage6-progress-strategy"

    def __init__(self, workspace: Path, tools=None):
        self.workspace = workspace
        self._tools = dict(tools or {})

    def default_goal(self):
        return GoalContract(goal="stage6 strategy probe", acceptance=["probe completes"])

    def tools(self):
        return dict(self._tools)

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "probe complete"),
            name="stage6-strategy-oracle",
        )


def _runtime(root, name, profile, policy=None):
    return HarnessRuntime(
        goal=profile.default_goal(),
        profile=profile,
        controller=ScriptedController([]),
        run_dir=root / name,
        workspace=profile.workspace,
        progress_policy=policy or ProgressPolicy(),
        budget=Budget(hard_max_steps=60),
        task_revision=f"stage6-strategy-{name}-v1",
    )


def _run() -> dict:
    with tempfile.TemporaryDirectory(prefix="stage6-strategy-") as td:
        root = Path(td)
        outcomes = {}

        # 1. Verified content change is progress.
        ws1 = root / "fact-ws"; ws1.mkdir()
        r1 = _runtime(root, "fact", ProbeProfile(ws1))
        r1.log("run.start", {"run_id": r1.run_id}); r1._persist_state("manual.start")
        decision = Decision("propose", {"key": "x", "value": 1})
        baseline = r1._progress_baseline()
        r1.state.commit_verified(Claim(
            "answer", 42, status=ClaimStatus.VERIFIED, authority=Authority.ENVIRONMENT,
        ))
        fact_result = r1._evaluate_actor_progress(decision, baseline, allow_trigger=True)
        outcomes["verified_fact_change_is_progress"] = {
            "passed": fact_result["made_progress"] and "verified_fact_content_changed" in fact_result["progress_reasons"],
            "reasons": fact_result["progress_reasons"],
        }

        # 2/3. Same successful evidence remains known after a strategy switch;
        # a later real progress event resets the exhaustion generation horizon.
        ws2 = root / "evidence-ws"; ws2.mkdir()
        tool = ToolSpec(
            name="observe", description="constant read", handler=lambda: "same-result",
            side_effect=SideEffect.NONE, idempotent=True,
            provenance={"revision": "stage6-strategy-v1"},
        )
        r2 = _runtime(
            root, "evidence", ProbeProfile(ws2, {"observe": tool}),
            ProgressPolicy(
                family_repeat_limit=8,
                no_progress_streak_limit=8,
                max_strategy_generations_without_progress=2,
            ),
        )
        r2.log("run.start", {"run_id": r2.run_id}); r2._persist_state("manual.start")
        tool_decision = Decision("tool", {"tool": "observe", "args": {}})
        b1 = r2._progress_baseline(); r2._dispatch_decision(tool_decision)
        first = r2._evaluate_actor_progress(tool_decision, b1, allow_trigger=True)
        r2.state.strategy_generation = 1
        b2 = r2._progress_baseline(); r2._dispatch_decision(tool_decision)
        second = r2._evaluate_actor_progress(tool_decision, b2, allow_trigger=True)
        outcomes["same_evidence_after_strategy_switch_not_novel"] = {
            "passed": first["made_progress"] and not second["made_progress"]
                      and second["generation_reset"] and r2.state.progress.last_progress_generation == 0,
            "first_progress": first["made_progress"],
            "second_progress": second["made_progress"],
            "last_progress_generation": r2.state.progress.last_progress_generation,
        }
        b3 = r2._progress_baseline()
        r2.state.commit_verified(Claim(
            "new_fact", "verified", status=ClaimStatus.VERIFIED, authority=Authority.ENVIRONMENT,
        ))
        third = r2._evaluate_actor_progress(
            Decision("propose", {"key": "new", "value": 1}), b3, allow_trigger=True
        )
        outcomes["real_progress_resets_exhaustion_horizon"] = {
            "passed": third["made_progress"] and r2.state.progress.last_progress_generation == 1,
            "last_progress_generation": r2.state.progress.last_progress_generation,
        }

        # 4. Generation exhaustion routes through Stage 05 terminal ESCALATE.
        ws3 = root / "exhaust-ws"; ws3.mkdir()
        r3 = _runtime(
            root, "exhaust", ProbeProfile(ws3),
            ProgressPolicy(
                family_repeat_limit=8,
                no_progress_streak_limit=8,
                max_strategy_generations_without_progress=1,
            ),
        )
        r3.log("run.start", {"run_id": r3.run_id}); r3._persist_state("manual.start")
        r3.state.strategy_generation = 1
        no_progress_decision = Decision("propose", {"key": "x", "value": 1})
        b4 = r3._progress_baseline(); r3._dispatch_decision(no_progress_decision)
        exhausted = r3._evaluate_actor_progress(no_progress_decision, b4, allow_trigger=True)
        pending_exhaustion = (
            r3.state.pending_recovery is not None
            and r3.state.pending_recovery.failure_kind == FailureKind.STRATEGY_EXHAUSTED
        )
        r3._apply_pending_recovery()
        outcomes["strategy_exhaustion_terminal_escalate"] = {
            "passed": exhausted["trigger"] == "strategy_exhausted" and pending_exhaustion
                      and r3.halted and r3.state.recovery_history[-1].action == RecoveryAction.ESCALATE,
            "trigger": exhausted["trigger"],
            "halted": r3.halted,
            "terminal_action": r3.state.recovery_history[-1].action.value,
        }

        # 5. Recovery itself does not become an Actor no-progress sample.
        ws4 = root / "recovery-ws"; ws4.mkdir()
        r4 = _runtime(root, "recovery", ProbeProfile(ws4))
        r4.log("run.start", {"run_id": r4.run_id}); r4._persist_state("manual.start")
        before_eval = r4.state.progress.evaluations
        r4.fail(Failure(FailureKind.MISSING_INFO, "need x", action="x"))
        applied = r4.step_once()
        outcomes["recovery_not_actor_progress_sample"] = {
            "passed": applied is True and r4.state.progress.evaluations == before_eval,
            "evaluations_before": before_eval,
            "evaluations_after": r4.state.progress.evaluations,
        }

        # 6. Volatile failed output remains in specific Stage05 failure handling;
        # changing error text never creates progress.
        ws5 = root / "failure-ws"; ws5.mkdir()
        calls = {"n": 0}
        def changing_failure():
            calls["n"] += 1
            raise RuntimeError(f"failure-{calls['n']}")
        fail_tool = ToolSpec(
            name="fail", description="volatile failure", handler=changing_failure,
            side_effect=SideEffect.NONE, idempotent=True,
            provenance={"revision": "stage6-strategy-v1"},
        )
        script = [
            Decision("tool", {"tool": "fail", "args": {}}),
            Decision("tool", {"tool": "fail", "args": {}}),
            Decision("complete", {"reason": "done"}),
        ]
        r5 = HarnessRuntime(
            goal=ProbeProfile(ws5, {"fail": fail_tool}).default_goal(),
            profile=ProbeProfile(ws5, {"fail": fail_tool}),
            controller=ScriptedController(script),
            run_dir=root / "failure",
            workspace=ws5,
            progress_policy=ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=2),
            budget=Budget(hard_max_steps=30),
            task_revision="stage6-strategy-failure-v1",
        )
        s5 = r5.run()
        failure_kinds = [f["kind"] for f in s5.failures]
        outcomes["changing_failed_errors_not_progress"] = {
            "passed": s5.completed and s5.progress.progress_events == 0
                      and failure_kinds.count(FailureKind.TOOL_ERROR.value) == 2
                      and FailureKind.NO_PROGRESS.value not in failure_kinds,
            "progress_events": s5.progress.progress_events,
            "failure_kinds": failure_kinds,
        }

        result = {"stage": "06", "probe": "progress-strategy-rc3", "outcomes": outcomes}
        result["summary"] = {
            "all_passed": all(item["passed"] for item in outcomes.values()),
            "scenario_count": len(outcomes),
            "recovery_actor_samples": 0 if outcomes["recovery_not_actor_progress_sample"]["passed"] else 1,
            "failed_output_progress_acceptances": 0 if outcomes["changing_failed_errors_not_progress"]["passed"] else 1,
            "strategy_exhaustion_nonterminal": 0 if outcomes["strategy_exhaustion_terminal_escalate"]["passed"] else 1,
        }
        return result


def main() -> int:
    result = _run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
