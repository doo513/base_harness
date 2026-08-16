from __future__ import annotations

from collections.abc import Callable

from harness.core.types import JsonObject


def evaluate_submission(output: str, expected: str | None = None, predicate: Callable[[str], bool] | None = None) -> JsonObject:
    if predicate is not None:
        passed = predicate(output)
        return {"passed": passed, "mode": "predicate", "truncated": False}
    if expected is None:
        return {"passed": None, "mode": "unsupported", "reason": "no evaluator configured", "truncated": False}
    return {"passed": output.strip() == expected.strip(), "mode": "exact", "truncated": False}
