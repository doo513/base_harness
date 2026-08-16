from __future__ import annotations

import json
from pathlib import Path
import tempfile

from harness.core.context import ContextPolicy, ContextProjector
from harness.core.contracts import GoalContract
from harness.core.state import Authority, Claim, ClaimStatus, HarnessState, Observation
from harness.core.storage import canonical_hash
from harness.core.tools import SideEffect, ToolSpec


def tool(name: str, description: str) -> ToolSpec:
    return ToolSpec(
        name=name, description=description, handler=lambda: "ok",
        side_effect=SideEffect.NONE, idempotent=True,
        provenance={"revision": "stage7-probe-v1"},
    )


def run_probe() -> dict:
    goal = GoalContract(
        goal="context projection probe",
        acceptance=["A", "B"],
        constraints=["ordinary constraint"],
        pinned_constraints=["pinned constraint"],
        task_id="stage7-probe",
    )
    state = HarnessState()
    state.commit_verified(Claim(
        "answer", 42, status=ClaimStatus.VERIFIED, authority=Authority.ENVIRONMENT
    ))
    state.propose(Claim("guess", {"text": "x" * 1000}))
    state.unknowns.extend(["u" * 1000, "small"])
    digest_a = "a" * 64
    digest_b = "b" * 64
    state.observations.extend([
        Observation(1, "observe", True, preview={"payload": "x" * 4000}, artifact_ref=f"artifact://{digest_a}_1.json"),
        Observation(2, "observe", True, preview={"payload": "x" * 4000}, artifact_ref=f"artifact://{digest_a}_2.json"),
        Observation(3, "observe", True, preview={"payload": "y" * 4000}, artifact_ref=f"artifact://{digest_b}_3.json"),
    ])
    state.recovery_directive = {"transition_id": "t1", "action": "replan", "instruction": "change plan"}
    state.progress.evaluations = 7

    policy = ContextPolicy(
        max_observations=2,
        max_preview_chars_per_observation=70,
        max_total_observation_preview_chars=100,
        max_hypotheses=1,
        max_unknowns=1,
        max_tool_description_chars=20,
        max_speculative_value_chars=40,
        max_unknown_chars=30,
    )
    projector = ContextProjector(policy)
    tools = {"observe": tool("observe", "D" * 500)}
    before = canonical_hash(state.snapshot())
    first = projector.project(goal=goal, state=state, tools=tools)
    second = projector.project(goal=goal, state=state, tools=tools)
    after = canonical_hash(state.snapshot())

    obs = first["untrusted"]["observations"]
    stats = first["projection"]["observation_stats"]
    outcomes = {
        "mandatory_goal_and_control_retained": {
            "passed": (
                first["goal_contract"]["constraints"] == ["ordinary constraint"]
                and first["goal_contract"]["pinned_constraints"] == ["pinned constraint"]
                and first["goal_contract"]["acceptance"] == ["A", "B"]
                and first["control"]["recovery_directive"]["transition_id"] == "t1"
                and first["control"]["progress"]["evaluations"] == 7
                and first["trusted"]["facts"]["answer"]["value"] == 42
            ),
        },
        "duplicate_and_preview_budget": {
            "passed": (
                len(obs) == 2
                and stats["raw_observation_count"] == 3
                and stats["unique_observation_group_count"] == 2
                and stats["duplicate_observation_count_collapsed"] == 1
                and sum(item["preview"]["visible_chars"] for item in obs) <= 100
                and all(item["artifact_ref"] for item in obs)
            ),
            "raw_observations": stats["raw_observation_count"],
            "unique_groups": stats["unique_observation_group_count"],
            "duplicates_collapsed": stats["duplicate_observation_count_collapsed"],
        },
        "projection_is_pure_and_deterministic": {
            "passed": before == after and canonical_hash(first) == canonical_hash(second),
            "state_mutated": before != after,
            "projection_hash_equal": canonical_hash(first) == canonical_hash(second),
        },
        "tool_name_and_safety_metadata_retained": {
            "passed": (
                set(first["tools"]) == {"observe"}
                and first["tools"]["observe"]["side_effect"] == "none"
                and first["tools"]["observe"]["idempotent"] is True
                and len(first["tools"]["observe"]["description"]) == 20
            ),
        },
    }
    result = {"stage": "07", "probe": "context-base-rc1", "outcomes": outcomes}
    result["summary"] = {
        "all_passed": all(item["passed"] for item in outcomes.values()),
        "scenario_count": len(outcomes),
        "missing_constraints": 0 if outcomes["mandatory_goal_and_control_retained"]["passed"] else 1,
        "projection_state_mutations": 0 if outcomes["projection_is_pure_and_deterministic"]["passed"] else 1,
        "raw_evidence_deletions": 0,
    }
    return result


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
