from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Any, Sequence, Callable
from enum import Enum
import os
import select
import signal
import subprocess
import time


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


@dataclass(frozen=True)
class SessionIOResult:
    stdout: bytes = b""
    stderr: bytes = b""
    returncode: int | None = None


class ExecutionSession(Protocol):
    def send(self, data: bytes) -> None: ...
    def read(self, *, max_bytes: int = 65536, wait_seconds: float = 0.0) -> SessionIOResult: ...
    def interrupt(self) -> None: ...
    def status(self) -> SessionIOResult: ...
    def close(self) -> SessionIOResult: ...


class ExecutionBackend(Protocol):
    name: str

    def run_shell(
        self,
        *,
        workspace: Path,
        command: str,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult: ...

    def run_argv(
        self,
        *,
        workspace: Path,
        argv: Sequence[str],
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> ExecutionResult: ...

    def open_argv_session(
        self,
        *,
        workspace: Path,
        argv: Sequence[str],
        env: dict[str, str] | None = None,
    ) -> ExecutionSession: ...

    def isolation_attestation(self, *, workspace: Path) -> IsolationAttestation: ...


class PopenExecutionSession:
    """Binary, non-blocking wrapper around a long-lived subprocess.

    The process is started in its own process group so interrupt/close apply to
    the complete launched process tree rather than only a shell wrapper.

    ``wait_seconds`` is a bounded observation window, not merely a wait for the
    first readable byte. A read accumulates stdout/stderr that becomes available
    anywhere in that window. ``wait_seconds=0`` remains an immediate non-blocking
    drain. This avoids losing a command response when startup output becomes
    readable before the later response while still keeping every read bounded.
    """

    def __init__(self, proc: subprocess.Popen[bytes], *, cleanup: Callable[[], None] | None = None):
        self.proc = proc
        self._cleanup = cleanup
        self._closed = False
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                os.set_blocking(stream.fileno(), False)

    @staticmethod
    def _read_fd(stream, limit: int) -> bytes:
        if stream is None or limit <= 0:
            return b""
        chunks: list[bytes] = []
        remaining = limit
        while remaining > 0:
            try:
                chunk = os.read(stream.fileno(), min(remaining, 65536))
            except BlockingIOError:
                break
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def send(self, data: bytes) -> None:
        if self._closed or self.proc.stdin is None:
            raise RuntimeError("session stdin is closed")
        if self.proc.poll() is not None:
            raise RuntimeError("session process has exited")
        view = memoryview(bytes(data))
        while view:
            written = os.write(self.proc.stdin.fileno(), view)
            view = view[written:]

    def read(self, *, max_bytes: int = 65536, wait_seconds: float = 0.0) -> SessionIOResult:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        if not isinstance(wait_seconds, (int, float)) or isinstance(wait_seconds, bool) or wait_seconds < 0:
            raise ValueError("wait_seconds must be non-negative")

        wait_seconds = float(wait_seconds)
        deadline = time.monotonic() + wait_seconds
        active: dict[Any, str] = {
            stream: name
            for name, stream in (("stdout", self.proc.stdout), ("stderr", self.proc.stderr))
            if stream is not None
        }
        chunks: dict[str, list[bytes]] = {"stdout": [], "stderr": []}
        totals = {"stdout": 0, "stderr": 0}

        def drain_available() -> None:
            for stream, name in list(active.items()):
                remaining = max_bytes - totals[name]
                if remaining <= 0:
                    continue
                while remaining > 0:
                    try:
                        chunk = os.read(stream.fileno(), min(remaining, 65536))
                    except BlockingIOError:
                        break
                    except OSError:
                        active.pop(stream, None)
                        break
                    if not chunk:
                        active.pop(stream, None)
                        break
                    chunks[name].append(chunk)
                    totals[name] += len(chunk)
                    remaining -= len(chunk)

        while True:
            drain_available()
            if wait_seconds == 0.0:
                break

            observable = [
                stream
                for stream, name in active.items()
                if totals[name] < max_bytes
            ]
            if not observable:
                break

            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                break

            readable, _, _ = select.select(observable, [], [], remaining_time)
            if not readable:
                break

        # One final non-blocking drain closes the small boundary between the
        # last readiness notification/deadline and result construction.
        drain_available()
        return SessionIOResult(
            stdout=b"".join(chunks["stdout"]),
            stderr=b"".join(chunks["stderr"]),
            returncode=self.proc.poll(),
        )

    def interrupt(self) -> None:
        if self._closed or self.proc.poll() is not None:
            return
        try:
            os.killpg(self.proc.pid, signal.SIGINT)
        except ProcessLookupError:
            return

    def status(self) -> SessionIOResult:
        return SessionIOResult(returncode=self.proc.poll())

    def close(self) -> SessionIOResult:
        if self._closed:
            return SessionIOResult(returncode=self.proc.poll())
        try:
            if self.proc.stdin is not None:
                try:
                    self.proc.stdin.close()
                except OSError:
                    pass
            if self.proc.poll() is None:
                try:
                    os.killpg(self.proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    self.proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(self.proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self.proc.wait(timeout=1.0)
            result = self.read(max_bytes=1024 * 1024, wait_seconds=0.0)
            return SessionIOResult(result.stdout, result.stderr, self.proc.poll())
        finally:
            self._closed = True
            for stream in (self.proc.stdout, self.proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if self._cleanup is not None:
                self._cleanup()
                self._cleanup = None


class LocalProcessBackend:
    """Plain subprocess backend. It deliberately reports no OS sandbox."""

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

    @staticmethod
    def _validate_argv(argv: Sequence[str]) -> list[str]:
        argv = list(argv)
        if not argv or any(not isinstance(item, str) or not item or "\x00" in item for item in argv):
            raise ValueError("argv must contain non-empty NUL-free strings")
        return argv

    def run_shell(self, *, workspace, command, timeout_seconds, env=None):
        try:
            proc = subprocess.run(
                command, cwd=Path(workspace), shell=True, text=True, capture_output=True,
                timeout=timeout_seconds, env=self._env(env, workspace=Path(workspace)),
            )
            return ExecutionResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(124, exc.stdout or "", exc.stderr or "", timed_out=True)

    def run_argv(self, *, workspace, argv, timeout_seconds, env=None):
        try:
            argv = self._validate_argv(argv)
        except ValueError as exc:
            return ExecutionResult(2, "", str(exc))
        try:
            proc = subprocess.run(
                argv, cwd=Path(workspace), shell=False, text=True, capture_output=True,
                timeout=timeout_seconds, env=self._env(env, workspace=Path(workspace)),
            )
            return ExecutionResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(124, exc.stdout or "", exc.stderr or "", timed_out=True)

    def open_argv_session(self, *, workspace, argv, env=None):
        argv = self._validate_argv(argv)
        proc = subprocess.Popen(
            argv,
            cwd=Path(workspace),
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._env(env, workspace=Path(workspace)),
            start_new_session=True,
        )
        return PopenExecutionSession(proc)

    def isolation_attestation(self, *, workspace):
        return IsolationAttestation(
            filesystem_isolated=False,
            network_isolated=False,
            environment_sanitized=not self.inherit_env,
            source="backend_declaration",
            evidence={"cwd_only": True, "note": "cwd is not an OS filesystem sandbox"},
        )


class RecordingIsolatedTestBackend:
    """Test-only backend for policy tests; it never executes arbitrary commands."""

    name = "recording_isolated_test"

    def __init__(self, outcomes: dict[Any, ExecutionResult] | None = None):
        self.outcomes = dict(outcomes or {})
        self.calls: list[dict[str, Any]] = []

    def run_shell(self, *, workspace, command, timeout_seconds, env=None):
        self.calls.append({"workspace": str(Path(workspace).resolve()), "command": command, "timeout_seconds": timeout_seconds})
        return self.outcomes.get(command, ExecutionResult(0, "", ""))

    def run_argv(self, *, workspace, argv, timeout_seconds, env=None):
        argv = tuple(argv)
        self.calls.append({"workspace": str(Path(workspace).resolve()), "argv": list(argv), "timeout_seconds": timeout_seconds})
        return self.outcomes.get(argv, ExecutionResult(0, "", ""))

    def isolation_attestation(self, *, workspace):
        return IsolationAttestation(
            filesystem_isolated=True,
            network_isolated=True,
            environment_sanitized=True,
            source="test_fixture",
            evidence={"warning": "test-only attestation; not production OS evidence"},
        )
