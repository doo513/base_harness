from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class LoopStage(str, Enum):
    INTAKE = "intake"
    REASON = "reason"
    ACT = "act"
    OBSERVE = "observe"
    VERIFY = "verify"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class SuccessCriterion:
    id: str
    description: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class Evidence:
    type: str
    criterion_id: str | None = None
    source: str | None = None
    observed: str | None = None
    expected: str | None = None
    verified: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Action:
    kind: str
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class Observation:
    action: Action
    ok: bool
    summary: str
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int | None = None
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True, slots=True)
class VerificationResult:
    passed: bool
    satisfied_criteria: tuple[str, ...]
    missing_criteria: tuple[str, ...]
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LoopState:
    objective: str
    stage: LoopStage
    iteration: int = 0
    success_criteria: tuple[SuccessCriterion, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    observations: tuple[Observation, ...] = ()
    last_action: Action | None = None
    notes: tuple[str, ...] = ()

    def with_stage(self, stage: LoopStage, *, note: str | None = None) -> "LoopState":
        notes = self.notes + ((note,) if note else ())
        return LoopState(
            objective=self.objective,
            stage=stage,
            iteration=self.iteration,
            success_criteria=self.success_criteria,
            evidence=self.evidence,
            observations=self.observations,
            last_action=self.last_action,
            notes=notes,
        )

    def with_observation(self, observation: Observation) -> "LoopState":
        return LoopState(
            objective=self.objective,
            stage=LoopStage.OBSERVE,
            iteration=self.iteration + 1,
            success_criteria=self.success_criteria,
            evidence=self.evidence + observation.evidence,
            observations=self.observations + (observation,),
            last_action=observation.action,
            notes=self.notes,
        )


def normalize_criteria(items: Sequence[str | Mapping[str, Any]] | None) -> tuple[SuccessCriterion, ...]:
    if not items:
        return ()
    criteria: list[SuccessCriterion] = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, str):
            criteria.append(SuccessCriterion(id=f"C{index:03d}", description=item))
            continue
        criterion_id = str(item.get("id") or f"C{index:03d}")
        description = str(item.get("description") or item.get("expected") or "").strip()
        if not description:
            continue
        criteria.append(
            SuccessCriterion(
                id=criterion_id,
                description=description,
                required=bool(item.get("required", True)),
            )
        )
    return tuple(criteria)
