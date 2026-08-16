from __future__ import annotations

import json
import tempfile
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
    name = "stage6-boundary-probe"

    def __init__(self, workspace: Path, tools=None):
        self.workspace = workspace
        self._tools = dict(tools or {})

    def default_goal(self):
        return GoalContract(goal="stage6 boundary probe", acceptance=["done"])

    def tools(self): return dict(self._tools)

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "done"), name="stage6-boundary-oracle"
        )


def runtime(root, name, profile, controller, policy=None):
    return HarnessRuntime(
        goal=profile.default_goal(), profile=profile, controller=controller,
        run_dir=root / name, workspace=profile.workspace,
        progress_policy=policy or ProgressPolicy(), budget=Budget(hard_max_steps=60),
        task_revision=f"stage6-boundary-{name}",
    )


def run_probe() -> dict:
    with tempfile.TemporaryDirectory(prefix="stage6-boundary-") as td:
        root = Path(td)
        outcomes = {}

        ws = root / "facts-ws"; ws.mkdir()
        r = runtime(root, "facts", Profile(ws), ScriptedController([]))
        r.state.commit_verified(Claim(
            "answer", "alpha   beta", status=ClaimStatus.VERIFIED,
            authority=Authority.ENVIRONMENT, evidence_refs=["artifact://one"],
        ))
        h1 = r._progress_facts_hash()
        r.state.commit_verified(Claim(
            "answer", "alpha beta", status=ClaimStatus.VERIFIED,
            authority=Authority.ENVIRONMENT, evidence_refs=["artifact://two"],
        ))
        h2 = r._progress_facts_hash()
        outcomes["fact_metadata_churn_not_progress"] = {
            "passed": h1 == h2,
            "hash_equal": h1 == h2,
        }

        ws2 = root / "global-ws"; ws2.mkdir()
        decisions = [Decision("propose", {"key": k, "value": k}) for k in "abcdef"]
        decisions.append(Decision("complete", {"reason": "done"}))
        r2 = runtime(
            root, "global", Profile(ws2), ScriptedController(decisions),
            ProgressPolicy(family_repeat_limit=10, no_progress_streak_limit=2,
                           max_strategy_generations_without_progress=5),
        )
        s2 = r2.run()
        failures = [
            f for f in s2.failures
            if f["kind"] == FailureKind.NO_PROGRESS.value
            and f["target"] == "stage6:global_no_progress"
        ]
        actions = [x.action.value for x in s2.recovery_history[:3]]
        outcomes["global_repeat_identity_stable"] = {
            "passed": [f["repeat_count"] for f in failures] == [1, 2, 3]
                      and actions == ["replan", "replan", "switch_strategy"],
            "repeat_counts": [f["repeat_count"] for f in failures],
            "actions": actions,
        }

        ws3 = root / "tamper-ws"; ws3.mkdir()
        tool = ToolSpec(
            name="observe", description="read", handler=lambda: {"stable": True},
            side_effect=SideEffect.NONE, idempotent=True,
            provenance={"revision": "stage6-boundary"},
        )
        controller = ScriptedController([
            Decision("tool", {"tool": "observe", "args": {}}),
            Decision("complete", {"reason": "must-not-run"}),
        ])
        r3 = runtime(root, "tamper", Profile(ws3, {"observe": tool}), controller)
        r3.log("run.start", {"run_id": r3.run_id}); r3._persist_state("manual.start")
        r3.step_once(); r3.state.step += 1; r3._persist_state("manual.first")
        ref = r3.state.observations[-1].artifact_ref
        r3.artifacts.resolve(ref).write_text("tampered", encoding="utf-8")
        r3.step_once()
        terminal_scheduled = (
            controller.index == 1 and r3.state.pending_recovery is not None
            and r3.state.pending_recovery.failure_kind == FailureKind.PERSISTENCE_ERROR
        )
        r3.step_once()
        outcomes["historical_tamper_terminalized_before_actor"] = {
            "passed": terminal_scheduled and r3.halted
                      and r3.state.recovery_history[-1].action == RecoveryAction.CHECKPOINT_STOP,
            "actor_cursor": controller.index,
            "terminal_scheduled": terminal_scheduled,
            "halted": r3.halted,
        }

        result = {"stage": "06", "probe": "progress-boundary-rc2", "outcomes": outcomes}
        result["summary"] = {
            "all_passed": all(v["passed"] for v in outcomes.values()),
            "scenario_count": len(outcomes),
            "historical_tamper_actor_calls": 0 if outcomes["historical_tamper_terminalized_before_actor"]["passed"] else 1,
            "global_repeat_identity_divergence": 0 if outcomes["global_repeat_identity_stable"]["passed"] else 1,
            "fact_metadata_false_progress": 0 if outcomes["fact_metadata_churn_not_progress"]["passed"] else 1,
        }
        return result


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
