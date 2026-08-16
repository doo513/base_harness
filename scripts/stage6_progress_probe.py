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


class ProbeProfile(DomainProfile):
    name = "stage6-progress-probe"

    def __init__(self, workspace: Path, tools=None):
        self.workspace = workspace
        self._tools = dict(tools or {})

    def default_goal(self):
        return GoalContract(goal="stage6 progress probe", acceptance=["probe completes"])

    def tools(self):
        return dict(self._tools)

    def completion_oracle(self):
        def accept(**_):
            return CompletionResult(True, "probe complete")
        return PredicateCompletionOracle(accept, name="stage6-probe-oracle")


def _runtime(root: Path, name: str, profile, controller, policy):
    return HarnessRuntime(
        goal=profile.default_goal(), profile=profile, controller=controller,
        run_dir=root / name, workspace=profile.workspace,
        progress_policy=policy, budget=Budget(hard_max_steps=40),
        task_revision=f"stage6-probe-{name}-v2",
    )


def _run() -> dict:
    with tempfile.TemporaryDirectory(prefix="stage6-progress-") as td:
        root = Path(td)
        outcomes = {}

        ws = root / "changing-workspace"; ws.mkdir()
        counter = {"n": 0}
        def changing():
            counter["n"] += 1
            return {"timestamp_like": counter["n"]}
        tool = ToolSpec(
            name="observe", description="changing observation", handler=changing,
            side_effect=SideEffect.NONE, idempotent=True,
            provenance={"revision": "stage6-probe-v2"},
        )
        profile = ProbeProfile(ws, {"observe": tool})
        runtime = _runtime(
            root, "changing", profile,
            ScriptedController([
                Decision("tool", {"tool": "observe", "args": {}}),
                Decision("tool", {"tool": "observe", "args": {}}),
                Decision("tool", {"tool": "observe", "args": {}}),
                Decision("complete", {"reason": "done"}),
            ]),
            ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=4),
        )
        state = runtime.run()
        no_progress = [f for f in state.failures if f["kind"] == FailureKind.NO_PROGRESS.value]
        outcomes["novel_bytes_are_activity_not_progress"] = {
            "passed": (
                state.completed
                and state.progress.progress_events == 0
                and state.progress.activity_events >= 3
                and len(no_progress) >= 1
            ),
            "progress_events": state.progress.progress_events,
            "activity_events": state.progress.activity_events,
            "no_progress_failures": len(no_progress),
        }

        ws2 = root / "verified-workspace"; ws2.mkdir()
        profile2 = ProbeProfile(ws2)
        decision = Decision("propose", {"key": "x", "value": 1})
        runtime2 = _runtime(root, "verified", profile2, ScriptedController([decision]), ProgressPolicy())
        baseline = runtime2._progress_baseline()
        runtime2.state.commit_verified(Claim(
            "verified.x", 1, status=ClaimStatus.VERIFIED, authority=Authority.SUPPORTED,
        ))
        result = runtime2._evaluate_actor_progress(decision, baseline, allow_trigger=True)
        outcomes["verified_fact_delta_is_epistemic_progress"] = {
            "passed": (
                result["made_progress"]
                and result["max_credit"] == 1.0
                and runtime2.state.progress.progress_events == 1
                and runtime2.state.progress.epistemic_events == 1
            ),
            "max_credit": result["max_credit"],
            "epistemic_events": runtime2.state.progress.epistemic_events,
        }

        ws3 = root / "spec-workspace"; ws3.mkdir()
        profile3 = ProbeProfile(ws3)
        runtime3 = _runtime(
            root, "speculative", profile3,
            ScriptedController([
                Decision("propose", {"key": "guess", "value": "one"}),
                Decision("propose", {"key": "guess", "value": "two"}),
                Decision("complete", {"reason": "done"}),
            ]),
            ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=5),
        )
        state3 = runtime3.run()
        no_progress3 = [f for f in state3.failures if f["kind"] == FailureKind.NO_PROGRESS.value]
        outcomes["speculative_churn_not_progress"] = {
            "passed": state3.completed and state3.progress.progress_events == 0 and len(no_progress3) >= 1,
            "progress_events": state3.progress.progress_events,
            "no_progress_failures": len(no_progress3),
        }

        all_passed = all(item["passed"] for item in outcomes.values())
        return {
            "stage": "06-remediation",
            "probe": "semantic-progress-v2",
            "outcomes": outcomes,
            "summary": {
                "all_passed": all_passed,
                "scenario_count": len(outcomes),
                "activity_novelty_false_progress": 0 if outcomes["novel_bytes_are_activity_not_progress"]["passed"] else 1,
                "verified_delta_missed_progress": 0 if outcomes["verified_fact_delta_is_epistemic_progress"]["passed"] else 1,
            },
        }


def main() -> int:
    result = _run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
