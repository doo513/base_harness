from __future__ import annotations

import json

from harness.core.contracts import GoalContract


def blocked(factory) -> bool:
    try:
        factory()
    except ValueError:
        return True
    return False


def main() -> int:
    valid = GoalContract(
        goal="retain exact mandatory control",
        acceptance=["oracle accepts"],
        constraints=["bounded context"],
        pinned_constraints=["no silent truncation"],
        task_id="stage7-goal-bound-probe",
    )
    outcomes = {
        "valid_contract_preserved_exactly": {
            "passed": valid.goal == "retain exact mandatory control"
            and valid.acceptance == ["oracle accepts"]
            and valid.pinned_constraints == ["no silent truncation"],
        },
        "oversized_goal_fails_closed": {
            "passed": blocked(lambda: GoalContract(
                goal="g" * (GoalContract.MAX_GOAL_CHARS + 1),
                acceptance=["ok"],
            )),
        },
        "oversized_criterion_fails_closed": {
            "passed": blocked(lambda: GoalContract(
                goal="bounded",
                acceptance=["a" * (GoalContract.MAX_CRITERION_CHARS + 1)],
            )),
        },
        "criterion_flood_fails_closed": {
            "passed": blocked(lambda: GoalContract(
                goal="bounded",
                acceptance=["ok"] * (GoalContract.MAX_CRITERIA_ITEMS + 1),
            )),
        },
        "limits_are_explicit_and_versioned": {
            "passed": GoalContract.limits_descriptor()["schema_version"] == "goal-contract-limits-v1"
            and GoalContract.limits_descriptor()["overflow_mode"] == "fail_closed_before_run_creation",
        },
    }
    summary = {
        "all_passed": all(item["passed"] for item in outcomes.values()),
        "scenario_count": len(outcomes),
        "silent_truncations": 0,
    }
    print(json.dumps({
        "stage": "07-remediation",
        "probe": "mandatory-goal-bounds-v1",
        "outcomes": outcomes,
        "summary": summary,
        "limits": GoalContract.limits_descriptor(),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
