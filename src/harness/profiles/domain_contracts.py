from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainPhase:
    id: str
    purpose: str
    exit_evidence: tuple[str, ...] = ()

    def dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "purpose": self.purpose,
            "exit_evidence": list(self.exit_evidence),
        }


@dataclass(frozen=True)
class DomainWorkflowContract:
    name: str
    phases: tuple[DomainPhase, ...]
    guidance: tuple[str, ...] = ()

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": "domain-workflow-v1",
            "name": self.name,
            "phases": [phase.dump() for phase in self.phases],
            "guidance": list(self.guidance),
            "authority": "harness_domain_contract",
            "truth_authority": "none",
            "completion_authority": False,
        }


@dataclass(frozen=True)
class SoftCriterion:
    id: str
    description: str
    max_score: float = 1.0

    def dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "max_score": float(self.max_score),
        }


@dataclass(frozen=True)
class DomainEvaluationContract:
    criteria: tuple[SoftCriterion, ...]
    guidance: tuple[str, ...] = ()

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": "domain-evaluation-v1",
            "criteria": [criterion.dump() for criterion in self.criteria],
            "guidance": list(self.guidance),
            "advisory_only": True,
            "truth_authority": "none",
            "progress_authority": False,
            "completion_authority": False,
        }
