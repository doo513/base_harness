from __future__ import annotations

import json

from harness.core.context import ContextPolicy, ContextProjector, ContextProjection
from harness.core.contracts import GoalContract
from harness.core.state import HarnessState


def test_legacy_read_aliases_work_without_being_json_serialized():
    state = HarnessState()
    state.failures.append({
        "kind": "tool_error",
        "message": "boom",
        "repeat_count": 1,
        "strategy_generation": 0,
        "recommended_recovery": "repair",
        "retry_safe": False,
        "target": "x",
        "signature": "sig",
        "recovery_transition_id": "r1",
    })
    state.progress.evaluations = 3
    context = ContextProjector(ContextPolicy()).project(
        goal=GoalContract(goal="g", acceptance=["a"]),
        state=state,
        tools={},
    )
    assert isinstance(context, ContextProjection)
    assert context["recent_failures"] == context["control"]["recent_failures"]
    assert context["progress"] == context["control"]["progress"]
    assert context.get("recovery_directive") is None
    assert "recent_failures" in context

    serialized = json.loads(json.dumps(context, ensure_ascii=False, default=str))
    assert "control" in serialized
    assert "recent_failures" not in serialized
    assert "facts" not in serialized
    assert "hypotheses" not in serialized
    assert "observations" not in serialized
    assert serialized["projection"]["legacy_aliases_model_visible"] is False
