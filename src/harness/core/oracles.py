from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Any, Callable
from pathlib import Path
import hashlib
import json
import os
import shlex

from .sandbox import ExecutionBackend, LocalProcessBackend


@dataclass
class CompletionResult:
    accepted: bool
    reason: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    oracle_id: str | None = None
    independence_level: str = "unknown"
    evidence_hash: str | None = None
    coverage: dict[str, Any] = field(default_factory=dict)


class CompletionOracle(Protocol):
    name: str
    def evaluate(self, *, goal, state, workspace) -> CompletionResult: ...


class NeverAcceptOracle:
    name = "never_accept"

    def __init__(self, reason: str = "no task-native completion oracle configured"):
        self.reason = reason

    def evaluate(self, *, goal, state, workspace):
        return CompletionResult(
            False,
            self.reason,
            oracle_id=self.name,
            independence_level="harness_fixed",
        )


class PredicateCompletionOracle:
    def __init__(self, predicate: Callable, *, name: str = "predicate_oracle"):
        self.predicate = predicate
        self.name = name

    def evaluate(self, *, goal, state, workspace):
        try:
            result = self.predicate(goal=goal, state=state, workspace=workspace)
        except Exception as exc:
            return CompletionResult(
                False,
                f"{type(exc).__name__}: {exc}",
                oracle_id=self.name,
                independence_level="harness_fixed",
            )
        if isinstance(result, CompletionResult):
            if result.oracle_id is None:
                result.oracle_id = self.name
            if result.independence_level == "unknown":
                result.independence_level = "harness_fixed"
            return result
        return CompletionResult(
            bool(result),
            "predicate accepted" if result else "predicate rejected",
            oracle_id=self.name,
            independence_level="harness_fixed",
        )


class CommandCompletionOracle:
    """Operator-fixed command oracle executed through an explicit backend.

    The backend is supplied by CLI/runtime composition. Completion checks can no
    longer instantiate a fresh host-local process and silently bypass the Actor
    sandbox selection.
    """
    name = "command_oracle"

    def __init__(
        self,
        commands: list[str],
        timeout_seconds: float = 120,
        *,
        backend: ExecutionBackend | None = None,
        require_filesystem_isolation: bool = False,
        allow_test_attestation: bool = False,
    ):
        self.commands = list(commands)
        self.timeout_seconds = float(timeout_seconds)
        self.backend = backend or LocalProcessBackend(inherit_env=False)
        self.require_filesystem_isolation = bool(require_filesystem_isolation)
        self.allow_test_attestation = bool(allow_test_attestation)

    def evaluate(self, *, goal, state, workspace):
        if not self.commands:
            return CompletionResult(
                False,
                "no acceptance commands configured",
                oracle_id=self.name,
                independence_level="operator_fixed_unsealed",
            )
        workspace = Path(workspace).expanduser().resolve()
        att = self.backend.isolation_attestation(workspace=workspace)
        trusted_source = (
            att.source == "runtime_probe"
            or (att.source == "test_fixture" and self.allow_test_attestation)
        )
        strong_boundary = att.strong_filesystem_boundary and trusted_source
        independence = (
            "operator_fixed_unsealed_and_filesystem_isolation"
            if strong_boundary
            else "operator_fixed_unsealed"
        )
        attestation = {
            "backend": getattr(self.backend, "name", type(self.backend).__name__),
            "source": att.source,
            "filesystem_isolated": att.filesystem_isolated,
            "network_isolated": att.network_isolated,
            "environment_sanitized": att.environment_sanitized,
        }
        if self.require_filesystem_isolation and not strong_boundary:
            return _finalize_completion_result(
                accepted=False,
                reason="command oracle requires filesystem-isolated backend",
                evidence=[{"sandbox": attestation}],
                oracle_id=self.name,
                independence_level=independence,
            )

        evidence = []
        for command in self.commands:
            result = self.backend.run_shell(
                workspace=workspace,
                command=command,
                timeout_seconds=self.timeout_seconds,
                env=None,
            )
            record = {
                "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
                "returncode": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
                "timed_out": result.timed_out,
                "sandbox": attestation,
            }
            evidence.append(record)
            if result.returncode != 0 or result.timed_out:
                return _finalize_completion_result(
                    accepted=False,
                    reason="acceptance command failed",
                    evidence=evidence,
                    oracle_id=self.name,
                    independence_level=independence,
                )
        return _finalize_completion_result(
            accepted=True,
            reason="all acceptance commands passed",
            evidence=evidence,
            oracle_id=self.name,
            independence_level=independence,
        )


@dataclass(frozen=True)
class SealVerification:
    ok: bool
    manifest_hash: str
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)


class SealedAssetBundle:
    """In-memory baseline of operator-owned acceptance assets.

    The baseline is captured before actor execution.  Any later file mutation,
    deletion, or addition causes oracle rejection.  This provides integrity
    detection even when a strong OS sandbox is unavailable.

    It does NOT provide confidentiality: without an OS/container sandbox, a
    same-UID actor subprocess may still be able to read paths outside workspace.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise ValueError(f"sealed oracle root must be an existing directory: {self.root}")
        self._baseline = self._snapshot()
        self._manifest_hash = self._digest_manifest(self._baseline)
        # Stable identity: reproducible across runs for byte/metadata-identical
        # acceptance bundles.  Security comes from the in-memory baseline and
        # strict trust boundary, not from a random identifier.
        self._seal_id = self._manifest_hash

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _snapshot(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for p in sorted(self.root.rglob("*")):
            rel = p.relative_to(self.root).as_posix()
            if p.is_symlink():
                # Hidden acceptance bundles deliberately reject symlinks.  A
                # symlink can redirect evaluation to actor-controlled content
                # while preserving an apparently stable path name.
                raise ValueError(f"symlinks are not allowed in sealed oracle assets: {rel}")
            st = p.stat()
            mode = st.st_mode & 0o7777
            if p.is_dir():
                out[f"{rel}/"] = {
                    "type": "dir",
                    "mode": mode,
                }
            elif p.is_file():
                out[rel] = {
                    "type": "file",
                    "mode": mode,
                    "sha256": self._hash_file(p),
                    "size": st.st_size,
                }
            else:
                raise ValueError(f"unsupported filesystem entry in sealed oracle assets: {rel}")
        return out

    @staticmethod
    def _digest_manifest(manifest: dict[str, dict[str, Any]]) -> str:
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @property
    def manifest_hash(self) -> str:
        return self._manifest_hash

    @property
    def seal_id(self) -> str:
        return self._seal_id

    def verify_unchanged(self) -> SealVerification:
        try:
            current = self._snapshot()
        except Exception as exc:
            return SealVerification(
                ok=False,
                manifest_hash=self._manifest_hash,
                changed=[f"<snapshot-error:{type(exc).__name__}:{exc}>"],
            )
        changed = sorted(
            k for k in self._baseline.keys() & current.keys()
            if self._baseline[k] != current[k]
        )
        missing = sorted(self._baseline.keys() - current.keys())
        added = sorted(current.keys() - self._baseline.keys())
        ok = not (changed or missing or added)
        return SealVerification(
            ok=ok,
            manifest_hash=self._manifest_hash,
            changed=changed,
            missing=missing,
            added=added,
        )


class SealedCommandCompletionOracle:
    """Integrity-checked completion oracle with operator-owned hidden assets.

    Commands are fixed by the harness operator and may use two placeholders:
      {workspace}   actor workspace path
      {sealed_root} operator-owned acceptance asset path

    Integrity is verified immediately before and immediately after evaluation.
    The actor is never given the command or sealed-root path through the agent
    context.  Confidentiality still requires an OS/container sandbox.
    """

    name = "sealed_command_oracle"
    is_sealed = True

    def __init__(
        self,
        commands: list[str],
        *,
        sealed_root: str | Path,
        timeout_seconds: float = 120,
        backend: ExecutionBackend | None = None,
        require_filesystem_isolation: bool = False,
        allow_test_attestation: bool = False,
    ):
        self.commands = list(commands)
        self.timeout_seconds = timeout_seconds
        self.backend = backend or LocalProcessBackend(inherit_env=False)
        self.bundle = SealedAssetBundle(sealed_root)
        self.require_filesystem_isolation = require_filesystem_isolation
        self.allow_test_attestation = allow_test_attestation
        self.oracle_id = f"{self.name}:{self.bundle.seal_id[:16]}"

    def _result(self, *, accepted, reason, evidence, independence_level, coverage=None):
        return _finalize_completion_result(
            accepted=accepted,
            reason=reason,
            evidence=evidence,
            oracle_id=self.oracle_id,
            independence_level=independence_level,
            coverage=coverage or {},
        )

    def evaluate(self, *, goal, state, workspace):
        if not self.commands:
            return self._result(
                accepted=False,
                reason="no sealed acceptance commands configured",
                evidence=[],
                independence_level="sealed_integrity_only",
            )

        workspace = Path(workspace).expanduser().resolve()
        att = self.backend.isolation_attestation(workspace=workspace)
        trusted_attestation_source = (
            att.source == "runtime_probe"
            or (att.source == "test_fixture" and self.allow_test_attestation)
        )
        strong_boundary = att.strong_filesystem_boundary and trusted_attestation_source
        independence = (
            "sealed_integrity_and_filesystem_isolation"
            if strong_boundary
            else "sealed_integrity_only"
        )

        if self.require_filesystem_isolation and not strong_boundary:
            return self._result(
                accepted=False,
                reason="sealed oracle requires filesystem-isolated backend",
                evidence=[{
                    "sandbox_source": att.source,
                    "filesystem_isolated": att.filesystem_isolated,
                    "environment_sanitized": att.environment_sanitized,
                }],
                independence_level=independence,
            )

        before = self.bundle.verify_unchanged()
        if not before.ok:
            return self._result(
                accepted=False,
                reason="sealed acceptance assets changed before evaluation",
                evidence=[{
                    "manifest_hash": before.manifest_hash,
                    "changed": before.changed,
                    "missing": before.missing,
                    "added": before.added,
                }],
                independence_level=independence,
            )

        evidence: list[dict[str, Any]] = []
        for command_template in self.commands:
            command = (
                command_template
                .replace("{workspace}", shlex.quote(str(workspace)))
                .replace("{sealed_root}", shlex.quote(str(self.bundle.root)))
            )
            result = self.backend.run_shell(
                workspace=workspace,
                command=command,
                timeout_seconds=self.timeout_seconds,
                env=None,
            )
            evidence.append({
                "command_sha256": hashlib.sha256(command_template.encode()).hexdigest(),
                "returncode": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
                "timed_out": result.timed_out,
                "seal_manifest_hash": self.bundle.manifest_hash,
            })
            if result.returncode != 0 or result.timed_out:
                after = self.bundle.verify_unchanged()
                if not after.ok:
                    evidence.append({
                        "seal_violation_after_evaluation": True,
                        "changed": after.changed,
                        "missing": after.missing,
                        "added": after.added,
                    })
                    return self._result(
                        accepted=False,
                        reason="sealed acceptance assets changed during evaluation",
                        evidence=evidence,
                        independence_level=independence,
                    )
                return self._result(
                    accepted=False,
                    reason="sealed acceptance command failed",
                    evidence=evidence,
                    independence_level=independence,
                )

        after = self.bundle.verify_unchanged()
        if not after.ok:
            evidence.append({
                "seal_violation_after_evaluation": True,
                "changed": after.changed,
                "missing": after.missing,
                "added": after.added,
            })
            return self._result(
                accepted=False,
                reason="sealed acceptance assets changed during evaluation",
                evidence=evidence,
                independence_level=independence,
            )

        return self._result(
            accepted=True,
            reason="all sealed acceptance commands passed and assets remained unchanged",
            evidence=evidence,
            independence_level=independence,
            coverage={"commands": len(self.commands)},
        )


def _finalize_completion_result(
    *,
    accepted: bool,
    reason: str,
    evidence: list[dict[str, Any]],
    oracle_id: str,
    independence_level: str,
    coverage: dict[str, Any] | None = None,
) -> CompletionResult:
    canonical = json.dumps(evidence, sort_keys=True, default=str, separators=(",", ":"))
    return CompletionResult(
        accepted=accepted,
        reason=reason,
        evidence=evidence,
        oracle_id=oracle_id,
        independence_level=independence_level,
        evidence_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        coverage=coverage or {},
    )
