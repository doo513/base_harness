from __future__ import annotations

import json
from types import SimpleNamespace

from harness.core.context import ContextPolicy, ContextProjector
from harness.core.contracts import GoalContract
from harness.core.runtime_context import RuntimeContextMixin
from harness.core.state import Claim, HarnessState, Observation
from harness.core.tools import SideEffect, ToolSpec


class DummyRuntime(RuntimeContextMixin):
    pass


def run_probe() -> dict:
    state = HarnessState()
    state.propose(Claim("hyp", {"raw": "FULL-HYPOTHESIS"}))
    state.observations.append(Observation(
        step=1,
        source="observe",
        ok=True,
        preview={"raw": "FULL-OBSERVATION"},
        artifact_ref=f"artifact://{'a' * 64}_compat.json",
    ))
    for i in range(7):
        state.failures.append({"kind": "tool_error", "message": f"failure-{i}"})

    tool = ToolSpec(
        name="observe",
        description="FULL-TOOL-DESCRIPTION",
        handler=lambda: "ok",
        side_effect=SideEffect.NONE,
        idempotent=True,
        provenance={"revision": "stage7-compat-v1"},
    )
    runtime = DummyRuntime()
    runtime.state = state
    runtime.goal = GoalContract(goal="compat", acceptance=["a"])
    runtime.actions = SimpleNamespace(tools={"observe": tool})
    runtime.context_projector = ContextProjector(ContextPolicy(
        max_speculative_value_chars=4,
        max_preview_chars_per_observation=4,
        max_total_observation_preview_chars=4,
        max_recent_failures=0,
        max_tool_description_chars=3,
    ))

    context = runtime._context()
    serialized = json.loads(json.dumps(context, ensure_ascii=False, default=str))
    serialized_text = json.dumps(serialized, ensure_ascii=False)

    schema_compatible = (
        context["hypotheses"]["hyp"]["value"] == {"raw": "FULL-HYPOTHESIS"}
        and context["observations"][0]["preview"] == {"raw": "FULL-OBSERVATION"}
        and context["recent_failures"] == [
            {"kind": "tool_error", "message": f"failure-{i}"} for i in range(2, 7)
        ]
        and context["tools"]["observe"]["description"] == "FULL-TOOL-DESCRIPTION"
    )
    model_clean = (
        "hypotheses" not in serialized
        and "observations" not in serialized
        and "recent_failures" not in serialized
        and "FULL-HYPOTHESIS" not in serialized_text
        and "FULL-OBSERVATION" not in serialized_text
        and serialized["projection"]["legacy_aliases_model_visible"] is False
    )
    bounded_projection = (
        serialized["untrusted"]["hypotheses"]["hyp"]["value_preview"]["visible_chars"] == 4
        and serialized["untrusted"]["observations"][0]["preview"]["visible_chars"] <= 4
        and serialized["control"]["recent_failures"] == []
        and serialized["tools"]["observe"]["description"] == "FUL"
    )

    result = {
        "stage": "07",
        "probe": "context-compat-rc3",
        "outcomes": {
            "trusted_controller_legacy_value_schema_preserved": {"passed": schema_compatible},
            "legacy_raw_values_not_model_visible": {"passed": model_clean},
            "governed_projection_remains_bounded": {"passed": bounded_projection},
        },
    }
    result["summary"] = {
        "all_passed": all(item["passed"] for item in result["outcomes"].values()),
        "scenario_count": len(result["outcomes"]),
        "legacy_schema_breakages": 0 if schema_compatible else 1,
        "model_visible_legacy_raw_values": 0 if model_clean else 1,
        "governed_projection_budget_bypasses": 0 if bounded_projection else 1,
    }
    return result


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
