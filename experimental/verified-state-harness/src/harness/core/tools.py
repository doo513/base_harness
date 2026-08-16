from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any
from pathlib import Path

from .security import (
    Principal,
    CapabilityPolicy,
    SecurityViolation,
    capability_for_side_effect,
)
from .sandbox import (
    ExecutionBackend,
    LocalProcessBackend,
    NetworkPolicy,
)


class SideEffect(str, Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    side_effect: SideEffect = SideEffect.NONE
    idempotent: bool = True
    permission: str = "auto"  # auto | confirm | deny
    precondition: Callable[[dict], bool] | None = None
    postcondition: Callable[[Any], bool] | None = None
    failure_modes: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    execution_backend: ExecutionBackend | None = None
    execution_workspace: Path | None = None


@dataclass
class ToolCall:
    tool: str
    args: dict


@dataclass
class ToolResult:
    ok: bool
    output: Any = None
    error: str | None = None
    approval_required: bool = False
    security_violation: bool = False
    isolation: dict[str, Any] | None = None


class ActionRuntime:
    """Policy-enforcing tool runtime.

    Security semantics:
    - capabilities are checked for the caller principal;
    - `permission="confirm"` is fail-closed without explicit approval;
    - strict isolation refuses WRITE/EXTERNAL tools unless the tool's backend
      reports a strong filesystem boundary;
    - network DENY additionally requires a backend that reports network isolation.

    A backend attestation is not assumed to be strong production evidence unless
    its source is a real runtime/sandbox probe.  Test fixtures are accepted only
    when `allow_test_attestation=True`.
    """

    def __init__(
        self,
        tools: dict[str, ToolSpec],
        approval_checker: Callable[[ToolCall, ToolSpec], bool] | None = None,
        *,
        capability_policy: CapabilityPolicy | None = None,
        principal: Principal = Principal.ACTOR,
        strict_isolation: bool = False,
        network_policy: NetworkPolicy = NetworkPolicy.ALLOW,
        allow_test_attestation: bool = False,
    ):
        self.tools = tools
        self.approval_checker = approval_checker
        self.capability_policy = capability_policy or CapabilityPolicy.default()
        self.principal = principal
        self.strict_isolation = strict_isolation
        self.network_policy = network_policy
        self.allow_test_attestation = allow_test_attestation

    def _check_capability(self, spec: ToolSpec) -> str | None:
        try:
            required = capability_for_side_effect(spec.side_effect.value)
            self.capability_policy.require(self.principal, required)
        except SecurityViolation as exc:
            return str(exc)
        return None

    def _check_isolation(self, spec: ToolSpec) -> tuple[str | None, dict[str, Any] | None]:
        if not self.strict_isolation:
            return None, None

        if spec.side_effect not in {SideEffect.WRITE, SideEffect.EXTERNAL}:
            return None, None

        if spec.execution_backend is None:
            return "strict isolation requires an execution backend", None

        att = spec.execution_backend.isolation_attestation(
            workspace=(spec.execution_workspace or Path(".")).resolve()
        )
        att_dict = {
            "filesystem_isolated": att.filesystem_isolated,
            "network_isolated": att.network_isolated,
            "environment_sanitized": att.environment_sanitized,
            "source": att.source,
            "evidence": att.evidence,
        }

        if att.source == "test_fixture":
            if not self.allow_test_attestation:
                return "test-only isolation attestation is not allowed in production mode", att_dict
        elif att.source != "runtime_probe":
            return "strict isolation requires filesystem isolation backed by a live runtime-probe attestation", att_dict

        if not att.strong_filesystem_boundary:
            return "strict isolation requires filesystem isolation and sanitized environment", att_dict

        if self.network_policy == NetworkPolicy.DENY and not att.network_isolated:
            return "network policy DENY requires network-isolated backend", att_dict

        return None, att_dict

    def execute(self, call: ToolCall):
        spec = self.tools.get(call.tool)
        if not spec:
            return ToolResult(False, error=f"unknown tool: {call.tool}")

        capability_error = self._check_capability(spec)
        if capability_error:
            return ToolResult(
                False,
                error=capability_error,
                security_violation=True,
            )

        if spec.permission not in {"auto", "confirm", "deny"}:
            return ToolResult(False, error=f"invalid permission policy: {spec.permission}")

        if spec.permission == "deny":
            return ToolResult(False, error="permission denied")

        if spec.permission == "confirm":
            approved = bool(self.approval_checker and self.approval_checker(call, spec))
            if not approved:
                return ToolResult(False, error="approval required", approval_required=True)

        if not isinstance(call.args, dict):
            return ToolResult(False, error="tool args must be an object")

        isolation_error, isolation = self._check_isolation(spec)
        if isolation_error:
            return ToolResult(
                False,
                error=isolation_error,
                security_violation=True,
                isolation=isolation,
            )

        if spec.precondition:
            try:
                if not spec.precondition(call.args):
                    return ToolResult(False, error="precondition failed", isolation=isolation)
            except Exception as exc:
                return ToolResult(
                    False,
                    error=f"precondition error: {type(exc).__name__}: {exc}",
                    isolation=isolation,
                )

        try:
            out = spec.handler(**call.args)
        except Exception as exc:
            return ToolResult(
                False,
                error=f"{type(exc).__name__}: {exc}",
                isolation=isolation,
            )

        if spec.postcondition:
            try:
                if not spec.postcondition(out):
                    return ToolResult(
                        False,
                        output=out,
                        error="postcondition failed",
                        isolation=isolation,
                    )
            except Exception as exc:
                return ToolResult(
                    False,
                    output=out,
                    error=f"postcondition error: {type(exc).__name__}: {exc}",
                    isolation=isolation,
                )

        return ToolResult(True, output=out, isolation=isolation)


def make_shell_tool(
    workspace: str | Path,
    timeout_seconds: float = 60,
    *,
    backend: ExecutionBackend | None = None,
) -> ToolSpec:
    workspace = Path(workspace).resolve()
    backend = backend or LocalProcessBackend(inherit_env=False)

    def shell(command: str) -> dict:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command must be a non-empty string")
        result = backend.run_shell(
            workspace=workspace,
            command=command,
            timeout_seconds=timeout_seconds,
            env=None,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
        }

    return ToolSpec(
        name="shell",
        description="Run a shell command in the configured workspace and return returncode/stdout/stderr.",
        handler=shell,
        side_effect=SideEffect.WRITE,
        idempotent=False,
        postcondition=lambda out: (
            isinstance(out, dict)
            and out.get("returncode") == 0
            and not out.get("timed_out", False)
        ),
        failure_modes=["nonzero_exit", "timeout", "invalid_command", "sandbox_violation"],
        provenance={"kind": "local_environment", "backend": backend.name},
        execution_backend=backend,
        execution_workspace=workspace,
    )
