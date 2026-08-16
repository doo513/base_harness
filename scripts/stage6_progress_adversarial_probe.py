from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision, ScriptedController
from harness.core.failures import FailureKind
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.progress import ProgressPolicy, decision_progress_signatures
from harness.core.runtime import HarnessRuntime
from harness.core.storage import IntegrityError
from harness.core.tools import SideEffect, ToolSpec
from harness.profiles.base import DomainProfile


class ProbeProfile(DomainProfile):
    name = "stage6-progress-adversarial"

    def __init__(self, workspace: Path, tools=None):
        self.workspace = workspace
        self._tools = dict(tools or {})

    def default_goal(self):
        return GoalContract(goal="stage6 adversarial probe", acceptance=["probe completes"])

    def tools(self):
        return dict(self._tools)

    def completion_oracle(self):
        def accept(**_):
            return CompletionResult(True, "probe complete")
        return PredicateCompletionOracle(accept, name="stage6-adversarial-oracle")


def _runtime(root, name, profile, controller, policy=None):
    return HarnessRuntime(
        goal=profile.default_goal(), profile=profile, controller=controller,
        run_dir=root / name, workspace=profile.workspace,
        progress_policy=policy or ProgressPolicy(),
        budget=Budget(hard_max_steps=30), task_revision=f"stage6-adv-{name}-v1",
    )


def _run() -> dict:
    with tempfile.TemporaryDirectory(prefix="stage6-adv-") as td:
        root = Path(td)
        outcomes = {}

        a = Decision("tool", {"tool": "observe", "args": {"q": "  alpha   beta ", "n": 7}})
        b = Decision("tool", {"args": {"n": 7, "q": "alpha beta"}, "tool": "observe"})
        ca = Decision("complete", {"reason": "first reason"})
        cb = Decision("complete", {"reason": "totally different reason"})
        outcomes["cosmetic_identity_evasion_blocked"] = {
            "passed": decision_progress_signatures(a) == decision_progress_signatures(b),
            "tool_same": decision_progress_signatures(a) == decision_progress_signatures(b),
            "complete_same": decision_progress_signatures(ca) == decision_progress_signatures(cb),
        }
        outcomes["cosmetic_identity_evasion_blocked"]["passed"] = (
            outcomes["cosmetic_identity_evasion_blocked"]["tool_same"]
            and outcomes["cosmetic_identity_evasion_blocked"]["complete_same"]
        )

        ws = root / "specific-workspace"; ws.mkdir()
        def failer():
            raise RuntimeError("specific failure 500")
        fail_tool = ToolSpec(
            name="fail", description="specific failure", handler=failer,
            side_effect=SideEffect.NONE, idempotent=True,
            provenance={"revision": "stage6-adv-v1"},
        )
        profile = ProbeProfile(ws, {"fail": fail_tool})
        runtime = _runtime(
            root, "specific", profile,
            ScriptedController([
                Decision("tool", {"tool": "fail", "args": {}}),
                Decision("complete", {"reason": "done"}),
            ]),
            ProgressPolicy(family_repeat_limit=2, no_progress_streak_limit=2),
        )
        state = runtime.run()
        kinds = [f["kind"] for f in state.failures]
        outcomes["specific_failure_precedence"] = {
            "passed": (
                state.completed
                and kinds.count(FailureKind.TOOL_ERROR.value) == 1
                and FailureKind.NO_PROGRESS.value not in kinds
            ),
            "failure_kinds": kinds,
        }

        ws2 = root / "tamper-workspace"; ws2.mkdir()
        tool2 = ToolSpec(
            name="observe", description="tamper target", handler=lambda: "ORIGINAL",
            side_effect=SideEffect.NONE, idempotent=True,
            provenance={"revision": "stage6-adv-v1"},
        )
        decision = Decision("tool", {"tool": "observe", "args": {}})
        profile2 = ProbeProfile(ws2, {"observe": tool2})
        runtime2 = _runtime(root, "tamper", profile2, ScriptedController([decision]))
        runtime2.log("run.start", {"run_id": runtime2.run_id})
        runtime2._persist_state("manual.start")
        baseline = runtime2._progress_baseline()
        runtime2._dispatch_decision(decision)
        ref = runtime2.state.observations[-1].artifact_ref
        runtime2.artifacts.resolve(ref).write_text("TAMPERED", encoding="utf-8")
        blocked = False
        try:
            runtime2._evaluate_actor_progress(decision, baseline, allow_trigger=True)
        except IntegrityError:
            blocked = True
        outcomes["tampered_artifact_not_progress"] = {
            "passed": blocked and runtime2.state.progress.progress_events == 0,
            "integrity_blocked": blocked,
            "progress_events": runtime2.state.progress.progress_events,
        }

        all_passed = all(item["passed"] for item in outcomes.values())
        return {
            "stage": "06",
            "probe": "progress-adversarial-rc1",
            "outcomes": outcomes,
            "summary": {
                "all_passed": all_passed,
                "scenario_count": len(outcomes),
                "cosmetic_evasions": 0 if outcomes["cosmetic_identity_evasion_blocked"]["passed"] else 1,
                "specific_failure_supersessions": 0 if outcomes["specific_failure_precedence"]["passed"] else 1,
                "tamper_progress_acceptances": 0 if outcomes["tampered_artifact_not_progress"]["passed"] else 1,
            },
        }


def main() -> int:
    result = _run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
