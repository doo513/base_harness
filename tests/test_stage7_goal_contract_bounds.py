from __future__ import annotations

import pytest

from harness.core.contracts import GoalContract


def test_valid_goal_contract_remains_exact():
    goal = GoalContract(
        goal="ship verified feature",
        acceptance=["oracle accepts"],
        constraints=["do not mutate truth directly"],
        pinned_constraints=["retrieval has no authority"],
        task_id="bounded-goal",
    )
    assert goal.goal == "ship verified feature"
    assert goal.acceptance == ["oracle accepts"]
    assert goal.constraints == ["do not mutate truth directly"]
    assert goal.pinned_constraints == ["retrieval has no authority"]


def test_oversized_goal_fails_closed_without_truncation():
    with pytest.raises(ValueError, match="goal exceeds max chars"):
        GoalContract(
            goal="g" * (GoalContract.MAX_GOAL_CHARS + 1),
            acceptance=["oracle accepts"],
        )


def test_oversized_criterion_fails_closed():
    with pytest.raises(ValueError, match=r"acceptance\[0\] exceeds max chars"):
        GoalContract(
            goal="bounded",
            acceptance=["a" * (GoalContract.MAX_CRITERION_CHARS + 1)],
        )


def test_criteria_count_is_bounded():
    with pytest.raises(ValueError, match="acceptance exceeds max items"):
        GoalContract(
            goal="bounded",
            acceptance=["ok"] * (GoalContract.MAX_CRITERIA_ITEMS + 1),
        )


def test_total_mandatory_text_is_bounded():
    item = "x" * GoalContract.MAX_CRITERION_CHARS
    with pytest.raises(ValueError, match="mandatory goal/control text exceeds total bound"):
        GoalContract(
            goal="g" * GoalContract.MAX_GOAL_CHARS,
            acceptance=[item] * 4,
            constraints=[item] * 4,
            pinned_constraints=[item] * 5,
        )


def test_goal_limit_policy_is_explicit_and_versioned():
    descriptor = GoalContract.limits_descriptor()
    assert descriptor["schema_version"] == "goal-contract-limits-v1"
    assert descriptor["overflow_mode"] == "fail_closed_before_run_creation"
    assert descriptor["max_goal_chars"] == GoalContract.MAX_GOAL_CHARS
