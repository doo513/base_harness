from __future__ import annotations

import json

from harness.core.context import ContextPolicy, ContextProjector
from harness.core.contracts import GoalContract
from harness.core.state import Authority, Claim, ClaimStatus, HarnessState


def run_probe() -> dict:
    goal = GoalContract(goal="context cost", acceptance=["A"], pinned_constraints=["PIN"])
    state = HarnessState()
    for i in range(200):
        state.commit_verified(Claim(
            f"fact.{i:03d}",
            {"payload": "Z" * 5000, "index": i},
            status=ClaimStatus.VERIFIED,
            authority=Authority.SUPPORTED,
        ))
    raw_full = json.dumps(
        {key: claim.dump() for key, claim in sorted(state.facts.items())},
        ensure_ascii=False,
        sort_keys=True,
    )
    context = ContextProjector(ContextPolicy(
        max_verified_facts=8,
        max_verified_value_chars=80,
        max_total_verified_value_chars=320,
    )).project(goal=goal, state=state, tools={})
    bounded = json.dumps(context, ensure_ascii=False, sort_keys=True)
    result = {
        "stage": "07-remediation",
        "probe": "trusted-context-cost-v2",
        "measurement": "serialized_chars_proxy_not_token_count",
        "before": {
            "raw_full_verified_fact_chars": len(raw_full),
            "selected_fact_count": 200,
        },
        "after": {
            "bounded_full_context_chars": len(bounded),
            "selected_verified_fact_count": len(context["trusted"]["facts"]),
            "visible_verified_value_chars": context["projection"]["fact_stats"]["visible_verified_value_chars"],
        },
    }
    before = result["before"]["raw_full_verified_fact_chars"]
    after = result["after"]["bounded_full_context_chars"]
    result["summary"] = {
        "all_passed": after < before and result["after"]["selected_verified_fact_count"] == 8,
        "serialized_char_reduction_ratio": round(1.0 - (after / before), 6),
        "durable_fact_count": len(state.facts),
    }
    return result


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
