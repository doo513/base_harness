from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class ClaimStatus(str, Enum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    VERIFIED = "verified"
    REFUTED = "refuted"


class Authority(str, Enum):
    USER = "user"
    MODEL = "model"
    OBSERVED = "observed"
    SUPPORTED = "supported"
    ENVIRONMENT = "environment"
    TRUSTED_TOOL = "trusted_tool"  # backward-compatible persisted value
    UNTRUSTED_TOOL = "untrusted_tool"
    EXTERNAL_ORACLE = "external_oracle"


@dataclass
class Claim:
    key: str
    value: Any
    status: ClaimStatus = ClaimStatus.PROPOSED
    authority: Authority = Authority.MODEL
    evidence_refs: list[str] = field(default_factory=list)
    valid_until: str | None = None
    superseded_by: str | None = None

    def dump(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["authority"] = self.authority.value
        return d

    @classmethod
    def load(cls, raw: dict) -> "Claim":
        raw = dict(raw)
        raw["status"] = ClaimStatus(raw.get("status", ClaimStatus.PROPOSED))
        raw["authority"] = Authority(raw.get("authority", Authority.MODEL))
        return cls(**raw)


@dataclass
class Observation:
    step: int
    source: str
    ok: bool
    preview: Any = None
    artifact_ref: str | None = None
    error: str | None = None

    def dump(self) -> dict:
        return asdict(self)


@dataclass
class HarnessState:
    facts: dict[str, Claim] = field(default_factory=dict)
    hypotheses: dict[str, Claim] = field(default_factory=dict)
    refuted_hypotheses: dict[str, Claim] = field(default_factory=dict)
    unknowns: list[str] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    step: int = 0
    completion_requested: bool = False
    completed: bool = False

    def propose(self, claim: Claim) -> None:
        if claim.status == ClaimStatus.VERIFIED:
            raise ValueError("proposal cannot start VERIFIED")
        self.hypotheses[claim.key] = claim

    def commit_verified(self, claim: Claim) -> None:
        if claim.status != ClaimStatus.VERIFIED:
            raise ValueError("only VERIFIED claims may enter facts")
        self.facts[claim.key] = claim
        self.hypotheses.pop(claim.key, None)

    def snapshot(self) -> dict:
        return {
            "facts": {k: v.dump() for k, v in self.facts.items()},
            "hypotheses": {k: v.dump() for k, v in self.hypotheses.items()},
            "refuted_hypotheses": {k: v.dump() for k, v in self.refuted_hypotheses.items()},
            "unknowns": list(self.unknowns),
            "failures": list(self.failures),
            "observations": [x.dump() for x in self.observations],
            "evidence_refs": list(self.evidence_refs),
            "artifacts": list(self.artifacts),
            "step": self.step,
            "completion_requested": self.completion_requested,
            "completed": self.completed,
        }

    @classmethod
    def from_snapshot(cls, raw: dict) -> "HarnessState":
        return cls(
            facts={k: Claim.load(v) for k, v in raw.get("facts", {}).items()},
            hypotheses={k: Claim.load(v) for k, v in raw.get("hypotheses", {}).items()},
            refuted_hypotheses={k: Claim.load(v) for k, v in raw.get("refuted_hypotheses", {}).items()},
            unknowns=list(raw.get("unknowns", [])),
            failures=list(raw.get("failures", [])),
            observations=[Observation(**x) for x in raw.get("observations", [])],
            evidence_refs=list(raw.get("evidence_refs", [])),
            artifacts=list(raw.get("artifacts", [])),
            step=int(raw.get("step", 0)),
            completion_requested=bool(raw.get("completion_requested", False)),
            completed=bool(raw.get("completed", False)),
        )
