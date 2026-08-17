from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from harness.core.contracts import Evidence, SuccessCriterion, VerificationResult


def verify_criteria(
    criteria: Iterable[SuccessCriterion],
    evidence: Iterable[Evidence],
) -> VerificationResult:
    criteria_list = list(criteria)
    evidence_by_criterion: dict[str, list[Evidence]] = defaultdict(list)
    for item in evidence:
        if item.criterion_id:
            evidence_by_criterion[item.criterion_id].append(item)

    satisfied: list[str] = []
    missing: list[str] = []
    reasons: list[str] = []

    for criterion in criteria_list:
        candidates = evidence_by_criterion.get(criterion.id, [])
        if any(item.verified for item in candidates):
            satisfied.append(criterion.id)
            continue
        if criterion.required:
            missing.append(criterion.id)
            if not candidates:
                reasons.append(f"{criterion.id}: no evidence")
            else:
                reasons.append(f"{criterion.id}: evidence present but unverified")

    passed = not missing
    if not criteria_list:
        passed = False
        reasons.append("no success criteria defined")

    return VerificationResult(
        passed=passed,
        satisfied_criteria=tuple(satisfied),
        missing_criteria=tuple(missing),
        reasons=tuple(reasons),
    )
