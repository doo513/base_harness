from dataclasses import dataclass, field
from enum import IntEnum
from typing import Protocol, Any, Callable

class VerificationLevel(IntEnum):
    SCHEMA = 0
    STRUCTURAL = 1
    LOGICAL = 2
    TRANSITION = 3
    EXECUTION = 4
    EXTERNAL_ORACLE = 5
    # Backward-compatible alias.
    SYNTAX = 0

@dataclass
class VerificationResult:
    verified: bool
    level: VerificationLevel
    reason: str
    verifier: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

class Verifier(Protocol):
    name: str
    level: VerificationLevel
    def verify(self, candidate: Any, context: dict) -> VerificationResult: ...

class VerifierChain:
    def __init__(self, verifiers):
        self.verifiers = sorted(verifiers, key=lambda x: int(x.level))

    def run(self, candidate, context) -> list[VerificationResult]:
        results: list[VerificationResult] = []
        for verifier in self.verifiers:
            result = verifier.verify(candidate, context)
            if not result.verifier:
                result.verifier = verifier.name
            results.append(result)
            if not result.verified:
                break
        return results

    @staticmethod
    def accepted(results, minimum_level) -> bool:
        return (
            bool(results)
            and all(r.verified for r in results)
            and results[-1].level >= minimum_level
        )

class ExistsVerifier:
    name = "exists"
    level = VerificationLevel.SCHEMA

    def verify(self, candidate, context):
        return VerificationResult(
            candidate is not None,
            self.level,
            "candidate exists" if candidate is not None else "candidate is None",
            verifier=self.name,
        )

class EvidenceRefVerifier:
    name = "evidence_ref"
    level = VerificationLevel.STRUCTURAL

    def verify(self, candidate, context):
        refs = list(context.get("claim_evidence_refs", []))
        known = set(context.get("state", {}).get("artifacts", []))
        missing = [r for r in refs if r not in known]
        ok = bool(refs) and not missing
        reason = "evidence refs resolve to stored artifacts" if ok else "missing or unresolved evidence refs"
        return VerificationResult(ok, self.level, reason, verifier=self.name, evidence_refs=refs,
                                  details={"missing": missing})

class PredicateVerifier:
    def __init__(self, *, name: str, level: VerificationLevel, predicate: Callable[[Any, dict], bool],
                 pass_reason: str = "predicate passed", fail_reason: str = "predicate failed"):
        self.name = name
        self.level = level
        self.predicate = predicate
        self.pass_reason = pass_reason
        self.fail_reason = fail_reason

    def verify(self, candidate, context):
        try:
            ok = bool(self.predicate(candidate, context))
        except Exception as exc:
            return VerificationResult(False, self.level, f"{type(exc).__name__}: {exc}", verifier=self.name)
        return VerificationResult(ok, self.level, self.pass_reason if ok else self.fail_reason, verifier=self.name)


class ClaimBoundEvidenceVerifier:
    """Rejects structurally unrelated artifacts.

    This is NOT a semantic truth verifier. It only proves that evidence was explicitly
    produced/bound for the claim being verified. Domain profiles should still require
    stronger LOGICAL/EXECUTION/EXTERNAL verifiers for meaningful claims.
    """
    name = "claim_bound_evidence"
    level = VerificationLevel.LOGICAL

    def verify(self, candidate, context):
        import json
        from pathlib import Path
        from .storage import ArtifactStore

        claim_key = context.get("claim_key")
        refs = list(context.get("claim_evidence_refs", []))
        artifact_root = Path(context.get("artifact_root", "")).resolve()
        if not claim_key or not refs or not artifact_root.exists():
            return VerificationResult(
                False, self.level, "claim-bound evidence unavailable",
                verifier=self.name, evidence_refs=refs
            )

        bad = []
        for ref in refs:
            try:
                p = ArtifactStore.resolve_ref_path(artifact_root, ref)
                raw = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                bad.append(ref)
                continue
            if raw.get("bound_claim") != claim_key:
                bad.append(ref)

        ok = not bad
        return VerificationResult(
            ok,
            self.level,
            "all evidence artifacts are explicitly bound to claim" if ok else "evidence is unresolved or not bound to claim",
            verifier=self.name,
            evidence_refs=refs,
            details={"unbound": bad},
        )
