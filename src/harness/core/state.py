from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from .failures import RecoveryTransition
from .progress import ProgressState
from .retrieval import RetrievalState


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
    pending_recovery: RecoveryTransition | None = None
    recovery_history: list[RecoveryTransition] = field(default_factory=list)
    recovery_directive: dict[str, Any] | None = None
    strategy_generation: int = 0
    recovery_halted: bool = False
    recovery_halt_reason: str | None = None
    progress: ProgressState = field(default_factory=ProgressState)
    retrieval: RetrievalState = field(default_factory=RetrievalState)

    def propose(self, claim: Claim) -> None:
        if claim.status == ClaimStatus.VERIFIED:
            raise ValueError("proposal cannot start VERIFIED")
        self.hypotheses[claim.key] = claim

    def commit_verified(self, claim: Claim) -> None:
        if claim.status != ClaimStatus.VERIFIED:
            raise ValueError("only VERIFIED claims may enter facts")
        self.facts[claim.key] = claim
        self.hypotheses.pop(claim.key, None)
        # A successfully re-verified fact supersedes the current refuted-state
        # marker for the same semantic key. Historical refutation remains in the
        # event log; keeping it in current state would expose contradictory
        # trusted/refuted entries to later projections and recovery logic.
        self.refuted_hypotheses.pop(claim.key, None)

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
            "pending_recovery": (
                self.pending_recovery.dump() if self.pending_recovery is not None else None
            ),
            "recovery_history": [item.dump() for item in self.recovery_history],
            "recovery_directive": (
                dict(self.recovery_directive) if self.recovery_directive is not None else None
            ),
            "strategy_generation": self.strategy_generation,
            "recovery_halted": self.recovery_halted,
            "recovery_halt_reason": self.recovery_halt_reason,
            "progress": self.progress.dump(),
            "retrieval": self.retrieval.dump(),
        }

    @classmethod
    def from_snapshot(cls, raw: dict) -> "HarnessState":
        pending_raw = raw.get("pending_recovery")
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
            pending_recovery=(
                RecoveryTransition.load(pending_raw)
                if isinstance(pending_raw, dict)
                else None
            ),
            recovery_history=[
                RecoveryTransition.load(item)
                for item in raw.get("recovery_history", [])
            ],
            recovery_directive=(
                dict(raw["recovery_directive"])
                if isinstance(raw.get("recovery_directive"), dict)
                else None
            ),
            strategy_generation=int(raw.get("strategy_generation", 0)),
            recovery_halted=bool(raw.get("recovery_halted", False)),
            recovery_halt_reason=raw.get("recovery_halt_reason"),
            progress=ProgressState.load(raw.get("progress", {})),
            retrieval=RetrievalState.load(raw.get("retrieval")),
        )
