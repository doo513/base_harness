from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness.core.budget import Budget
from harness.core.context import ContextPolicy
from harness.core.contracts import GoalContract
from harness.core.controller import Decision, ScriptedController
from harness.core.oracles import CompletionResult, PredicateCompletionOracle
from harness.core.runtime import HarnessRuntime
from harness.core.state import Authority, Claim, ClaimStatus, Observation
from harness.core.storage import ResumeConflict, canonical_hash
from harness.profiles.base import DomainProfile


class Profile(DomainProfile):
    name = "stage7-context-resume"

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def default_goal(self):
        return GoalContract(
            goal="stage7 resume projection",
            acceptance=["deterministic"],
            constraints=["ordinary"],
            pinned_constraints=["pinned"],
            task_id="stage7-resume",
        )

    def completion_oracle(self):
        return PredicateCompletionOracle(
            lambda **_: CompletionResult(True, "done"), name="stage7-resume-oracle"
        )


def make_runtime(root: Path, profile: Profile, controller, policy, *, resume=False):
    kwargs = dict(
        goal=profile.default_goal(), profile=profile, controller=controller,
        run_dir=root / "run", workspace=profile.workspace,
        context_policy=policy, budget=Budget(hard_max_steps=30),
        task_revision="stage7-resume-v1",
    )
    return HarnessRuntime.resume(**kwargs) if resume else HarnessRuntime(**kwargs)


def run_probe() -> dict:
    with tempfile.TemporaryDirectory(prefix="stage7-context-resume-") as td:
        root = Path(td)
        ws = root / "workspace"; ws.mkdir()
        profile = Profile(ws)
        script = [Decision("complete", {"reason": "done"})]
        policy = ContextPolicy(
            max_observations=2,
            max_preview_chars_per_observation=50,
            max_total_observation_preview_chars=70,
            max_hypotheses=2,
        )
        runtime = make_runtime(root, profile, ScriptedController(script), policy)
        runtime.state.commit_verified(Claim(
            "fact", "value", status=ClaimStatus.VERIFIED, authority=Authority.ENVIRONMENT
        ))
        runtime.state.observations.extend([
            Observation(1, "observe", True, preview="same", artifact_ref=f"artifact://{'a'*64}_one.json"),
            Observation(2, "observe", True, preview="same", artifact_ref=f"artifact://{'a'*64}_two.json"),
        ])
        runtime.state.propose(Claim("guess", "maybe"))
        runtime.log("run.start", {"run_id": runtime.run_id})
        runtime._persist_state("stage7.resume.seed")
        projection_before = runtime._context()
        state_hash_before = canonical_hash(runtime.state.snapshot())

        resumed = make_runtime(root, Profile(ws), ScriptedController(script), policy, resume=True)
        projection_after = resumed._context()
        state_hash_after_projection = canonical_hash(resumed.state.snapshot())
        same_projection = canonical_hash(projection_before) == canonical_hash(projection_after)
        no_mutation = state_hash_before == state_hash_after_projection

        drift_blocked = False
        try:
            make_runtime(
                root, Profile(ws), ScriptedController(script),
                ContextPolicy(
                    max_observations=3,
                    max_preview_chars_per_observation=50,
                    max_total_observation_preview_chars=70,
                    max_hypotheses=2,
                ),
                resume=True,
            )
        except ResumeConflict:
            drift_blocked = True

        outcomes = {
            "same_state_same_policy_same_projection_after_resume": {
                "passed": same_projection,
                "projection_hash_before": canonical_hash(projection_before),
                "projection_hash_after": canonical_hash(projection_after),
            },
            "projection_does_not_mutate_resumed_state": {
                "passed": no_mutation,
                "state_hash_before": state_hash_before,
                "state_hash_after_projection": state_hash_after_projection,
            },
            "context_policy_drift_fails_closed": {
                "passed": drift_blocked,
            },
        }
        result = {"stage": "07", "probe": "context-resume-rc1", "outcomes": outcomes}
        result["summary"] = {
            "all_passed": all(item["passed"] for item in outcomes.values()),
            "scenario_count": len(outcomes),
            "projection_resume_divergence": 0 if same_projection else 1,
            "projection_state_mutations": 0 if no_mutation else 1,
            "policy_drift_acceptances": 0 if drift_blocked else 1,
        }
        return result


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
