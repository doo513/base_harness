from __future__ import annotations

import json
from types import SimpleNamespace

from harness.core.context import ContextPolicy, ContextProjector, ContextProjection
from harness.core.contracts import GoalContract
from harness.core.runtime_context import RuntimeContextMixin, RuntimeContextProjection
from harness.core.state import Authority, Claim, ClaimStatus, HarnessState, Observation
from harness.core.tools import SideEffect, ToolSpec


def _tool():
    return ToolSpec(
        name="observe",
        description="FULL LEGACY DESCRIPTION " + ("x" * 100),
        handler=lambda: "ok",
        side_effect=SideEffect.NONE,
        idempotent=True,
        provenance={"revision": "stage7-compat-v1"},
    )


class DummyRuntime(RuntimeContextMixin):
    pass


def _runtime_context() -> RuntimeContextProjection:
    state = HarnessState()
    state.facts["fact"] = Claim(
        "fact", {"raw": "FACT"}, status=ClaimStatus.VERIFIED,
        authority=Authority.ENVIRONMENT,
    )
    state.propose(Claim("hyp", {"raw": "HYPOTHESIS-VALUE"}))
    state.refuted_hypotheses["old"] = Claim("old", "REFUTED")
    state.unknowns.append("UNKNOWN-RAW")
    state.observations.append(Observation(
        step=2,
        source="observe",
        ok=True,
        preview={"raw": "OBSERVATION-VALUE"},
        artifact_ref=f"artifact://{'a' * 64}_compat.json",
    ))
    for i in range(7):
        state.failures.append({"kind": "tool_error", "message": f"failure-{i}"})
    state.progress.evaluations = 3

    runtime = DummyRuntime()
    runtime.state = state
    runtime.goal = GoalContract(
        goal="g", acceptance=["a"], pinned_constraints=["pinned"]
    )
    runtime.actions = SimpleNamespace(tools={"observe": _tool()})
    runtime.context_projector = ContextProjector(ContextPolicy(
        max_speculative_value_chars=4,
        max_observations=1,
        max_preview_chars_per_observation=4,
        max_total_observation_preview_chars=4,
        max_recent_failures=0,
        max_tool_description_chars=3,
    ))
    return runtime._context()


def test_runtime_moved_legacy_read_schema_preserves_old_values_without_model_serialization():
    context = _runtime_context()
    assert isinstance(context, RuntimeContextProjection)

    # Fields that moved into namespaces keep their old raw trusted-Controller
    # read schema through non-serialized aliases.
    assert context["facts"]["fact"]["value"] == {"raw": "FACT"}
    assert context["hypotheses"]["hyp"]["value"] == {"raw": "HYPOTHESIS-VALUE"}
    assert context["refuted_hypotheses"]["old"]["value"] == "REFUTED"
    assert context["unknowns"] == ["UNKNOWN-RAW"]
    assert context["observations"][0]["preview"] == {"raw": "OBSERVATION-VALUE"}
    assert context["recent_failures"] == [
        {"kind": "tool_error", "message": f"failure-{i}"} for i in range(2, 7)
    ]
    assert context["progress"]["evaluations"] == 3

    # `tools` did not move out of the top-level schema. It must therefore have
    # one governed value for Python lookup and JSON/model serialization rather
    # than returning a different hidden legacy value in-process.
    assert context["tools"]["observe"] == {
        "description": "FUL",
        "description_truncated": True,
        "side_effect": "none",
        "idempotent": True,
    }

    assert context["untrusted"]["hypotheses"]["hyp"]["value_preview"]["visible_chars"] == 4
    assert context["untrusted"]["observations"][0]["preview"]["visible_chars"] <= 4
    assert context["control"]["recent_failures"] == []

    serialized = json.loads(json.dumps(context, ensure_ascii=False, default=str))
    serialized_text = json.dumps(serialized, ensure_ascii=False)
    assert serialized["tools"] == context["tools"]
    assert "recent_failures" not in serialized
    assert "facts" not in serialized
    assert "hypotheses" not in serialized
    assert "observations" not in serialized
    assert "HYPOTHESIS-VALUE" not in serialized_text
    assert "OBSERVATION-VALUE" not in serialized_text
    assert serialized["projection"]["legacy_aliases_model_visible"] is False


def test_legacy_snapshot_is_detached_from_durable_state():
    context = _runtime_context()
    context["hypotheses"]["hyp"]["value"]["raw"] = "MUTATED-COPY"
    context["recent_failures"][0]["message"] = "MUTATED-COPY"

    fresh = _runtime_context()
    assert fresh["hypotheses"]["hyp"]["value"] == {"raw": "HYPOTHESIS-VALUE"}
    assert fresh["recent_failures"][0]["message"] == "failure-2"


def test_base_context_projection_still_has_nonserialized_transition_aliases():
    state = HarnessState()
    context = ContextProjector(ContextPolicy()).project(
        goal=GoalContract(goal="g", acceptance=["a"]),
        state=state,
        tools={},
    )
    assert isinstance(context, ContextProjection)
    assert context.get("recovery_directive") is None
    serialized = json.loads(json.dumps(context, ensure_ascii=False, default=str))
    assert "facts" not in serialized
    assert "hypotheses" not in serialized
