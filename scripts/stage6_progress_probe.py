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
        task_revision=f"stage6-probe-{name}-v1",
    )


def _run() -> dict:
    with tempfile.TemporaryDirectory(prefix="stage6-progress-") as td:
        root = Path(td)
        outcomes = {}

        ws = root / "duplicate-workspace"; ws.mkdir()
        tool = ToolSpec(
            name="observe", description="constant observation", handler=lambda: "SAME",
            side_effect=SideEffect.NONE, idempotent=True,
            provenance={"revision": "stage6-probe-v1"},
        )
        profile = ProbeProfile(ws, {"observe": tool})
        controller = ScriptedController([
            Decision("tool", {"tool": "observe", "args": {}}),
            Decision("tool", {"tool": "observe", "args": {}}),
            Decision("tool", {"tool": "observe", "args": {}}),
            Decision("complete", {"reason": "done"}),
        ])
        runtime = _runtime(
            root, "duplicate", profile, controller,
            ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=5),
        )
        state = runtime.run()
        successful = [o for o in state.observations if o.ok]
        digests = {
            o.artifact_ref[len("artifact://"):len("artifact://") + 64]
            for o in successful
        }
        no_progress = [f for f in state.failures if f["kind"] == FailureKind.NO_PROGRESS.value]
        outcomes["duplicate_successful_bytes_bounded"] = {
            "passed": (
                state.completed and state.progress.progress_events == 1
                and len(successful) == 3 and len(digests) == 1
                and len(no_progress) == 1
                and any(x.action == RecoveryAction.REPLAN for x in state.recovery_history)
            ),
            "progress_events": state.progress.progress_events,
            "successful_observations": len(successful),
            "unique_content_digests": len(digests),
            "no_progress_failures": len(no_progress),
        }

        ws2 = root / "spec-workspace"; ws2.mkdir()
        profile2 = ProbeProfile(ws2)
        controller2 = ScriptedController([
            Decision("propose", {"key": "guess", "value": "one"}),
            Decision("propose", {"key": "guess", "value": "two"}),
            Decision("complete", {"reason": "done"}),
        ])
        runtime2 = _runtime(
            root, "speculative", profile2, controller2,
            ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=5),
        )
        state2 = runtime2.run()
        no_progress2 = [f for f in state2.failures if f["kind"] == FailureKind.NO_PROGRESS.value]
        outcomes["actor_speculative_churn_not_progress"] = {
            "passed": state2.completed and state2.progress.progress_events == 0 and len(no_progress2) == 1,
            "progress_events": state2.progress.progress_events,
            "no_progress_failures": len(no_progress2),
        }

        ws3 = root / "novel-workspace"; ws3.mkdir()
        counter = {"n": 0}
        def changing():
            counter["n"] += 1
            return {"n": counter["n"]}
        tool3 = ToolSpec(
            name="observe", description="changing observation", handler=changing,
            side_effect=SideEffect.NONE, idempotent=True,
            provenance={"revision": "stage6-probe-v1"},
        )
        profile3 = ProbeProfile(ws3, {"observe": tool3})
        controller3 = ScriptedController([
            Decision("tool", {"tool": "observe", "args": {}}),
            Decision("tool", {"tool": "observe", "args": {}}),
            Decision("tool", {"tool": "observe", "args": {}}),
            Decision("complete", {"reason": "done"}),
        ])
        runtime3 = _runtime(
            root, "novel", profile3, controller3,
            ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=2),
        )
        state3 = runtime3.run()
        outcomes["novel_successful_bytes_continue"] = {
            "passed": (
                state3.completed and state3.progress.progress_events == 3
                and not any(f["kind"] == FailureKind.NO_PROGRESS.value for f in state3.failures)
            ),
            "progress_events": state3.progress.progress_events,
        }

        all_passed = all(item["passed"] for item in outcomes.values())
        return {
            "stage": "06",
            "probe": "progress-base-rc1",
            "outcomes": outcomes,
            "summary": {
                "all_passed": all_passed,
                "scenario_count": len(outcomes),
                "actor_self_progress_acceptances": 0,
            },
        }


def main() -> int:
    result = _run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
