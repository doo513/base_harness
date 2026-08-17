from __future__ import annotations

from typing import Any, Mapping

from harness.core.contracts import Action, Evidence, Observation


def observation_from_tool_result(
    action: Action,
    result: Mapping[str, Any],
    *,
    criterion_id: str | None = None,
    expected: str | None = None,
    verified: bool = False,
) -> Observation:
    """Normalize an existing harness tool result into a closed-loop observation.

    Tool success and semantic verification are intentionally separate. A command
    returning zero may be useful evidence, but it does not prove that a goal's
    success criterion is satisfied. Callers may set ``verified=True`` only after
    an explicit verifier/evaluator has accepted the observation.
    """

    exit_code_value = result.get("exit_code", result.get("returncode"))
    exit_code = exit_code_value if isinstance(exit_code_value, int) else None
    error = result.get("error")
    ok_field = result.get("ok")
    if isinstance(ok_field, bool):
        ok = ok_field
    elif exit_code is not None:
        ok = exit_code == 0
    else:
        ok = not bool(error)

    stdout = str(result.get("stdout") or "")
    stderr = str(result.get("stderr") or "")
    summary = str(result.get("summary") or error or f"{action.name}: {'ok' if ok else 'failed'}")

    evidence: tuple[Evidence, ...] = ()
    if criterion_id is not None:
        evidence = (
            Evidence(
                type="tool_result",
                criterion_id=criterion_id,
                source=action.name,
                observed=summary,
                expected=expected,
                verified=bool(ok and verified),
                metadata={"exit_code": exit_code, "tool_ok": ok},
            ),
        )

    duration_value = result.get("duration_ms")
    duration_ms = duration_value if isinstance(duration_value, int) else None

    return Observation(
        action=action,
        ok=ok,
        summary=summary,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        evidence=evidence,
    )
