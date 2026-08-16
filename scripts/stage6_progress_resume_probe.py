from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.contracts import GoalContract
from harness.core.controller import Decision, ScriptedController
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.progress import ProgressPolicy
from harness.core.runtime import HarnessRuntime
from harness.core.storage import ResumeConflict
from harness.profiles.base import DomainProfile


class ProbeProfile(DomainProfile):
    name = "stage6-progress-resume"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(goal="stage6 resume probe", acceptance=["probe completes"])

    def completion_oracle(self):
        def accept(**_):
            return CompletionResult(True, "probe complete")
        return PredicateCompletionOracle(accept, name="stage6-resume-oracle")


def _runtime(root, profile, controller, policy, *, resume=False):
    kwargs = dict(
        goal=profile.default_goal(), profile=profile, controller=controller,
        run_dir=root / "run", workspace=profile.workspace,
        progress_policy=policy, budget=Budget(hard_max_steps=30),
        task_revision="stage6-resume-probe-v1",
    )
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)


def _run() -> dict:
    with tempfile.TemporaryDirectory(prefix="stage6-resume-") as td:
        root = Path(td)
        ws = root / "workspace"; ws.mkdir()
        profile = ProbeProfile(ws)
        script = [Decision("propose", {"key": "x", "value": 1})]
        policy = ProgressPolicy(family_repeat_limit=3, no_progress_streak_limit=4)

        runtime = _runtime(root, profile, ScriptedController(script), policy)
        runtime.log("run.start", {"run_id": runtime.run_id})
        runtime.state.progress.no_progress_streak = 2
        runtime.state.progress.last_family_signature = "propose:x"
        runtime.state.progress.family_repeat_count = 2
        runtime.state.progress.evaluations = 9
        runtime._persist_state("manual.progress")

        resumed = _runtime(root, ProbeProfile(ws), ScriptedController(script), policy, resume=True)
        survived = (
            resumed.state.progress.no_progress_streak == 2
            and resumed.state.progress.family_repeat_count == 2
            and resumed.state.progress.evaluations == 9
        )

        drift_blocked = False
        try:
            _runtime(
                root,
                ProbeProfile(ws),
                ScriptedController(script),
                ProgressPolicy(family_repeat_limit=4, no_progress_streak_limit=4),
                resume=True,
            )
        except ResumeConflict:
            drift_blocked = True

        result = {
            "stage": "06",
            "probe": "progress-resume-rc1",
            "outcomes": {
                "progress_state_survives_resume": {
                    "passed": survived,
                    "no_progress_streak": resumed.state.progress.no_progress_streak,
                    "family_repeat_count": resumed.state.progress.family_repeat_count,
                    "evaluations": resumed.state.progress.evaluations,
                },
                "progress_policy_drift_fails_closed": {
                    "passed": drift_blocked,
                },
            },
        }
        result["summary"] = {
            "all_passed": all(item["passed"] for item in result["outcomes"].values()),
            "scenario_count": len(result["outcomes"]),
            "resume_progress_divergence": 0 if survived else 1,
            "policy_drift_acceptances": 0 if drift_blocked else 1,
        }
        return result


def main() -> int:
    result = _run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
