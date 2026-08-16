from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.contracts import GoalContract
from harness.core.controller import Decision
from harness.core.progress import ProgressPolicy
from harness.core.runtime_progress import RuntimeProgressMixin
from harness.core.state import HarnessState
from harness.core.storage import ArtifactStore, IntegrityError
from harness.profiles.base import DomainProfile


class BaseProfile(DomainProfile):
    name = "stage6-task-world-probe"

    def default_goal(self):
        return GoalContract(goal="reach explicit milestone", acceptance=["milestone reached"])


class MilestoneProfile(BaseProfile):
    def task_progress_snapshot(self, *, goal, state):
        return {"accepted": bool(state.completed)}


class MutatingProfile(BaseProfile):
    def task_progress_snapshot(self, *, goal, state):
        state.completed = True
        return {"accepted": True}


class Harness(RuntimeProgressMixin):
    def __init__(self, root: Path, profile):
        self.profile = profile
        self.goal = profile.default_goal()
        self.state = HarnessState()
        self.progress_policy = ProgressPolicy()
        self.metrics = {"progress_evaluations": 0, "progress_events": 0}
        self.artifacts = ArtifactStore(root / "artifacts")
        self.events = []
        self.failures = []

    def log(self, kind, payload):
        self.events.append((kind, payload))

    def fail(self, failure):
        self.failures.append(failure)


def main() -> int:
    outcomes = {}
    with tempfile.TemporaryDirectory(prefix="vsh-stage6-task-") as tmp:
        root = Path(tmp)

        explicit = Harness(root / "explicit", MilestoneProfile())
        baseline = explicit._progress_baseline()
        explicit.state.completed = True
        result = explicit._evaluate_actor_progress(
            Decision("complete", {"reason": "milestone"}), baseline, allow_trigger=True
        )
        outcomes["profile_explicit_delta_is_task_progress"] = {
            "passed": result["made_progress"]
            and explicit.state.progress.task_events == 1
            and "profile_task_progress_snapshot_changed" in result["progress_reasons"],
            "task_events": explicit.state.progress.task_events,
            "progress_events": explicit.state.progress.progress_events,
        }

        default = Harness(root / "default", BaseProfile())
        baseline = default._progress_baseline()
        default.state.completed = True
        result = default._evaluate_actor_progress(
            Decision("complete", {"reason": "no profile authority"}), baseline, allow_trigger=False
        )
        outcomes["default_profile_has_no_task_authority"] = {
            "passed": default.state.progress.task_events == 0
            and all(signal["kind"] != "task" for signal in result["progress_signals"]),
            "task_events": default.state.progress.task_events,
        }

        mutating = Harness(root / "mutating", MutatingProfile())
        mutation_blocked = False
        try:
            mutating._progress_baseline()
        except IntegrityError:
            mutation_blocked = True
        outcomes["snapshot_hook_must_be_pure"] = {
            "passed": mutation_blocked,
        }

    summary = {
        "all_passed": all(item["passed"] for item in outcomes.values()),
        "scenario_count": len(outcomes),
        "implicit_task_authority": 0 if outcomes["default_profile_has_no_task_authority"]["passed"] else 1,
        "snapshot_state_mutations_accepted": 0 if outcomes["snapshot_hook_must_be_pure"]["passed"] else 1,
    }
    print(json.dumps({
        "stage": "06-remediation",
        "probe": "task-world-progress-v1",
        "outcomes": outcomes,
        "summary": summary,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
