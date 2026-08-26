from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = 2
DEFAULT_MAX_SAME_FAILURE_REPAIRS = 2
MAX_CAPTURE_CHARS = 32_000
STRENGTH = {"structural": 1, "execution": 2, "behavioral": 3, "external_oracle": 4}
RISKS = {"low", "medium", "high", "critical"}
CLAIM_KINDS = {"artifact", "execution", "behavior", "configuration", "negative", "external"}
RESULTS = {
    "verified",
    "partial",
    "refuted",
    "inconclusive",
    "not_applicable",
    "verifier_invalid",
}
FAILURE_KINDS = {
    "model_provider_error",
    "model_protocol_error",
    "tool_execution_error",
    "implementation_error",
    "harness_error",
    "harness_protocol_error",
    "harness_protocol_version_mismatch",
    "harness_verifier_error",
    "harness_verifier_unavailable",
    "harness_verifier_timeout",
    "integrity_error",
    "persistence_error",
    "verification_failed",
}
SECRET_KEY = re.compile(
    r"(authorization|api[-_]?key|token|secret|password|cookie|credential)",
    re.IGNORECASE,
)


class ProtocolError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def redact(value: Any, key: str = "") -> Any:
    if SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value[:200]]
    if isinstance(value, str) and len(value) > MAX_CAPTURE_CHARS:
        return value[:MAX_CAPTURE_CHARS] + "\n[TRUNCATED]"
    return value


def strip_jsonc(source: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and following == "/":
            index += 2
            while index < len(source) and source[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and following == "*":
            index += 2
            while index + 1 < len(source) and source[index : index + 2] != "*/":
                if source[index] in "\r\n":
                    output.append(source[index])
                index += 1
            index += 2
            continue
        output.append(char)
        index += 1
    cleaned = "".join(output)
    return re.sub(r",\s*([}\]])", r"\1", cleaned)


def load_jsonc(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        raise ProtocolError("base-harness.jsonc must contain a JSON object")
    return value


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        merged[key] = deep_merge(current, value) if isinstance(current, dict) and isinstance(value, dict) else value
    return merged


def config_root() -> Path:
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "base-harness"
    if os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / "base-harness"
    return Path.home() / ".config" / "base-harness"


def state_root() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "base-harness"
    if os.environ.get("XDG_STATE_HOME"):
        return Path(os.environ["XDG_STATE_HOME"]) / "base-harness"
    return Path.home() / ".local" / "state" / "base-harness"


def load_config(workspace: Path) -> dict[str, Any]:
    return deep_merge(
        load_jsonc(config_root() / "base-harness.jsonc"),
        load_jsonc(workspace / "base-harness.jsonc"),
    )


def inside(workspace: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def as_nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(name + " must be a non-empty string")
    return value.strip()


def as_string_list(value: Any, name: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ProtocolError(name + " must be " + ("an array" if allow_empty else "a non-empty array"))
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ProtocolError(name + " must contain non-empty strings")
    return [item.strip() for item in value]


@dataclass(frozen=True)
class VerifierSpec:
    verifier_id: str
    command: tuple[str, ...] | None
    cwd: Path
    strength: str
    claim_kinds: tuple[str, ...]
    method_id: str
    timeout_seconds: float
    deterministic_oracle: bool
    freshness_seconds: int | None
    contradiction_severity: str
    revision: str
    source_hash: str
    policy_hash: str

    def attestation(self) -> dict[str, Any]:
        return {
            "verifierId": self.verifier_id,
            "revision": self.revision,
            "sourceHash": self.source_hash,
            "policyHash": self.policy_hash,
            "buildHash": self.source_hash,
            "testSuiteHash": self.policy_hash,
            "supportedClaimKinds": list(self.claim_kinds),
            "strength": self.strength,
        }


@dataclass
class ScopeState:
    scope_id: str
    parent_scope_id: str | None
    actions: list[dict[str, Any]] = field(default_factory=list)
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class RunState:
    run_id: str
    root_scope_id: str
    workspace: Path
    run_dir: Path
    config: dict[str, Any]
    sources: dict[str, dict[str, Any]]
    scopes: dict[str, ScopeState]
    goal_contract: dict[str, Any] | None = None
    contract_status: str = "missing"
    candidate_refs: list[dict[str, Any]] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    evidence_families: list[dict[str, Any]] = field(default_factory=list)
    criterion_results: list[dict[str, Any]] = field(default_factory=list)
    claim_results: list[dict[str, Any]] = field(default_factory=list)
    repair_counts: dict[str, int] = field(default_factory=dict)
    ready_ref: dict[str, Any] | None = None
    runtime_failure: dict[str, Any] | None = None
    status: str = "open"
    event_hash: str = "0" * 64
    event_sequence: int = 0


class EvidenceMemory:
    TIERS = ("candidate", "supported", "reproduced", "established")

    def __init__(self, root: Path) -> None:
        self.root = root
        self.case_root = root / "memory" / "cases"
        self.retrieval_root = root / "memory" / "retrieval"

    @staticmethod
    def case_id(claim: dict[str, Any]) -> str:
        return canonical_hash(
            {
                "statement": claim["statement"],
                "kind": claim["kind"],
                "scope": claim["scope"],
                "applicability": claim["applicability"],
                "predicate": claim["predicate"],
            }
        )

    def _load(self, claim: dict[str, Any]) -> dict[str, Any]:
        case_id = self.case_id(claim)
        path = self.case_root / (case_id + ".json")
        if path.is_file():
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        return {
            "schemaVersion": "evidence-case-v2",
            "caseId": case_id,
            "title": claim["claimId"] + " - " + claim["statement"][:80],
            "claim": redact(claim),
            "supports": [],
            "contradictions": [],
            "tier": "candidate",
            "status": "active",
            "updatedAt": utc_now(),
        }

    @staticmethod
    def _tier(case: dict[str, Any], revoked: set[str]) -> tuple[str, str]:
        revoked_supports = [
            item
            for item in case.get("supports", [])
            if item.get("verifierId") in revoked
        ]
        supports = [
            item
            for item in case.get("supports", [])
            if item.get("verifierId") not in revoked
        ]
        hard = [item for item in case.get("contradictions", []) if item.get("severity") == "hard"]
        if hard:
            return "candidate", "quarantined"
        if revoked_supports and not supports:
            return "candidate", "quarantined"
        runs = {str(item.get("runId")) for item in supports}
        methods = {str(item.get("methodId")) for item in supports}
        tier_index = 0
        if supports:
            tier_index = 1
        if len(runs) >= 2:
            tier_index = 2
        if len(runs) >= 2 and len(methods) >= 2:
            tier_index = 3
        soft_families = {
            str(item.get("familyId"))
            for item in case.get("contradictions", [])
            if item.get("severity") == "soft"
        }
        if len(soft_families) >= 2:
            tier_index = max(0, tier_index - 1)
        status = "disputed" if soft_families or revoked_supports else "active"
        return EvidenceMemory.TIERS[tier_index], status

    def _write_projection(self, case: dict[str, Any]) -> None:
        if case.get("status") == "quarantined":
            path = self.retrieval_root / (str(case["caseId"]) + ".md")
            if path.exists():
                path.unlink()
            return
        self.retrieval_root.mkdir(parents=True, exist_ok=True)
        claim = case["claim"]
        support = case.get("supports", [])
        contradiction = case.get("contradictions", [])
        lines = [
            "# " + str(case["title"]),
            "",
            "Trust: " + str(case["tier"]) + " / " + str(case["status"]),
            "",
            "## Situation",
            str(claim.get("statement", "")),
            "## Reason",
            "Prior evidence may suggest a verification candidate but has no completion authority.",
            "## Action",
            ", ".join(sorted({str(item.get("methodId")) for item in support})) or "none",
            "## Result",
            f"{len(support)} support event(s), {len(contradiction)} contradiction event(s)",
            "## Evidence",
            ", ".join(str(item.get("evidenceId")) for item in support[-5:]) or "none",
        ]
        path = self.retrieval_root / (str(case["caseId"]) + ".md")
        path.write_text("\n".join(lines[:20]) + "\n", encoding="utf-8")

    def record(
        self,
        claim: dict[str, Any],
        event: dict[str, Any],
        *,
        support: bool,
        severity: str = "soft",
        revoked: set[str] | None = None,
    ) -> dict[str, Any]:
        case = self._load(claim)
        collection = "supports" if support else "contradictions"
        fingerprint = event["semanticFingerprint"]
        existing = {
            (str(item.get("runId")), str(item.get("methodId")), str(item.get("semanticFingerprint")))
            for item in case[collection]
        }
        identity = (str(event.get("runId")), str(event.get("methodId")), str(fingerprint))
        if identity not in existing:
            item = redact(event)
            if not support:
                item["severity"] = severity
            case[collection].append(item)
        case["tier"], case["status"] = self._tier(case, revoked or set())
        case["updatedAt"] = utc_now()
        atomic_json(self.case_root / (str(case["caseId"]) + ".json"), case)
        self._write_projection(case)
        return case

    def recompute(self, claim: dict[str, Any], revoked: set[str]) -> dict[str, Any]:
        case = self._load(claim)
        case["tier"], case["status"] = self._tier(case, revoked)
        case["updatedAt"] = utc_now()
        atomic_json(self.case_root / (str(case["caseId"]) + ".json"), case)
        self._write_projection(case)
        return case

    def independent_historical_methods(
        self,
        claim: dict[str, Any],
        current_methods: set[str],
        revoked: set[str],
    ) -> set[str]:
        case = self._load(claim)
        if case.get("status") == "quarantined":
            return set()
        methods: set[str] = set()
        for event in case.get("supports", []):
            verifier_id = str(event.get("verifierId", ""))
            method_id = str(event.get("methodId", ""))
            if verifier_id in revoked or method_id in current_methods:
                continue
            if event.get("applicabilityHash") != canonical_hash(claim["applicability"]):
                continue
            freshness = event.get("freshnessSeconds")
            if claim.get("kind") in {"execution", "behavior", "configuration"}:
                if claim["applicability"].get("workspaceRevision") in {None, "unknown"}:
                    continue
                if not isinstance(freshness, int):
                    continue
            if isinstance(freshness, int):
                try:
                    observed = datetime.fromisoformat(str(event.get("observedAt")))
                except ValueError:
                    continue
                if (datetime.now(UTC) - observed).total_seconds() > freshness:
                    continue
            methods.add(method_id)
        return methods


class VerificationEngine:
    def __init__(self, root: Path | None = None) -> None:
        self.state_root = (root or state_root()).resolve()
        self.runs: dict[str, RunState] = {}
        self.memory = EvidenceMemory(self.state_root)

    def _run(self, run_id: str) -> RunState:
        try:
            return self.runs[run_id]
        except KeyError as error:
            raise ProtocolError("run.open must be sent before this request") from error

    def _event(self, run: RunState, event_type: str, payload: dict[str, Any]) -> None:
        run.event_sequence += 1
        body = {
            "schemaVersion": "verification-event-v2",
            "sequence": run.event_sequence,
            "previousHash": run.event_hash,
            "eventType": event_type,
            "runId": run.run_id,
            "observedAt": utc_now(),
            "payload": redact(payload),
        }
        body["eventHash"] = canonical_hash(body)
        path = run.run_dir / "events.ndjson"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        run.event_hash = body["eventHash"]

    def _artifact(self, run: RunState, kind: str, trust: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "schemaVersion": "verification-artifact-v2",
            "artifactType": kind,
            "runId": run.run_id,
            "trust": trust,
            "createdAt": utc_now(),
            "payload": redact(payload),
        }
        digest = canonical_hash(body)
        path = run.run_dir / "artifacts" / digest[:2] / (digest + ".json")
        if not path.exists():
            atomic_json(path, body)
        return {
            "artifactType": kind,
            "sha256": digest,
            "path": str(path),
            "trust": trust,
        }

    def _verification_config(self, run: RunState) -> dict[str, Any]:
        value = run.config.get("verification", {})
        return value if isinstance(value, dict) else {}

    def _verifiers(self, run: RunState) -> dict[str, VerifierSpec]:
        raw = self._verification_config(run).get("verifiers", [])
        if raw is None:
            raw = []
        if not isinstance(raw, list):
            raise ProtocolError("verification.verifiers must be an array")
        if self._verification_config(run).get("checks") is not None:
            raise ProtocolError("verification.checks is V1; replace it with verification.verifiers")
        specs: dict[str, VerifierSpec] = {}
        source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        for index, value in enumerate(raw):
            if not isinstance(value, dict):
                raise ProtocolError("verification.verifiers entries must be objects")
            verifier_id = as_nonempty_string(value.get("id", "verifier-" + str(index + 1)), "verifier.id")
            command = value.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
                raise ProtocolError("verification.verifiers[].command must be a non-empty argv array")
            cwd_value = value.get("cwd", ".")
            if not isinstance(cwd_value, str):
                raise ProtocolError("verification.verifiers[].cwd must be a string")
            cwd = (run.workspace / cwd_value).resolve()
            if not inside(run.workspace, cwd):
                raise ProtocolError("verifier cwd must remain inside the workspace")
            strength = str(value.get("strength", "execution"))
            if strength not in STRENGTH:
                raise ProtocolError("unknown verifier strength: " + strength)
            claim_kinds = tuple(as_string_list(value.get("claimKinds", ["execution"]), "verifier.claimKinds"))
            if any(item not in CLAIM_KINDS for item in claim_kinds):
                raise ProtocolError("verifier has an unknown claim kind")
            policy = {
                "command": command,
                "cwd": str(cwd),
                "strength": strength,
                "claimKinds": claim_kinds,
                "methodId": value.get("methodId", verifier_id),
                "deterministicOracle": bool(value.get("deterministicOracle", False)),
                "freshnessSeconds": value.get("freshnessSeconds"),
            }
            specs[verifier_id] = VerifierSpec(
                verifier_id=verifier_id,
                command=tuple(command),
                cwd=cwd,
                strength=strength,
                claim_kinds=claim_kinds,
                method_id=as_nonempty_string(value.get("methodId", verifier_id), "verifier.methodId"),
                timeout_seconds=max(1.0, float(value.get("timeoutSeconds", 120))),
                deterministic_oracle=bool(value.get("deterministicOracle", False)),
                freshness_seconds=(
                    int(value["freshnessSeconds"])
                    if isinstance(value.get("freshnessSeconds"), (int, float))
                    else None
                ),
                contradiction_severity=(
                    "hard" if value.get("contradictionSeverity", "hard") == "hard" else "soft"
                ),
                revision=canonical_hash(policy),
                source_hash=source_hash,
                policy_hash=canonical_hash(policy),
            )
        automatic: list[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = []
        package_path = run.workspace / "package.json"
        if package_path.is_file():
            package = json.loads(package_path.read_text(encoding="utf-8"))
            scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
            manager = "bun" if (run.workspace / "bun.lock").exists() else "npm"
            if isinstance(scripts, dict):
                for script in ("test", "typecheck", "build"):
                    if isinstance(scripts.get(script), str):
                        command = (
                            (manager, "run", script)
                            if manager != "npm"
                            else ("npm", "run", script)
                        )
                        kinds = (
                            ("execution", "behavior")
                            if script == "test"
                            else ("execution", "configuration")
                        )
                        automatic.append(("auto-" + script, command, "behavioral" if script == "test" else "execution", kinds))
        if (run.workspace / "pyproject.toml").is_file() and (run.workspace / "tests").is_dir():
            automatic.append(
                (
                    "auto-pytest",
                    (sys.executable, "-m", "pytest", "-q"),
                    "behavioral",
                    ("execution", "behavior"),
                )
            )
        for verifier_id, command, strength, claim_kinds in automatic:
            if verifier_id in specs:
                continue
            policy = {
                "command": command,
                "cwd": str(run.workspace),
                "strength": strength,
                "claimKinds": claim_kinds,
                "methodId": verifier_id,
                "deterministicOracle": False,
            }
            specs[verifier_id] = VerifierSpec(
                verifier_id=verifier_id,
                command=command,
                cwd=run.workspace,
                strength=strength,
                claim_kinds=claim_kinds,
                method_id=verifier_id,
                timeout_seconds=120.0,
                deterministic_oracle=False,
                freshness_seconds=None,
                contradiction_severity="hard",
                revision=canonical_hash(policy),
                source_hash=source_hash,
                policy_hash=canonical_hash(policy),
            )
        return specs

    @staticmethod
    def _source_ref(source: dict[str, Any]) -> dict[str, Any]:
        source_id = as_nonempty_string(source.get("sourceId"), "sourceId")
        source_type = as_nonempty_string(source.get("sourceType"), "sourceType")
        text = as_nonempty_string(source.get("text"), "source.text")
        return {
            "sourceId": source_id,
            "sourceType": source_type,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text": redact(text),
        }

    def _validate_contract(self, run: RunState, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            raise ProtocolError("contract.propose requires a contract object")
        if raw.get("schemaVersion") != "goal-contract-v2":
            raise ProtocolError("GoalContract schemaVersion must be goal-contract-v2")
        contract = redact(raw)
        as_nonempty_string(contract.get("contractId"), "contractId")
        as_nonempty_string(contract.get("goal"), "goal")
        if not isinstance(contract.get("revision"), int) or contract["revision"] < 1:
            raise ProtocolError("GoalContract revision must be a positive integer")
        source_refs = contract.get("sourceRefs")
        if not isinstance(source_refs, list) or not source_refs:
            raise ProtocolError("GoalContract requires sourceRefs")
        for source_ref in source_refs:
            if not isinstance(source_ref, dict):
                raise ProtocolError("sourceRefs entries must be objects")
            source_id = as_nonempty_string(source_ref.get("sourceId"), "sourceRef.sourceId")
            source = run.sources.get(source_id)
            if source is None or source_ref.get("sha256") != source["sha256"]:
                raise ProtocolError("GoalContract source reference does not match a recorded source")

        criteria = contract.get("criteria")
        claims = contract.get("claims")
        if not isinstance(criteria, list) or not criteria:
            raise ProtocolError("GoalContract requires criteria")
        if not isinstance(claims, list) or not claims:
            raise ProtocolError("GoalContract requires claims")
        verifier_specs = self._verifiers(run)
        claim_by_id: dict[str, dict[str, Any]] = {}
        for claim in claims:
            if not isinstance(claim, dict):
                raise ProtocolError("claims entries must be objects")
            claim_id = as_nonempty_string(claim.get("claimId"), "claimId")
            if claim_id in claim_by_id:
                raise ProtocolError("duplicate claimId: " + claim_id)
            kind = as_nonempty_string(claim.get("kind"), "claim.kind")
            if kind not in CLAIM_KINDS:
                raise ProtocolError("unknown claim kind: " + kind)
            criterion_ids = as_string_list(claim.get("criterionIds"), "claim.criterionIds")
            if claim.get("origin") not in {"user", "harness_policy", "derived_dependency"}:
                raise ProtocolError("claim.origin is invalid")
            as_nonempty_string(claim.get("statement"), "claim.statement")
            scope = claim.get("scope")
            if not isinstance(scope, dict):
                raise ProtocolError("claim.scope must be an object")
            as_string_list(scope.get("targets"), "claim.scope.targets")
            as_string_list(scope.get("capabilities"), "claim.scope.capabilities")
            as_string_list(scope.get("exclusions", []), "claim.scope.exclusions", allow_empty=True)
            applicability = claim.get("applicability")
            if not isinstance(applicability, dict):
                raise ProtocolError("claim.applicability must be an object")
            required_dimensions = {
                "os",
                "arch",
                "runtime",
                "provider",
                "model",
                "tools",
                "dependencyLockHash",
                "configHash",
                "workspaceRevision",
            }
            if not required_dimensions.issubset(applicability):
                raise ProtocolError("claim.applicability is missing required dimensions")
            predicate = claim.get("predicate")
            if not isinstance(predicate, dict) or not isinstance(predicate.get("type"), str):
                raise ProtocolError("claim.predicate must contain one typed predicate")
            policy = claim.get("verifierPolicy")
            if not isinstance(policy, dict):
                raise ProtocolError("claim.verifierPolicy must be an object")
            minimum = str(policy.get("minimumStrength", "execution"))
            if minimum not in STRENGTH:
                raise ProtocolError("claim verifier strength is invalid")
            allowed = as_string_list(policy.get("allowedVerifierIds"), "claim.allowedVerifierIds")
            if "auto" in allowed:
                allowed = [
                    verifier_id
                    for verifier_id, spec in verifier_specs.items()
                    if kind in spec.claim_kinds and STRENGTH[spec.strength] >= STRENGTH[minimum]
                ]
                if not allowed:
                    raise ProtocolError("no applicable verifier is registered for claim " + claim_id)
                policy["allowedVerifierIds"] = sorted(allowed)
            for verifier_id in allowed:
                spec = verifier_specs.get(verifier_id)
                if spec is None:
                    raise ProtocolError("claim references unknown verifier: " + verifier_id)
                if kind not in spec.claim_kinds or STRENGTH[spec.strength] < STRENGTH[minimum]:
                    raise ProtocolError("verifier is not strong enough or cannot verify claim " + claim_id)
            minimum_families = policy.get("minIndependentFamilies", 1)
            if not isinstance(minimum_families, int) or minimum_families < 1:
                raise ProtocolError("minIndependentFamilies must be a positive integer")
            claim_by_id[claim_id] = claim

        criterion_ids: set[str] = set()
        for criterion in criteria:
            if not isinstance(criterion, dict):
                raise ProtocolError("criteria entries must be objects")
            criterion_id = as_nonempty_string(criterion.get("criterionId"), "criterionId")
            if criterion_id in criterion_ids:
                raise ProtocolError("duplicate criterionId: " + criterion_id)
            criterion_ids.add(criterion_id)
            as_nonempty_string(criterion.get("statement"), "criterion.statement")
            if criterion.get("risk") not in RISKS:
                raise ProtocolError("criterion.risk is invalid")
            linked = as_string_list(criterion.get("claimIds"), "criterion.claimIds")
            if any(item not in claim_by_id for item in linked):
                raise ProtocolError("criterion references an unknown claim")
            refs = criterion.get("sourceRefs")
            if not isinstance(refs, list) or not refs:
                raise ProtocolError("criterion requires sourceRefs")
            for source_ref in refs:
                if not isinstance(source_ref, dict):
                    raise ProtocolError("criterion sourceRefs entries must be objects")
                source_id = as_nonempty_string(source_ref.get("sourceId"), "criterion.sourceId")
                source = run.sources.get(source_id)
                if source is None or source_ref.get("sha256") != source["sha256"]:
                    raise ProtocolError("criterion source reference does not match a recorded source")
        for claim_id, claim in claim_by_id.items():
            if any(item not in criterion_ids for item in claim["criterionIds"]):
                raise ProtocolError("claim references an unknown criterion: " + claim_id)
            for criterion_id in claim["criterionIds"]:
                criterion = next(item for item in criteria if item["criterionId"] == criterion_id)
                if claim_id not in criterion["claimIds"]:
                    raise ProtocolError("Criterion-Claim binding must be bidirectional")
        return contract

    def _append_unique(self, target: list[dict[str, Any]], value: dict[str, Any]) -> None:
        identity = (value.get("sha256"), value.get("artifactType"))
        if all((item.get("sha256"), item.get("artifactType")) != identity for item in target):
            target.append(value)

    def _manifest(self, run: RunState) -> None:
        atomic_json(
            run.run_dir / "manifest.json",
            {
                "schemaVersion": "verified-run-v2",
                "sidecarProtocolVersion": PROTOCOL_VERSION,
                "executionCoreRevision": run.config.get("executionCoreRevision", "opencode-v1.18.23-fork"),
                "runId": run.run_id,
                "rootScopeId": run.root_scope_id,
                "workspace": str(run.workspace),
                "goalContract": run.goal_contract,
                "contractStatus": run.contract_status,
                "status": run.status,
                "scopes": {
                    key: {
                        "parentScopeId": value.parent_scope_id,
                        "actionCount": len(value.actions),
                        "pendingActionCount": len(value.pending),
                    }
                    for key, value in run.scopes.items()
                },
                "candidateRefs": run.candidate_refs,
                "evidenceRefs": run.evidence_refs,
                "evidenceFamilies": run.evidence_families,
                "criterionResults": run.criterion_results,
                "claimResults": run.claim_results,
                "readyRef": run.ready_ref,
                "runtimeFailure": run.runtime_failure,
                "repairCounts": run.repair_counts,
                "eventHead": run.event_hash,
                "updatedAt": utc_now(),
            },
        )

    def _status(self, run: RunState, scope_id: str) -> dict[str, Any]:
        return {
            "state": run.status,
            "goal": str((run.goal_contract or {}).get("goal", "")),
            "runId": run.run_id,
            "scopeId": scope_id,
            "rootScopeId": run.root_scope_id,
            "contractStatus": run.contract_status,
            "goalContract": run.goal_contract,
            "criterionResults": run.criterion_results,
            "claimResults": run.claim_results,
            "evidenceFamilies": run.evidence_families,
            "evidenceRefs": run.evidence_refs,
            "candidateRefs": run.candidate_refs,
            "readyRef": run.ready_ref,
            "runtimeFailure": run.runtime_failure,
            "maxSameFailureRepairs": int(
                self._verification_config(run).get(
                    "maxSameFailureRepairs",
                    DEFAULT_MAX_SAME_FAILURE_REPAIRS,
                )
            ),
        }

    @staticmethod
    def _classify_failure(payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        declared = metadata.get("failureKind")
        if declared in FAILURE_KINDS:
            kind = str(declared)
        else:
            rendered = json.dumps(redact(payload), ensure_ascii=False).lower()
            if any(marker in rendered for marker in ("rate limit", "quota", "authentication", "api key", "provider")):
                kind = "model_provider_error"
            elif any(marker in rendered for marker in ("invalid json", "structured output", "response format")):
                kind = "model_protocol_error"
            elif str(payload.get("tool", "")) == "model":
                kind = "model_protocol_error"
            else:
                kind = "tool_execution_error"
        critical = kind in {"integrity_error", "persistence_error", "harness_protocol_error"}
        return {
            "failureKind": kind,
            "severity": "critical" if critical else "error",
            "blocking": True,
            "retryable": kind not in {"integrity_error", "persistence_error"},
            "terminal": critical,
        }

    def _run_verifier(self, run: RunState, spec: VerifierSpec) -> dict[str, Any]:
        started = time.monotonic()
        try:
            completed = subprocess.run(
                spec.command or (),
                cwd=spec.cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=spec.timeout_seconds,
                shell=False,
                check=False,
            )
            return {
                "verifierId": spec.verifier_id,
                "methodId": spec.method_id,
                "command": list(spec.command or ()),
                "cwd": str(spec.cwd),
                "exitCode": completed.returncode,
                "stdout": completed.stdout[-MAX_CAPTURE_CHARS:],
                "stderr": completed.stderr[-MAX_CAPTURE_CHARS:],
                "durationMs": round((time.monotonic() - started) * 1000),
                "attestation": spec.attestation(),
            }
        except subprocess.TimeoutExpired as error:
            return {
                "verifierId": spec.verifier_id,
                "methodId": spec.method_id,
                "command": list(spec.command or ()),
                "cwd": str(spec.cwd),
                "timeoutSeconds": spec.timeout_seconds,
                "stdout": str(error.stdout or "")[-MAX_CAPTURE_CHARS:],
                "stderr": str(error.stderr or "")[-MAX_CAPTURE_CHARS:],
                "durationMs": round((time.monotonic() - started) * 1000),
                "attestation": spec.attestation(),
            }
        except OSError as error:
            return {
                "verifierId": spec.verifier_id,
                "methodId": spec.method_id,
                "command": list(spec.command or ()),
                "cwd": str(spec.cwd),
                "error": str(error),
                "durationMs": round((time.monotonic() - started) * 1000),
                "attestation": spec.attestation(),
            }

    @staticmethod
    def _predicate_result(predicate: dict[str, Any], result: dict[str, Any]) -> tuple[bool, str]:
        predicate_type = str(predicate.get("type"))
        if predicate_type == "command_exit":
            expected = int(predicate.get("expectedExitCode", 0))
            return result.get("exitCode") == expected, "exitCode"
        if predicate_type == "output_contains":
            stream = "stderr" if predicate.get("stream") == "stderr" else "stdout"
            expected = str(predicate.get("value", ""))
            return expected in str(result.get(stream, "")), stream
        return False, "unsupported_predicate"

    def _verify_claim(
        self,
        run: RunState,
        claim: dict[str, Any],
        verifier_specs: dict[str, VerifierSpec],
        cache: dict[str, dict[str, Any]],
        revoked: set[str],
    ) -> dict[str, Any]:
        policy = claim["verifierPolicy"]
        self.memory.recompute(claim, revoked)
        allowed = [item for item in policy["allowedVerifierIds"] if item not in revoked]
        if not allowed:
            return {
                "claimId": claim["claimId"],
                "result": "verifier_invalid",
                "coverage": "none",
                "evidenceIds": [],
                "reason": "Every allowed verifier is missing or revoked.",
            }
        passed: list[tuple[VerifierSpec, dict[str, Any], dict[str, Any]]] = []
        failed: list[tuple[VerifierSpec, dict[str, Any], dict[str, Any]]] = []
        quarantined = False
        for verifier_id in allowed:
            spec = verifier_specs[verifier_id]
            result = cache.setdefault(verifier_id, self._run_verifier(run, spec))
            verified, observed_field = self._predicate_result(claim["predicate"], result)
            semantic = {
                "claimId": claim["claimId"],
                "methodId": spec.method_id,
                "command": result.get("command"),
                "cwd": result.get("cwd"),
                "observedField": observed_field,
                "observedValue": result.get(observed_field),
            }
            semantic_fingerprint = canonical_hash(semantic)
            family_id = canonical_hash(
                {
                    "runId": run.run_id,
                    "methodId": spec.method_id,
                    "command": result.get("command"),
                    "cwd": result.get("cwd"),
                    "applicability": claim["applicability"],
                }
            )
            payload = {
                "claimId": claim["claimId"],
                "criterionIds": claim["criterionIds"],
                "familyId": family_id,
                "semanticFingerprint": semantic_fingerprint,
                "applicability": claim["applicability"],
                "result": result,
                "verified": verified,
            }
            reference = self._artifact(run, "claim_evidence", "verifier_observed", payload)
            event = {
                "evidenceId": reference["sha256"],
                "runId": run.run_id,
                "familyId": family_id,
                "methodId": spec.method_id,
                "verifierId": spec.verifier_id,
                "verifierRevision": spec.revision,
                "semanticFingerprint": semantic_fingerprint,
                "applicabilityHash": canonical_hash(claim["applicability"]),
                "observedAt": utc_now(),
                "freshnessSeconds": spec.freshness_seconds,
            }
            case = self.memory.record(
                claim,
                event,
                support=verified,
                severity=spec.contradiction_severity,
                revoked=revoked,
            )
            quarantined = quarantined or case["status"] == "quarantined"
            family = {
                "familyId": family_id,
                "methodId": spec.method_id,
                "runId": run.run_id,
                "claimId": claim["claimId"],
                "trustTier": case["tier"],
                "status": case["status"],
            }
            if all(item.get("familyId") != family_id for item in run.evidence_families):
                run.evidence_families.append(family)
            self._append_unique(run.evidence_refs, reference)
            (passed if verified else failed).append((spec, result, event))

        methods = {spec.method_id for spec, _, _ in passed}
        deterministic = any(spec.deterministic_oracle for spec, _, _ in passed)
        criterion_risk = max(
            (
                criterion["risk"]
                for criterion in (run.goal_contract or {})["criteria"]
                if criterion["criterionId"] in claim["criterionIds"]
            ),
            key=lambda value: ("low", "medium", "high", "critical").index(value),
        )
        required = int(policy.get("minIndependentFamilies", 1))
        if criterion_risk == "high":
            required = max(required, 2)
        if criterion_risk == "critical":
            required = max(required, 2)
        if criterion_risk == "high" and deterministic:
            required = 1
        historical = self.memory.independent_historical_methods(claim, methods, revoked)
        effective_methods = methods | historical
        if criterion_risk == "critical":
            effective_methods = methods
        has_external = any(spec.strength == "external_oracle" for spec, _, _ in passed)
        enough = len(effective_methods) >= required
        if criterion_risk == "critical" and not has_external:
            enough = False
        if quarantined:
            return {
                "claimId": claim["claimId"],
                "result": "refuted",
                "coverage": "none",
                "evidenceIds": [event["evidenceId"] for _, _, event in passed + failed],
                "reason": "A hard contradiction or revoked verifier dependency quarantined this Claim case.",
            }
        if passed and enough:
            return {
                "claimId": claim["claimId"],
                "result": "verified",
                "coverage": "full",
                "evidenceIds": [event["evidenceId"] for _, _, event in passed],
                "familyIds": [event["familyId"] for _, _, event in passed],
                "historicalIndependentMethods": sorted(historical),
                "reason": "Typed predicate and adaptive independence policy are satisfied.",
            }
        if passed:
            return {
                "claimId": claim["claimId"],
                "result": "partial",
                "coverage": "partial",
                "evidenceIds": [event["evidenceId"] for _, _, event in passed],
                "missingIndependentFamilies": max(0, required - len(effective_methods)),
                "reason": "Direct evidence passed but the adaptive independence requirement is incomplete.",
            }
        return {
            "claimId": claim["claimId"],
            "result": "refuted" if failed else "inconclusive",
            "coverage": "none",
            "evidenceIds": [event["evidenceId"] for _, _, event in failed],
            "reason": "No allowed verifier produced the expected observation.",
        }

    def _reject(
        self,
        run: RunState,
        scope_id: str,
        failed_criterion: str,
        missing_evidence: list[str],
        repair_scope: str,
        *,
        failure_kind: str = "verification_failed",
        details: list[dict[str, Any]] | None = None,
        needs_input: bool = False,
    ) -> dict[str, Any]:
        body = {
            "failureKind": failure_kind,
            "failedCriterion": failed_criterion,
            "missingEvidence": sorted(missing_evidence),
            "details": details or [],
        }
        fingerprint = canonical_hash(body)
        count = run.repair_counts.get(fingerprint, 0) + 1
        run.repair_counts[fingerprint] = count
        maximum = int(
            self._verification_config(run).get(
                "maxSameFailureRepairs",
                DEFAULT_MAX_SAME_FAILURE_REPAIRS,
            )
        )
        outcome = "needs_input" if needs_input else ("blocked" if count > maximum else "repair")
        run.status = outcome
        run.ready_ref = None
        rejection = {
            "outcome": outcome,
            "failureKind": failure_kind,
            "failedCriterion": failed_criterion,
            "missingEvidence": missing_evidence,
            "repairScope": repair_scope,
            "repairCount": count,
            "failureFingerprint": fingerprint,
            "details": details or [],
        }
        reference = self._artifact(run, "verification_rejection", "verifier_attested", rejection)
        self._event(run, "verification.rejected", {"reference": reference, **rejection})
        self._manifest(run)
        return {**self._status(run, scope_id), **rejection}

    def handle(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if envelope.get("version") != PROTOCOL_VERSION:
            raise ProtocolError(
                "sidecar protocol version mismatch: expected "
                + str(PROTOCOL_VERSION)
                + ", received "
                + repr(envelope.get("version"))
            )
        request_type = envelope.get("type")
        run_id = envelope.get("runId")
        scope_id = envelope.get("scopeId")
        payload = envelope.get("payload", {})
        if not isinstance(request_type, str) or not isinstance(run_id, str) or not isinstance(scope_id, str):
            raise ProtocolError("version, runId, scopeId and type are required")
        if not isinstance(payload, dict):
            raise ProtocolError("payload must be an object")

        if request_type == "hello":
            return {
                "protocolVersion": PROTOCOL_VERSION,
                "verifier": "base-harness-verifier",
                "capabilities": [
                    "run.open",
                    "scope.open",
                    "contract.propose",
                    "contract.amend",
                    "action.open",
                    "action.close",
                    "verify.request",
                    "status.get",
                    "run.close",
                ],
            }
        if request_type == "run.open":
            workspace_value = payload.get("workspace")
            source_values = payload.get("goalSources")
            if source_values is None and isinstance(payload.get("goalSource"), dict):
                source_values = [payload["goalSource"]]
            if not isinstance(workspace_value, str) or not isinstance(source_values, list) or not source_values:
                raise ProtocolError("run.open requires workspace and goalSources")
            workspace = Path(workspace_value).resolve()
            if not workspace.is_dir():
                raise ProtocolError("workspace does not exist")
            sources = {}
            for raw_source in source_values:
                if not isinstance(raw_source, dict):
                    raise ProtocolError("goalSources entries must be objects")
                source = self._source_ref(raw_source)
                sources[source["sourceId"]] = source
            token = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16] + "-" + uuid.uuid4().hex[:8]
            run_dir = self.state_root / "runs" / token
            run_dir.mkdir(parents=True, exist_ok=False)
            run = RunState(
                run_id=run_id,
                root_scope_id=scope_id,
                workspace=workspace,
                run_dir=run_dir,
                config=load_config(workspace),
                sources=sources,
                scopes={scope_id: ScopeState(scope_id, None)},
            )
            self.runs[run_id] = run
            self._event(run, "run.opened", {"sources": list(sources.values())})
            if isinstance(payload.get("goalContract"), dict):
                run.goal_contract = self._validate_contract(run, payload["goalContract"])
                run.contract_status = "accepted"
                self._event(run, "contract.accepted", {"contract": run.goal_contract})
            self._manifest(run)
            return self._status(run, scope_id)

        run = self._run(run_id)
        if request_type == "scope.open":
            parent = payload.get("parentScopeId")
            if not isinstance(parent, str) or parent not in run.scopes:
                raise ProtocolError("scope.open requires an existing parentScopeId")
            if scope_id in run.scopes:
                raise ProtocolError("scopeId is already open")
            run.scopes[scope_id] = ScopeState(scope_id, parent)
            self._event(run, "scope.opened", {"scopeId": scope_id, "parentScopeId": parent})
            self._manifest(run)
            return self._status(run, scope_id)
        if request_type in {"contract.propose", "contract.amend"}:
            contract = self._validate_contract(run, payload.get("contract"))
            if request_type == "contract.amend":
                if run.goal_contract is None:
                    raise ProtocolError("contract.amend requires an accepted contract")
                if contract["revision"] <= run.goal_contract["revision"]:
                    raise ProtocolError("contract amendment revision must increase")
                if any(scope.actions for scope in run.scopes.values()):
                    previous_claims = {item["claimId"] for item in run.goal_contract["claims"]}
                    new_claims = {item["claimId"] for item in contract["claims"]}
                    if not previous_claims.issubset(new_claims):
                        raise ProtocolError("contract amendments cannot remove claims after actions")
            run.goal_contract = contract
            run.contract_status = "accepted"
            run.status = "open"
            self._event(run, "contract.accepted", {"contract": contract, "amendment": request_type == "contract.amend"})
            self._manifest(run)
            return self._status(run, scope_id)
        if request_type == "action.open":
            if run.goal_contract is None:
                return self._reject(
                    run,
                    scope_id,
                    "goal_contract_missing",
                    ["Submit a typed GoalContract before executing state-changing actions."],
                    "Submit harness_contract with Criterion, Claim, Scope, Applicability and VerifierPolicy.",
                )
            scope = run.scopes.get(scope_id)
            if scope is None:
                raise ProtocolError("scope is not open")
            action_id = as_nonempty_string(payload.get("actionId"), "actionId")
            execution_id = as_nonempty_string(payload.get("executionId"), "executionId")
            if action_id in scope.pending:
                raise ProtocolError("actionId is already pending")
            claims = as_string_list(payload.get("claimIds"), "action.claimIds")
            known = {item["claimId"] for item in run.goal_contract["claims"]}
            if any(item not in known for item in claims):
                raise ProtocolError("action references an unknown claim")
            action = {
                "actionId": action_id,
                "executionId": execution_id,
                "scopeId": scope_id,
                "claimIds": claims,
                "tool": as_nonempty_string(payload.get("tool"), "action.tool"),
                "input": redact(payload.get("input")),
                "inputHash": canonical_hash(redact(payload.get("input"))),
                "startedAt": payload.get("startedAt", utc_now()),
            }
            scope.pending[action_id] = action
            self._event(run, "action.opened", action)
            self._manifest(run)
            return self._status(run, scope_id)
        if request_type == "action.close":
            scope = run.scopes.get(scope_id)
            if scope is None:
                raise ProtocolError("scope is not open")
            action_id = as_nonempty_string(payload.get("actionId"), "actionId")
            action = scope.pending.pop(action_id, None)
            if action is None:
                raise ProtocolError("action.close requires a matching action.open")
            status = payload.get("status")
            if status not in {"completed", "error"}:
                raise ProtocolError("action status must be completed or error")
            action.update(
                {
                    "status": status,
                    "output": redact(payload.get("output")),
                    "error": redact(payload.get("error")),
                    "metadata": redact(payload.get("metadata", {})),
                    "completedAt": payload.get("completedAt", utc_now()),
                }
            )
            action["semanticFingerprint"] = canonical_hash(
                {
                    "tool": action["tool"],
                    "inputHash": action["inputHash"],
                    "status": status,
                    "output": action["output"],
                    "error": action["error"],
                }
            )
            scope.actions.append(action)
            reference = self._artifact(run, "action_observation", "untrusted_execution_observation", action)
            self._append_unique(run.candidate_refs, reference)
            if status == "error":
                failure = self._classify_failure(payload)
                run.runtime_failure = {
                    **failure,
                    "scopeId": scope_id,
                    "tool": action["tool"],
                    "fingerprint": canonical_hash(
                        {"kind": failure["failureKind"], "tool": action["tool"], "error": action["error"]}
                    ),
                }
            elif run.runtime_failure and run.runtime_failure.get("tool") == action["tool"]:
                run.runtime_failure = None
            self._event(run, "action.closed", {"action": action, "reference": reference})
            self._manifest(run)
            return self._status(run, scope_id)
        if request_type == "status.get":
            return self._status(run, scope_id)
        if request_type == "run.close":
            run.status = "closed"
            self._event(run, "run.closed", {})
            self._manifest(run)
            return self._status(run, scope_id)
        if request_type != "verify.request":
            raise ProtocolError("unsupported request type: " + request_type)

        if run.goal_contract is None:
            return self._reject(
                run,
                scope_id,
                "goal_contract_missing",
                ["No accepted GoalContract exists."],
                "Submit harness_contract before verification.",
            )
        if scope_id != run.root_scope_id:
            return self._reject(
                run,
                scope_id,
                "root_scope_required",
                ["Only the root GoalContract can receive Ready."],
                "Return child Evidence to the root scope.",
            )
        if any(scope.pending for scope in run.scopes.values()):
            return self._reject(
                run,
                scope_id,
                "pending_actions",
                ["One or more actions have not emitted action.close."],
                "Close pending actions before verification.",
            )
        if not any(scope.actions for scope in run.scopes.values()):
            return self._reject(
                run,
                scope_id,
                "missing_action_evidence",
                ["No host-observed action is bound to the GoalContract."],
                "Execute the minimum action required by the accepted Claim.",
            )
        if run.runtime_failure:
            return self._reject(
                run,
                scope_id,
                "runtime_failure",
                [str(run.runtime_failure.get("failureKind"))],
                "Repair only the failed provider, model, tool or implementation boundary.",
                failure_kind=str(run.runtime_failure.get("failureKind", "verification_failed")),
                details=[run.runtime_failure],
            )

        verifier_specs = self._verifiers(run)
        revoked = {
            str(item)
            for item in self._verification_config(run).get("revokedVerifiers", [])
            if isinstance(item, str)
        }
        cache: dict[str, dict[str, Any]] = {}
        run.claim_results = [
            self._verify_claim(run, claim, verifier_specs, cache, revoked)
            for claim in run.goal_contract["claims"]
        ]
        result_by_claim = {item["claimId"]: item for item in run.claim_results}
        run.criterion_results = []
        for criterion in run.goal_contract["criteria"]:
            linked = [result_by_claim[item] for item in criterion["claimIds"]]
            if all(item["result"] == "verified" and item["coverage"] == "full" for item in linked):
                result = "verified"
                coverage = "full"
            elif any(item["result"] == "refuted" for item in linked):
                result = "refuted"
                coverage = "none"
            elif any(item["coverage"] == "partial" for item in linked):
                result = "partial"
                coverage = "partial"
            else:
                result = "inconclusive"
                coverage = "none"
            run.criterion_results.append(
                {
                    "criterionId": criterion["criterionId"],
                    "result": result,
                    "coverage": coverage,
                    "claimIds": criterion["claimIds"],
                    "required": bool(criterion.get("required", True)),
                    "risk": criterion["risk"],
                }
            )
        failed = [
            item
            for item in run.criterion_results
            if item["required"] and item["result"] != "verified"
        ]
        if failed:
            first = failed[0]
            missing = [
                item["claimId"] + ": " + item["reason"]
                for item in run.claim_results
                if item["claimId"] in first["claimIds"] and item["result"] != "verified"
            ]
            return self._reject(
                run,
                scope_id,
                str(first["criterionId"]),
                missing,
                "Repair only the failed Claim or add the required independent verifier evidence.",
                details=failed,
            )

        ready_payload = {
            "goalContract": run.goal_contract,
            "criterionResults": run.criterion_results,
            "claimResults": run.claim_results,
            "evidenceRefs": run.evidence_refs,
            "evidenceFamilies": run.evidence_families,
            "scopeId": scope_id,
            "verificationMode": self._verification_config(run).get("mode", "adaptive"),
            "requestedBy": redact(payload),
            "eventHead": run.event_hash,
        }
        run.ready_ref = self._artifact(run, "ready_attestation", "verifier_attested", ready_payload)
        run.status = "ready"
        self._event(run, "ready.issued", {"readyRef": run.ready_ref})
        self._manifest(run)
        return {
            **self._status(run, scope_id),
            "outcome": "ready",
            "failureKind": None,
            "failedCriterion": None,
            "missingEvidence": [],
            "repairScope": None,
            "repairCount": 0,
        }
