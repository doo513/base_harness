from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Protocol, Any, Callable, Iterable
import hashlib
import json


class VerificationLevel(IntEnum):
    SCHEMA = 0
    STRUCTURAL = 1
    LOGICAL = 2
    TRANSITION = 3
    EXECUTION = 4
    EXTERNAL_ORACLE = 5
    # Backward-compatible alias.
    SYNTAX = 0


@dataclass(frozen=True)
class VerificationRequirement:
    id: str
    minimum_level: VerificationLevel
    description: str = ""
    require_evidence: bool = False
    minimum_confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("verification requirement id must be non-empty")
        if self.minimum_confidence is not None and not (0.0 <= self.minimum_confidence <= 1.0):
            raise ValueError("minimum_confidence must be between 0 and 1")

    def dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "minimum_level": int(self.minimum_level),
            "minimum_level_name": self.minimum_level.name,
            "description": self.description,
            "require_evidence": self.require_evidence,
            "minimum_confidence": self.minimum_confidence,
        }


@dataclass
class VerificationResult:
    verified: bool
    level: VerificationLevel
    reason: str
    verifier: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    coverage: list[str] = field(default_factory=list)
    confidence: float | None = None


@dataclass
class VerificationAssessment:
    accepted: bool
    minimum_level: VerificationLevel
    highest_level: VerificationLevel | None
    satisfied_requirements: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def dump(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "minimum_level": int(self.minimum_level),
            "minimum_level_name": self.minimum_level.name,
            "highest_level": None if self.highest_level is None else int(self.highest_level),
            "highest_level_name": None if self.highest_level is None else self.highest_level.name,
            "satisfied_requirements": list(self.satisfied_requirements),
            "missing_requirements": list(self.missing_requirements),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class VerificationContract:
    minimum_level: VerificationLevel
    requirements: tuple[VerificationRequirement, ...] = ()

    @classmethod
    def legacy(cls, minimum_level: VerificationLevel) -> "VerificationContract":
        return cls(minimum_level=minimum_level)

    def dump(self) -> dict[str, Any]:
        return {
            "minimum_level": int(self.minimum_level),
            "minimum_level_name": self.minimum_level.name,
            "requirements": [r.dump() for r in self.requirements],
        }

    def assess(self, results: Iterable[VerificationResult]) -> VerificationAssessment:
        results = list(results)
        highest = max((r.level for r in results if r.verified), default=None)
        satisfied: list[str] = []
        missing: list[str] = []
        reasons: list[str] = []

        if not results:
            reasons.append("no verifier results")
        if any(not r.verified for r in results):
            reasons.append("one or more verifiers rejected the candidate")
        if highest is None or highest < self.minimum_level:
            reasons.append(f"minimum verification level {self.minimum_level.name} not reached")

        for requirement in self.requirements:
            matches = []
            for result in results:
                if not result.verified:
                    continue
                if requirement.id not in result.coverage:
                    continue
                if result.level < requirement.minimum_level:
                    continue
                if requirement.require_evidence and not result.evidence_refs:
                    continue
                if requirement.minimum_confidence is not None:
                    if result.confidence is None or result.confidence < requirement.minimum_confidence:
                        continue
                matches.append(result)
            if matches:
                satisfied.append(requirement.id)
            else:
                missing.append(requirement.id)

        if missing:
            reasons.append("missing required verification coverage: " + ", ".join(missing))

        accepted = (
            bool(results)
            and all(r.verified for r in results)
            and highest is not None
            and highest >= self.minimum_level
            and not missing
        )
        return VerificationAssessment(
            accepted=accepted,
            minimum_level=self.minimum_level,
            highest_level=highest,
            satisfied_requirements=satisfied,
            missing_requirements=missing,
            reasons=reasons,
        )


class Verifier(Protocol):
    name: str
    level: VerificationLevel
    covers: tuple[str, ...]
    def verify(self, candidate: Any, context: dict) -> VerificationResult: ...


class VerifierChain:
    """Run trusted verifier implementations while enforcing declared metadata.

    The result object is not allowed to self-promote its verification level or
    coverage.  Both are normalized from the verifier object's declared metadata.
    Domain profiles remain responsible for selecting trusted verifier code.
    """

    def __init__(self, verifiers):
        self.verifiers = sorted(verifiers, key=lambda x: int(x.level))

    @staticmethod
    def _normalize(verifier, result: Any) -> VerificationResult:
        name = str(getattr(verifier, "name", type(verifier).__name__))
        declared_level = VerificationLevel(int(verifier.level))
        declared_coverage = sorted({str(x) for x in getattr(verifier, "covers", ()) if str(x)})

        if not isinstance(result, VerificationResult):
            return VerificationResult(
                False,
                declared_level,
                "verifier returned an invalid result object",
                verifier=name,
                coverage=declared_coverage,
            )

        try:
            reported_level = VerificationLevel(int(result.level))
        except Exception:
            reported_level = None
        if reported_level != declared_level:
            return VerificationResult(
                False,
                declared_level,
                "verifier result attempted to report a level different from its declaration",
                verifier=name,
                evidence_refs=list(result.evidence_refs),
                details={"reported_level": None if reported_level is None else int(reported_level)},
                coverage=declared_coverage,
            )

        if result.confidence is not None and not (0.0 <= float(result.confidence) <= 1.0):
            return VerificationResult(
                False,
                declared_level,
                "verifier confidence must be between 0 and 1",
                verifier=name,
                evidence_refs=list(result.evidence_refs),
                coverage=declared_coverage,
            )

        # Trusted metadata comes from the configured verifier, never from the
        # candidate or the result object returned by verify().
        result.verifier = name
        result.level = declared_level
        result.coverage = declared_coverage
        return result

    def run(self, candidate, context) -> list[VerificationResult]:
        results: list[VerificationResult] = []
        for verifier in self.verifiers:
            try:
                raw = verifier.verify(candidate, context)
            except Exception as exc:
                raw = VerificationResult(
                    False,
                    VerificationLevel(int(verifier.level)),
                    f"{type(exc).__name__}: {exc}",
                )
            result = self._normalize(verifier, raw)
            results.append(result)
            if not result.verified:
                break
        return results

    @staticmethod
    def accepted(results, minimum_level) -> bool:
        # Backward-compatible API. New runtime code uses VerificationContract.
        return VerificationContract.legacy(VerificationLevel(minimum_level)).assess(results).accepted


class ExistsVerifier:
    name = "exists"
    level = VerificationLevel.SCHEMA
    covers = ("candidate_exists",)

    def verify(self, candidate, context):
        return VerificationResult(
            candidate is not None,
            self.level,
            "candidate exists" if candidate is not None else "candidate is None",
            verifier=self.name,
            confidence=1.0,
        )


class EvidenceRefVerifier:
    name = "evidence_ref"
    level = VerificationLevel.STRUCTURAL
    covers = ("evidence_present",)

    def verify(self, candidate, context):
        refs = list(context.get("claim_evidence_refs", []))
        known = set(context.get("state", {}).get("artifacts", []))
        missing = [r for r in refs if r not in known]
        ok = bool(refs) and not missing
        reason = "evidence refs resolve to stored artifacts" if ok else "missing or unresolved evidence refs"
        return VerificationResult(
            ok,
            self.level,
            reason,
            verifier=self.name,
            evidence_refs=refs,
            details={"missing": missing},
            confidence=1.0,
        )


class PredicateVerifier:
    def __init__(
        self,
        *,
        name: str,
        level: VerificationLevel,
        predicate: Callable[[Any, dict], bool],
        pass_reason: str = "predicate passed",
        fail_reason: str = "predicate failed",
        covers: Iterable[str] = (),
        confidence: float | None = None,
    ):
        self.name = name
        self.level = level
        self.predicate = predicate
        self.pass_reason = pass_reason
        self.fail_reason = fail_reason
        self.covers = tuple(str(x) for x in covers)
        self.confidence = confidence

    def verify(self, candidate, context):
        try:
            ok = bool(self.predicate(candidate, context))
        except Exception as exc:
            return VerificationResult(False, self.level, f"{type(exc).__name__}: {exc}", verifier=self.name)
        return VerificationResult(
            ok,
            self.level,
            self.pass_reason if ok else self.fail_reason,
            verifier=self.name,
            confidence=self.confidence,
        )


class ClaimBoundEvidenceVerifier:
    """Reject structurally unrelated artifacts.

    This remains a structural/logical helper, not a semantic truth verifier.
    """

    name = "claim_bound_evidence"
    level = VerificationLevel.LOGICAL
    covers = ("claim_evidence_binding",)

    def verify(self, candidate, context):
        from pathlib import Path
        from .storage import ArtifactStore

        claim_key = context.get("claim_key")
        refs = list(context.get("claim_evidence_refs", []))
        artifact_root = Path(context.get("artifact_root", "")).resolve()
        if not claim_key or not refs or not artifact_root.exists():
            return VerificationResult(
                False,
                self.level,
                "claim-bound evidence unavailable",
                verifier=self.name,
                evidence_refs=refs,
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
            confidence=1.0 if ok else None,
        )


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class StructuredArtifactAssertionVerifier:
    """Execution-level verifier for a narrow, explicit artifact proposition.

    Supported claim value:
      {
        "kind": "artifact_json_assertion",
        "path": ["output", "returncode"],
        "operator": "eq",
        "expected": 0
      }

    The verifier proves only that the referenced stored JSON artifact currently
    has the expected value at the declared path.  It deliberately does not try
    to infer the meaning of free-form natural-language claims.
    """

    name = "structured_artifact_assertion"
    level = VerificationLevel.EXECUTION
    covers = ("artifact_semantics",)

    @staticmethod
    def _resolve_path(value: Any, path: list[Any]) -> Any:
        current = value
        for component in path:
            if isinstance(current, dict) and isinstance(component, str):
                if component not in current:
                    raise KeyError(component)
                current = current[component]
            elif isinstance(current, list) and isinstance(component, int):
                current = current[component]
            else:
                raise KeyError(component)
        return current

    def verify(self, candidate, context):
        from pathlib import Path
        from .storage import ArtifactStore

        refs = list(context.get("claim_evidence_refs", []))
        artifact_root = Path(context.get("artifact_root", "")).resolve()
        if not isinstance(candidate, dict) or candidate.get("kind") != "artifact_json_assertion":
            return VerificationResult(
                False,
                self.level,
                "free-form or unsupported claim cannot satisfy structured artifact semantics",
                evidence_refs=refs,
            )
        path = candidate.get("path")
        operator = candidate.get("operator", "eq")
        if not isinstance(path, list) or not path:
            return VerificationResult(False, self.level, "assertion path must be a non-empty list", evidence_refs=refs)
        if any(not isinstance(x, (str, int)) for x in path):
            return VerificationResult(False, self.level, "assertion path components must be strings or integers", evidence_refs=refs)
        if operator != "eq":
            return VerificationResult(False, self.level, "only deterministic eq assertions are supported", evidence_refs=refs)
        if "expected" not in candidate:
            return VerificationResult(False, self.level, "assertion expected value is required", evidence_refs=refs)
        if len(refs) != 1 or not artifact_root.exists():
            return VerificationResult(False, self.level, "exactly one resolvable evidence artifact is required", evidence_refs=refs)

        try:
            artifact = ArtifactStore.resolve_ref_path(artifact_root, refs[0])
            raw = json.loads(artifact.read_text(encoding="utf-8"))
            actual = self._resolve_path(raw, path)
        except Exception as exc:
            return VerificationResult(
                False,
                self.level,
                f"artifact assertion could not be evaluated: {type(exc).__name__}",
                evidence_refs=refs,
                details={"path": path, "operator": operator},
            )

        expected = candidate["expected"]
        ok = actual == expected
        return VerificationResult(
            ok,
            self.level,
            "structured artifact assertion matched" if ok else "structured artifact assertion did not match",
            evidence_refs=refs,
            details={
                "path": path,
                "operator": operator,
                "actual_hash": _stable_hash(actual),
                "expected_hash": _stable_hash(expected),
            },
            confidence=1.0,
        )
