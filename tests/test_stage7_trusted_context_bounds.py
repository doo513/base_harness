from pathlib import Path

from harness.core.context import ContextPolicy, ContextProjector
from harness.core.contracts import GoalContract
from harness.core.state import Authority, Claim, ClaimStatus, HarnessState
from harness.core.storage import canonical_hash


def goal():
    return GoalContract(
        goal="preserve mandatory goal",
        acceptance=["A"],
        constraints=["C"],
        pinned_constraints=["PIN"],
    )


def verified(key, value, authority=Authority.SUPPORTED):
    return Claim(key, value, status=ClaimStatus.VERIFIED, authority=authority)


def test_large_verified_state_is_bounded_without_mutating_truth():
    state = HarnessState()
    for i in range(200):
        state.commit_verified(verified(f"fact.{i:03d}", {"payload": "X" * 5000}))
    before = canonical_hash(state.snapshot())
    policy = ContextPolicy(
        max_verified_facts=5,
        max_verified_value_chars=50,
        max_total_verified_value_chars=120,
    )
    context = ContextProjector(policy).project(goal=goal(), state=state, tools={})
    after = canonical_hash(state.snapshot())

    facts = context["trusted"]["facts"]
    stats = context["projection"]["fact_stats"]
    assert len(facts) == 5
    assert stats["raw_current_fact_count"] == 200
    assert stats["omitted_current_fact_count"] == 195
    assert stats["visible_verified_value_chars"] <= 120
    assert sum(item["value_preview"]["visible_chars"] for item in facts.values()) <= 120
    assert all(item["value"] is None for item in facts.values())
    assert all(item["value_preview"]["truncated"] for item in facts.values())
    assert context["goal_contract"]["goal"] == "preserve mandatory goal"
    assert context["goal_contract"]["pinned_constraints"] == ["PIN"]
    assert before == after


def test_verified_fact_selection_prefers_stronger_authority_deterministically():
    state = HarnessState()
    state.commit_verified(verified("z.supported", 1, Authority.SUPPORTED))
    state.commit_verified(verified("a.environment", 2, Authority.ENVIRONMENT))
    state.commit_verified(verified("m.oracle", 3, Authority.EXTERNAL_ORACLE))
    context = ContextProjector(ContextPolicy(max_verified_facts=2)).project(
        goal=goal(), state=state, tools={}
    )
    assert list(context["trusted"]["facts"]) == ["m.oracle", "a.environment"]


def test_large_verified_key_is_replaced_by_bounded_stable_projection_id():
    state = HarnessState()
    long_key = "K" * 5000
    state.commit_verified(verified(long_key, 1, Authority.ENVIRONMENT))
    context = ContextProjector(ContextPolicy(max_verified_key_chars=32)).project(
        goal=goal(), state=state, tools={}
    )
    [(projected_key, item)] = list(context["trusted"]["facts"].items())
    assert projected_key.startswith("fact:")
    assert len(item["key_preview"]) == 32
    assert item["key"] is None
    assert item["key_truncated"] is True
    assert len(item["key_hash"]) == 64


def test_small_verified_scalar_keeps_exact_value_for_compatibility():
    state = HarnessState()
    state.commit_verified(verified("answer", 42, Authority.ENVIRONMENT))
    context = ContextProjector().project(goal=goal(), state=state, tools={})
    item = context["trusted"]["facts"]["answer"]
    assert item["value"] == 42
    assert item["value_preview"]["truncated"] is False
