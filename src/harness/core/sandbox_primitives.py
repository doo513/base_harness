from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Any, Sequence
from enum import Enum
import os
import subprocess


class NetworkPolicy(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class IsolationAttestation:
    filesystem_isolated: bool
    network_isolated: bool
    environment_sanitized: bool
    source: str
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def strong_filesystem_boundary(self) -> bool:
        return self.filesystem_isolated and self.environment_sanitized


@dataclass
class ExecutionResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


class ExecutionBackend(Protocol):
    name: str

    def run_shell(
        self,
        *,
        workspace: Path,
        command: str,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        ...

    def run_argv(
        self,
        *,
        workspace: Path,
        argv: Sequence[str],
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        ...

    def isolation_attestation(self, *, workspace: Path) -> IsolationAttestation:
        ...


class LocalProcessBackend:
    """Plain subprocess backend.

    It deliberately reports filesystem/network isolation as false. This makes
    strict mode fail closed rather than pretending cwd is a sandbox.
    """

    name = "local_process"

    def __init__(self, *, inherit_env: bool = False):
        self.inherit_env = inherit_env

    def _env(self, supplied: dict[str, str] | None, *, workspace: Path) -> dict[str, str]:
        if self.inherit_env:
            base = dict(os.environ)
        else:
            base = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(Path(workspace).resolve()),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
            }
        if supplied:
            base.update({str(k): str(v) for k, v in supplied.items()})
        return base

    def run_shell(self, *, workspace, command, timeout_seconds, env=None):
        try:
            proc = subprocess.run(
                command,
                cwd=Path(workspace),
                shell=True,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                env=self._env(env, workspace=Path(workspace)),
            )
            return ExecutionResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(124, exc.stdout or "", exc.stderr or "", timed_out=True)

    def run_argv(self, *, workspace, argv, timeout_seconds, env=None):
        argv = list(argv)
        if not argv or any(not isinstance(item, str) or not item or "\x00" in item for item in argv):
            return ExecutionResult(2, "", "argv must contain non-empty NUL-free strings")
        try:
            proc = subprocess.run(
                argv,
                cwd=Path(workspace),
                shell=False,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                env=self._env(env, workspace=Path(workspace)),
            )
            return ExecutionResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(124, exc.stdout or "", exc.stderr or "", timed_out=True)

    def isolation_attestation(self, *, workspace):
        return IsolationAttestation(
            filesystem_isolated=False,
            network_isolated=False,
            environment_sanitized=not self.inherit_env,
            source="backend_declaration",
            evidence={"cwd_only": True, "note": "cwd is not an OS filesystem sandbox"},
        )


class RecordingIsolatedTestBackend:
    """Test-only backend.

    It does not execute arbitrary commands. Tests inject deterministic outcomes
    while exercising policy code that requires a positively attested backend.
    """

    name = "recording_isolated_test"

    def __init__(self, outcomes: dict[Any, ExecutionResult] | None = None):
        self.outcomes = dict(outcomes or {})
        self.calls: list[dict[str, Any]] = []

    def run_shell(self, *, workspace, command, timeout_seconds, env=None):
        self.calls.append({
            "workspace": str(Path(workspace).resolve()),
            "command": command,
            "timeout_seconds": timeout_seconds,
        })
        return self.outcomes.get(command, ExecutionResult(0, "", ""))

    def run_argv(self, *, workspace, argv, timeout_seconds, env=None):
        argv = tuple(argv)
        self.calls.append({
            "workspace": str(Path(workspace).resolve()),
            "argv": list(argv),
            "timeout_seconds": timeout_seconds,
        })
        return self.outcomes.get(argv, ExecutionResult(0, "", ""))

    def isolation_attestation(self, *, workspace):
        return IsolationAttestation(
            filesystem_isolated=True,
            network_isolated=True,
            environment_sanitized=True,
            source="test_fixture",
            evidence={"warning": "test-only attestation; not production OS evidence"},
        )
