from __future__ import annotations

import json

from harness.core.context import ContextPolicy, ContextProjector
from harness.core.contracts import GoalContract
from harness.core.state import Authority, Claim, ClaimStatus, HarnessState
from harness.core.storage import canonical_hash


def run_probe() -> dict:
    goal = GoalContract(
        goal="trusted context bound probe",
        acceptance=["A"],
        constraints=["C"],
        pinned_constraints=["PIN"],
    )
    state = HarnessState()
    for i in range(150):
        state.commit_verified(Claim(
            f"fact.{i:03d}",
            {"payload": "X" * 4000, "i": i},
            status=ClaimStatus.VERIFIED,
            authority=Authority.SUPPORTED,
        ))
    state.commit_verified(Claim(
        "critical.environment", 7,
        status=ClaimStatus.VERIFIED,
        authority=Authority.ENVIRONMENT,
    ))
    before = canonical_hash(state.snapshot())
    policy = ContextPolicy(
        max_verified_facts=6,
        max_verified_value_chars=60,
        max_total_verified_value_chars=180,
    )
    context = ContextProjector(policy).project(goal=goal, state=state, tools={})
    after = canonical_hash(state.snapshot())
    facts = context["trusted"]["facts"]
    stats = context["projection"]["fact_stats"]
    serialized = json.dumps(context, ensure_ascii=False, sort_keys=True)

    outcomes = {
        "verified_fact_count_bounded": {
            "passed": len(facts) == 6 and stats["omitted_current_fact_count"] == 145,
            "selected": len(facts),
            "omitted": stats["omitted_current_fact_count"],
        },
        "verified_value_preview_bounded": {
            "passed": stats["visible_verified_value_chars"] <= 180,
            "visible_chars": stats["visible_verified_value_chars"],
        },
        "stronger_authority_retained_first": {
            "passed": "critical.environment" in facts and facts["critical.environment"]["value"] == 7,
        },
        "mandatory_goal_retained": {
            "passed": context["goal_contract"]["pinned_constraints"] == ["PIN"],
        },
        "durable_truth_unchanged": {
            "passed": before == after and len(state.facts) == 151,
            "state_mutated": before != after,
        },
    }
    result = {
        "stage": "07-remediation",
        "probe": "trusted-context-growth-v2",
        "outcomes": outcomes,
        "metrics": {
            "serialized_context_chars": len(serialized),
            "durable_fact_count": len(state.facts),
        },
    }
    result["summary"] = {
        "all_passed": all(item["passed"] for item in outcomes.values()),
        "scenario_count": len(outcomes),
        "mandatory_goal_drops": 0 if outcomes["mandatory_goal_retained"]["passed"] else 1,
        "durable_fact_deletions": 0 if outcomes["durable_truth_unchanged"]["passed"] else 1,
    }
    return result


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
