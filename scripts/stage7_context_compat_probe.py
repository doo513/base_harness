from __future__ import annotations

import json

from harness.core.context import ContextPolicy, ContextProjector
from harness.core.contracts import GoalContract
from harness.core.state import HarnessState


def run_probe() -> dict:
    state = HarnessState()
    state.failures.append({
        "kind": "tool_error", "message": "boom", "signature": "sig",
        "repeat_count": 1, "strategy_generation": 0,
        "recommended_recovery": "repair", "retry_safe": False,
        "target": "tool", "recovery_transition_id": "r1",
    })
    state.progress.evaluations = 2
    context = ContextProjector(ContextPolicy()).project(
        goal=GoalContract(goal="compat", acceptance=["a"]), state=state, tools={}
    )
    serialized = json.loads(json.dumps(context, ensure_ascii=False, default=str))
    alias_read = (
        context["recent_failures"] == context["control"]["recent_failures"]
        and context["progress"] == context["control"]["progress"]
    )
    model_clean = (
        "recent_failures" not in serialized
        and "facts" not in serialized
        and "hypotheses" not in serialized
        and "observations" not in serialized
        and serialized["projection"]["legacy_aliases_model_visible"] is False
    )
    result = {
        "stage": "07",
        "probe": "context-compat-rc2",
        "outcomes": {
            "trusted_controller_legacy_reads_work": {"passed": alias_read},
            "legacy_flat_aliases_not_model_visible": {"passed": model_clean},
        },
    }
    result["summary"] = {
        "all_passed": all(item["passed"] for item in result["outcomes"].values()),
        "scenario_count": len(result["outcomes"]),
        "model_visible_legacy_aliases": 0 if model_clean else 1,
        "legacy_controller_read_breakages": 0 if alias_read else 1,
    }
    return result


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__": raise SystemExit(main())
