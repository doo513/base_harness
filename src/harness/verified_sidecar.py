from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO


PROTOCOL_VERSION = 1
DEFAULT_MAX_SAME_FAILURE_REPAIRS = 2
MAX_CAPTURE_CHARS = 32_000
SECRET_KEY = re.compile(
    r"(authorization|api[-_]?key|token|secret|password|cookie|credential)",
    re.IGNORECASE,
)


class ProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    command: tuple[str, ...]
    cwd: Path
    timeout_seconds: float = 120.0


@dataclass
class ScopeState:
    scope_id: str
    parent_scope_id: str | None
    actions: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunState:
    run_id: str
    root_scope_id: str
    workspace: Path
    goal_contract: dict[str, Any]
    run_dir: Path
    config: dict[str, Any]
    scopes: dict[str, ScopeState]
    candidate_refs: list[dict[str, Any]] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    repair_counts: dict[str, int] = field(default_factory=dict)
    ready_ref: dict[str, Any] | None = None
    runtime_failure: dict[str, Any] | None = None
    status: str = "open"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _state_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "base-harness"
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / "base-harness"
    return Path.home() / ".local" / "state" / "base-harness"


def _config_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "base-harness"
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "base-harness"
    return Path.home() / ".config" / "base-harness"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _strip_jsonc(source: str) -> str:
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
    output = []
    index = 0
    in_string = False
    escaped = False
    while index < len(cleaned):
        char = cleaned[index]
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
        if char == ",":
            lookahead = index + 1
            while lookahead < len(cleaned) and cleaned[lookahead].isspace():
                lookahead += 1
            if lookahead < len(cleaned) and cleaned[lookahead] in "]}":
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output)


def _load_jsonc(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        raise ProtocolError("base-harness.jsonc must contain a JSON object")
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _load_config(workspace: Path) -> dict[str, Any]:
    user = _load_jsonc(_config_root() / "base-harness.jsonc")
    project = _load_jsonc(workspace / "base-harness.jsonc")
    return _deep_merge(user, project)


def _redact(value: Any, key: str = "") -> Any:
    if SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value[:100]]
    if isinstance(value, str) and len(value) > MAX_CAPTURE_CHARS:
        return value[:MAX_CAPTURE_CHARS] + "\n[TRUNCATED]"
    return value


def _classify_runtime_failure(value: Any) -> str:
    rendered = json.dumps(_redact(value), ensure_ascii=False).lower()
    if any(
        marker in rendered
        for marker in (
            "rate limit",
            "ratelimit",
            "quota",
            "unauthorized",
            "authentication",
            "api key",
            "provider",
            "model not found",
        )
    ):
        return "model_provider_error"
    if any(
        marker in rendered
        for marker in (
            "invalid json",
            "protocol",
            "schema",
            "structured output",
            "response format",
        )
    ):
        return "model_protocol_error"
    if any(marker in rendered for marker in ("verifier", "sidecar", "ndjson", "harness")):
        return "harness_error"
    return "implementation_error"


def _inside_workspace(workspace: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def _artifact(run: RunState, kind: str, trust: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = {
        "schemaVersion": 1,
        "artifactType": kind,
        "runId": run.run_id,
        "trust": trust,
        "createdAt": _utc_now(),
        "payload": _redact(payload),
    }
    digest = hashlib.sha256(_canonical_bytes(body)).hexdigest()
    path = run.run_dir / "artifacts" / digest[:2] / (digest + ".json")
    if not path.exists():
        _atomic_json(path, body)
    return {
        "artifactType": kind,
        "sha256": digest,
        "path": str(path),
        "trust": trust,
    }


def _verification_config(run: RunState) -> dict[str, Any]:
    value = run.config.get("verification", {})
    return value if isinstance(value, dict) else {}


def _package_command(workspace: Path, script: str, package: dict[str, Any]) -> tuple[str, ...]:
    manager = str(package.get("packageManager", "")).split("@", 1)[0]
    if not manager:
        if (workspace / "bun.lock").exists() or (workspace / "bun.lockb").exists():
            manager = os.environ.get("BASE_HARNESS_BUN", "bun")
        elif (workspace / "pnpm-lock.yaml").exists():
            manager = "pnpm"
        elif (workspace / "yarn.lock").exists():
            manager = "yarn"
        else:
            manager = "npm"
    if manager == "npm":
        return ("npm", "run", script)
    return (manager, "run", script)


def _discover_checks(run: RunState) -> list[CheckSpec]:
    verification = _verification_config(run)
    configured = verification.get("checks")
    checks: list[CheckSpec] = []
    if isinstance(configured, list):
        for index, value in enumerate(configured):
            if not isinstance(value, dict):
                raise ProtocolError("verification.checks entries must be objects")
            command = value.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
                raise ProtocolError("verification.checks[].command must be a non-empty argv array")
            cwd_value = value.get("cwd", ".")
            if not isinstance(cwd_value, str):
                raise ProtocolError("verification.checks[].cwd must be a string")
            cwd = (run.workspace / cwd_value).resolve()
            if not _inside_workspace(run.workspace, cwd):
                raise ProtocolError("verification check cwd must remain inside the workspace")
            timeout = float(value.get("timeoutSeconds", 120))
            checks.append(
                CheckSpec(
                    check_id=str(value.get("id", "configured-" + str(index + 1))),
                    command=tuple(command),
                    cwd=cwd,
                    timeout_seconds=max(1.0, timeout),
                )
            )
        return checks

    package_path = run.workspace / "package.json"
    if package_path.is_file():
        package = json.loads(package_path.read_text(encoding="utf-8"))
        scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
        if isinstance(scripts, dict):
            for name in ("typecheck", "test", "build"):
                if isinstance(scripts.get(name), str):
                    checks.append(CheckSpec(name, _package_command(run.workspace, name, package), run.workspace))

    if (run.workspace / "pyproject.toml").is_file() and (run.workspace / "tests").is_dir():
        checks.append(CheckSpec("pytest", (sys.executable, "-m", "pytest", "-q"), run.workspace))
    if (run.workspace / "Cargo.toml").is_file():
        checks.append(CheckSpec("cargo-test", ("cargo", "test"), run.workspace))
    if (run.workspace / "go.mod").is_file():
        checks.append(CheckSpec("go-test", ("go", "test", "./..."), run.workspace))
    return checks


def _run_check(run: RunState, check: CheckSpec) -> tuple[bool, dict[str, Any]]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            check.command,
            cwd=check.cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=check.timeout_seconds,
            shell=False,
            check=False,
        )
        payload = {
            "criterion": "check:" + check.check_id,
            "command": list(check.command),
            "cwd": str(check.cwd),
            "exitCode": completed.returncode,
            "stdout": completed.stdout[-MAX_CAPTURE_CHARS:],
            "stderr": completed.stderr[-MAX_CAPTURE_CHARS:],
            "durationMs": round((time.monotonic() - started) * 1000),
        }
        return completed.returncode == 0, payload
    except subprocess.TimeoutExpired as error:
        return False, {
            "criterion": "check:" + check.check_id,
            "command": list(check.command),
            "cwd": str(check.cwd),
            "timeoutSeconds": check.timeout_seconds,
            "stdout": str(error.stdout or "")[-MAX_CAPTURE_CHARS:],
            "stderr": str(error.stderr or "")[-MAX_CAPTURE_CHARS:],
            "durationMs": round((time.monotonic() - started) * 1000),
        }
    except OSError as error:
        return False, {
            "criterion": "check:" + check.check_id,
            "command": list(check.command),
            "cwd": str(check.cwd),
            "error": str(error),
            "durationMs": round((time.monotonic() - started) * 1000),
        }


class VerifiedSidecar:
    def __init__(self, state_root: Path | None = None) -> None:
        self.state_root = (state_root or _state_root()).resolve()
        self.runs: dict[str, RunState] = {}

    def _run(self, run_id: str) -> RunState:
        try:
            return self.runs[run_id]
        except KeyError as error:
            raise ProtocolError("run.open must be sent before this request") from error

    def _manifest(self, run: RunState) -> None:
        _atomic_json(
            run.run_dir / "manifest.json",
            {
                "schemaVersion": 2,
                "sidecarProtocolVersion": PROTOCOL_VERSION,
                "executionCoreRevision": run.config.get("executionCoreRevision", "opencode-v1.18.23-fork"),
                "runId": run.run_id,
                "rootScopeId": run.root_scope_id,
                "workspace": str(run.workspace),
                "goalContract": run.goal_contract,
                "status": run.status,
                "scopes": {
                    scope_id: {
                        "parentScopeId": scope.parent_scope_id,
                        "actionCount": len(scope.actions),
                    }
                    for scope_id, scope in run.scopes.items()
                },
                "candidateRefs": run.candidate_refs,
                "evidenceRefs": run.evidence_refs,
                "readyRef": run.ready_ref,
                "runtimeFailure": run.runtime_failure,
                "repairCounts": run.repair_counts,
                "updatedAt": _utc_now(),
            },
        )

    def _status(self, run: RunState, scope_id: str) -> dict[str, Any]:
        return {
            "state": run.status,
            "goal": str(run.goal_contract.get("goal", "")),
            "runId": run.run_id,
            "scopeId": scope_id,
            "rootScopeId": run.root_scope_id,
            "evidenceRefs": run.evidence_refs,
            "candidateRefs": run.candidate_refs,
            "readyRef": run.ready_ref,
            "runtimeFailure": run.runtime_failure,
            "maxSameFailureRepairs": int(
                _verification_config(run).get(
                    "maxSameFailureRepairs",
                    DEFAULT_MAX_SAME_FAILURE_REPAIRS,
                )
            ),
        }

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
                    "action.observe",
                    "verify.request",
                    "status.get",
                    "run.close",
                ],
            }
        if request_type == "run.open":
            workspace_value = payload.get("workspace")
            goal_contract = payload.get("goalContract")
            if not isinstance(workspace_value, str) or not isinstance(goal_contract, dict):
                raise ProtocolError("run.open requires workspace and goalContract")
            acceptance = goal_contract.get("acceptance")
            if not isinstance(goal_contract.get("goal"), str) or not isinstance(acceptance, list) or not acceptance:
                raise ProtocolError("GoalContract requires goal and at least one acceptance criterion")
            workspace = Path(workspace_value).resolve()
            if not workspace.is_dir():
                raise ProtocolError("workspace does not exist")
            token = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16] + "-" + uuid.uuid4().hex[:8]
            run_dir = self.state_root / "runs" / token
            run_dir.mkdir(parents=True, exist_ok=False)
            run = RunState(
                run_id=run_id,
                root_scope_id=scope_id,
                workspace=workspace,
                goal_contract=_redact(goal_contract),
                run_dir=run_dir,
                config=_load_config(workspace),
                scopes={scope_id: ScopeState(scope_id, None)},
            )
            self.runs[run_id] = run
            self._manifest(run)
            return self._status(run, scope_id)

        run = self._run(run_id)
        if request_type == "scope.open":
            parent_scope_id = payload.get("parentScopeId")
            if not isinstance(parent_scope_id, str) or parent_scope_id not in run.scopes:
                raise ProtocolError("scope.open requires an existing parentScopeId")
            if scope_id in run.scopes:
                raise ProtocolError("scopeId is already open")
            run.scopes[scope_id] = ScopeState(scope_id, parent_scope_id)
            self._manifest(run)
            return self._status(run, scope_id)
        if request_type == "action.observe":
            scope = run.scopes.get(scope_id)
            if scope is None:
                raise ProtocolError("scope is not open")
            observation = {
                "scopeId": scope_id,
                "parentScopeId": scope.parent_scope_id,
                "observedAt": _utc_now(),
                **_redact(payload),
            }
            scope.actions.append(observation)
            if payload.get("status") == "error":
                metadata = payload.get("metadata")
                metadata = metadata if isinstance(metadata, dict) else {}
                failure_kind = metadata.get("failureKind")
                run.runtime_failure = {
                    "failureKind": (
                        failure_kind
                        if isinstance(failure_kind, str)
                        else _classify_runtime_failure(payload)
                    ),
                    "scopeId": scope_id,
                    "tool": str(payload.get("tool", "unknown")),
                }
            elif payload.get("status") == "completed":
                run.runtime_failure = None
            reference = _artifact(
                run,
                "evidence_candidate",
                "untrusted_execution_observation",
                observation,
            )
            run.candidate_refs.append(reference)
            run.status = "observing"
            self._manifest(run)
            return self._status(run, scope_id)
        if request_type == "status.get":
            return self._status(run, scope_id)
        if request_type == "verify.request":
            return self._verify(run, scope_id, payload)
        if request_type == "run.close":
            run.status = "closed"
            self._manifest(run)
            return self._status(run, scope_id)
        raise ProtocolError("unsupported request type: " + request_type)

    def _verify(self, run: RunState, scope_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if scope_id not in run.scopes:
            raise ProtocolError("scope is not open")
        if scope_id != run.root_scope_id:
            return {
                **self._status(run, scope_id),
                "outcome": "repair",
                "failureKind": "verification_authority_error",
                "failedCriterion": "root_goal_contract_authority",
                "missingEvidence": ["Only the root scope may issue final Ready."],
                "repairScope": scope_id,
                "repairCount": 0,
            }

        if run.runtime_failure:
            failure_kind = str(run.runtime_failure["failureKind"])
            return self._reject(
                run,
                scope_id,
                "runtime_action_failed",
                [
                    "The latest runtime action failed in scope "
                    + str(run.runtime_failure["scopeId"])
                    + "."
                ],
                "Repair only the failed "
                + str(run.runtime_failure["tool"])
                + " action before requesting verification again.",
                failure_kind=failure_kind,
            )

        all_actions = [action for scope in run.scopes.values() for action in scope.actions]
        if not all_actions:
            return self._reject(
                run,
                scope_id,
                "missing_action_evidence",
                ["No completed tool action has been observed."],
                "Perform the smallest action needed to satisfy the GoalContract.",
            )

        checks = _discover_checks(run)
        if not checks:
            return self._reject(
                run,
                scope_id,
                "missing_verification_strategy",
                ["No configured or safely discoverable verification check exists."],
                "Add verification.checks to base-harness.jsonc for this workspace.",
            )

        failed: list[dict[str, Any]] = []
        evidence_refs: list[dict[str, Any]] = []
        for check in checks:
            passed, result = _run_check(run, check)
            reference = _artifact(
                run,
                "verification_result",
                "verifier_observed",
                {**result, "passed": passed},
            )
            if passed:
                evidence_refs.append(reference)
            else:
                failed.append({**result, "artifact": reference})

        if failed:
            criteria = [str(item["criterion"]) for item in failed]
            return self._reject(
                run,
                scope_id,
                "verification_failed",
                criteria,
                "Repair only the files and behavior implicated by the failed checks.",
                failed,
            )

        run.evidence_refs.extend(
            reference for reference in evidence_refs if reference not in run.evidence_refs
        )
        ready_payload = {
            "goalContract": run.goal_contract,
            "scopeId": scope_id,
            "evidenceRefs": run.evidence_refs,
            "verificationMode": _verification_config(run).get("mode", "adaptive"),
            "requestedBy": _redact(payload),
        }
        run.ready_ref = _artifact(run, "ready", "verifier_attested", ready_payload)
        run.status = "ready"
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

    def _reject(
        self,
        run: RunState,
        scope_id: str,
        failed_criterion: str,
        missing_evidence: list[str],
        repair_scope: str,
        details: list[dict[str, Any]] | None = None,
        failure_kind: str = "verification_failed",
    ) -> dict[str, Any]:
        fingerprint_body = {
            "failureKind": failure_kind,
            "failedCriterion": failed_criterion,
            "missingEvidence": missing_evidence,
            "checks": [
                {
                    "criterion": item.get("criterion"),
                    "exitCode": item.get("exitCode"),
                    "timeoutSeconds": item.get("timeoutSeconds"),
                    "command": item.get("command"),
                }
                for item in (details or [])
            ],
        }
        fingerprint = hashlib.sha256(_canonical_bytes(fingerprint_body)).hexdigest()
        count = run.repair_counts.get(fingerprint, 0) + 1
        run.repair_counts[fingerprint] = count
        maximum = int(
            _verification_config(run).get(
                "maxSameFailureRepairs",
                DEFAULT_MAX_SAME_FAILURE_REPAIRS,
            )
        )
        outcome = "blocked" if count > maximum else "repair"
        run.status = outcome
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
        _artifact(run, "verification_rejection", "verifier_attested", rejection)
        self._manifest(run)
        return {**self._status(run, scope_id), **rejection}


def _response(envelope: dict[str, Any], payload: dict[str, Any], response_type: str = "response") -> dict[str, Any]:
    return {
        "version": PROTOCOL_VERSION,
        "id": str(envelope.get("id", "")),
        "runId": str(envelope.get("runId", "")),
        "scopeId": str(envelope.get("scopeId", "")),
        "type": response_type,
        "payload": payload,
    }


def serve(input_stream: TextIO, output_stream: TextIO, sidecar: VerifiedSidecar | None = None) -> int:
    verifier = sidecar or VerifiedSidecar()
    for line in input_stream:
        if not line.strip():
            continue
        envelope: dict[str, Any] = {}
        try:
            decoded = json.loads(line)
            if not isinstance(decoded, dict):
                raise ProtocolError("NDJSON message must be an object")
            envelope = decoded
            payload = verifier.handle(envelope)
            response = _response(envelope, payload)
        except ProtocolError as error:
            failure_kind = (
                "harness_protocol_version_mismatch"
                if "version mismatch" in str(error)
                else "harness_protocol_error"
            )
            response = _response(
                envelope,
                {
                    "outcome": "failure",
                    "state": "failure",
                    "failureKind": failure_kind,
                    "message": str(error),
                },
                "failure",
            )
        except Exception as error:
            response = _response(
                envelope,
                {
                    "outcome": "failure",
                    "state": "failure",
                    "failureKind": "harness_verifier_error",
                    "message": str(error),
                },
                "failure",
            )
        output_stream.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        output_stream.flush()
    return 0


def main() -> int:
    return serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
