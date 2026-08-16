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
from harness.core.storage import ResumeConflict
from harness.profiles.base import DomainProfile


class ProbeProfile(DomainProfile):
    name = "stage6-progress-resume"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(goal="stage6 resume probe", acceptance=["probe completes"])

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "probe complete"),
            name="stage6-resume-oracle",
        )


def _runtime(root, profile, controller, policy, *, resume=False):
    kwargs = dict(
        goal=profile.default_goal(),
        profile=profile,
        controller=controller,
        run_dir=root / "run",
        workspace=profile.workspace,
        progress_policy=policy,
        budget=Budget(hard_max_steps=40),
        task_revision="stage6-resume-probe-v2",
    )
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)


def _run() -> dict:
    with tempfile.TemporaryDirectory(prefix="stage6-resume-") as td:
        root = Path(td)
        ws = root / "workspace"
        ws.mkdir()
        policy = ProgressPolicy(
            family_repeat_limit=3,
            no_progress_streak_limit=8,
            max_strategy_generations_without_progress=4,
        )
        script = [
            Decision("propose", {"key": "x", "value": 1}),
            Decision("propose", {"key": "x", "value": 2}),
            Decision("propose", {"key": "x", "value": 3}),
            Decision("complete", {"reason": "probe done"}),
        ]

        runtime = _runtime(root, ProbeProfile(ws), ScriptedController(script), policy)
        runtime.log("run.start", {"run_id": runtime.run_id})
        runtime._persist_state("probe.start")

        # Execute exactly one Actor decision and persist the same transition
        # boundary used by the normal outer loop.
        first_is_recovery = runtime.step_once()
        if not first_is_recovery:
            runtime.state.step += 1
        runtime._persist_state("probe.partial-actor-step")
        runtime._save_metrics()

        pre_resume = {
            "controller_index": runtime.controller.index,
            "step": runtime.state.step,
            "family_repeat_count": runtime.state.progress.family_repeat_count,
            "no_progress_streak": runtime.state.progress.no_progress_streak,
            "evaluations": runtime.state.progress.evaluations,
        }

        resumed_controller = ScriptedController(script)
        resumed = _runtime(root, ProbeProfile(ws), resumed_controller, policy, resume=True)
        restored = {
            "controller_index": resumed_controller.index,
            "step": resumed.state.step,
            "family_repeat_count": resumed.state.progress.family_repeat_count,
            "no_progress_streak": resumed.state.progress.no_progress_streak,
            "evaluations": resumed.state.progress.evaluations,
        }
        restoration_exact = restored == pre_resume

        final = resumed.run()
        no_progress = [f for f in final.failures if f["kind"] == FailureKind.NO_PROGRESS.value]
        replan_count = sum(1 for item in final.recovery_history if item.action == RecoveryAction.REPLAN)
        continuation_deterministic = (
            final.completed
            and resumed_controller.index == len(script)
            and len(no_progress) == 1
            and no_progress[0]["repeat_count"] == 1
            and replan_count >= 1
        )

        drift_blocked = False
        try:
            _runtime(
                root,
                ProbeProfile(ws),
                ScriptedController(script),
                ProgressPolicy(
                    family_repeat_limit=4,
                    no_progress_streak_limit=8,
                    max_strategy_generations_without_progress=4,
                ),
                resume=True,
            )
        except ResumeConflict:
            drift_blocked = True

        result = {
            "stage": "06",
            "probe": "progress-resume-rc3",
            "outcomes": {
                "checkpointed_progress_and_controller_state_restore_exactly": {
                    "passed": restoration_exact,
                    "before": pre_resume,
                    "after": restored,
                },
                "resumed_window_reaches_same_no_progress_threshold": {
                    "passed": continuation_deterministic,
                    "completed": final.completed,
                    "controller_index": resumed_controller.index,
                    "no_progress_failures": len(no_progress),
                    "replan_count": replan_count,
                },
                "progress_policy_drift_fails_closed": {
                    "passed": drift_blocked,
                },
            },
        }
        result["summary"] = {
            "all_passed": all(item["passed"] for item in result["outcomes"].values()),
            "scenario_count": len(result["outcomes"]),
            "resume_progress_divergence": 0 if restoration_exact and continuation_deterministic else 1,
            "policy_drift_acceptances": 0 if drift_blocked else 1,
        }
        return result


def main() -> int:
    result = _run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
