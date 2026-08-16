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
    """Trusted in-process/legacy tool specification.

    This type is intentionally *not* an attested sandbox execution object.
    In strict isolation, WRITE/EXTERNAL tools using this type are rejected even
    if an `execution_backend` field is populated: metadata about one backend may
    not authorize an unrelated in-process handler.
    """

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
    # Compatibility metadata only for this legacy type. Strict side-effect
    # execution never trusts it as proof that `handler` ran through the backend.
    execution_backend: ExecutionBackend | None = None
    execution_workspace: Path | None = None
    execution_kind: str = field(default="trusted_in_process", init=False)


@dataclass
class SandboxedCommandToolSpec:
    """Declarative command tool whose execution is owned by ActionRuntime.

    There is deliberately no arbitrary handler/precondition/postcondition
    callable on the command-execution path. The exact backend object inspected
    for isolation is also the object Runtime invokes for execution.
    """

    name: str
    description: str
    execution_backend: ExecutionBackend
    execution_workspace: Path
    timeout_seconds: float = 60.0
    command_arg: str = "command"
    side_effect: SideEffect = SideEffect.WRITE
    idempotent: bool = False
    permission: str = "auto"
    failure_modes: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    require_zero_exit: bool = True
    execution_kind: str = field(default="sandboxed_command", init=False)

    def __post_init__(self) -> None:
        self.execution_workspace = Path(self.execution_workspace).resolve()
        if self.execution_backend is None:
            raise ValueError("sandboxed command tool requires an execution backend")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool):
            raise ValueError("timeout_seconds must be numeric")
        if float(self.timeout_seconds) <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = float(self.timeout_seconds)
        if not isinstance(self.command_arg, str) or not self.command_arg.strip():
            raise ValueError("command_arg must be a non-empty string")
        if self.side_effect not in {SideEffect.WRITE, SideEffect.EXTERNAL}:
            raise ValueError("sandboxed command tools must declare WRITE or EXTERNAL side effects")

        # Existing run provenance already fingerprints ToolSpec.provenance. Put
        # the declarative execution semantics there so replacing the old handler
        # closure does not weaken Stage-03 resume/config drift detection.
        self.provenance = dict(self.provenance)
        self.provenance.update({
            "execution_kind": self.execution_kind,
            "timeout_seconds": repr(self.timeout_seconds),
            "command_arg": self.command_arg,
            "require_zero_exit": "true" if self.require_zero_exit else "false",
        })

    # Compatibility properties keep persistence/context descriptor code generic
    # without introducing executable callables into this spec.
    @property
    def handler(self):
        return None

    @property
    def precondition(self):
        return None

    @property
    def postcondition(self):
        return None


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
    - strict WRITE/EXTERNAL execution must use a `SandboxedCommandToolSpec`;
    - the same backend object that produces isolation attestation is invoked by
      Runtime for the command; generic in-process handlers cannot borrow a safe
      backend's metadata;
    - network DENY additionally requires a backend that reports network isolation.

    A backend attestation is not assumed to be strong production evidence unless
    its source is a real runtime/sandbox probe. Test fixtures are accepted only
    when `allow_test_attestation=True`.
    """

    def __init__(
        self,
        tools: dict[str, ToolSpec | SandboxedCommandToolSpec],
        approval_checker: Callable[[ToolCall, Any], bool] | None = None,
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

    def _check_capability(self, spec) -> str | None:
        try:
            required = capability_for_side_effect(spec.side_effect.value)
            self.capability_policy.require(self.principal, required)
        except SecurityViolation as exc:
            return str(exc)
        return None

    def _check_permission(self, call: ToolCall, spec) -> ToolResult | None:
        if spec.permission not in {"auto", "confirm", "deny"}:
            return ToolResult(False, error=f"invalid permission policy: {spec.permission}")
        if spec.permission == "deny":
            return ToolResult(False, error="permission denied")
        if spec.permission == "confirm":
            approved = bool(self.approval_checker and self.approval_checker(call, spec))
            if not approved:
                return ToolResult(False, error="approval required", approval_required=True)
        return None

    def _check_isolation(self, spec) -> tuple[str | None, dict[str, Any] | None]:
        if not self.strict_isolation:
            return None, None

        if spec.side_effect not in {SideEffect.WRITE, SideEffect.EXTERNAL}:
            return None, None

        # This is the critical binding rule. A generic handler may not borrow an
        # attestation from a backend it does not structurally execute through.
        if not isinstance(spec, SandboxedCommandToolSpec):
            return (
                "strict isolation forbids generic in-process WRITE/EXTERNAL tools; "
                "use SandboxedCommandToolSpec so the attested backend owns execution",
                None,
            )

        backend = spec.execution_backend
        att = backend.isolation_attestation(workspace=spec.execution_workspace)
        att_dict = {
            "filesystem_isolated": att.filesystem_isolated,
            "network_isolated": att.network_isolated,
            "environment_sanitized": att.environment_sanitized,
            "source": att.source,
            "evidence": att.evidence,
            "execution_kind": spec.execution_kind,
            "backend_name": getattr(backend, "name", type(backend).__name__),
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

    @staticmethod
    def _command_from_call(spec: SandboxedCommandToolSpec, call: ToolCall) -> tuple[str | None, str | None]:
        if set(call.args) != {spec.command_arg}:
            return None, f"sandboxed command args must contain exactly {spec.command_arg!r}"
        command = call.args.get(spec.command_arg)
        if not isinstance(command, str) or not command.strip():
            return None, "command must be a non-empty string"
        return command, None

    def _execute_sandboxed_command(
        self,
        spec: SandboxedCommandToolSpec,
        call: ToolCall,
        *,
        isolation: dict[str, Any] | None,
    ) -> ToolResult:
        command, error = self._command_from_call(spec, call)
        if error:
            return ToolResult(False, error=error, isolation=isolation)
        assert command is not None

        # Backend object identity is not reconstructed between check and use.
        # The exact object referenced by `spec.execution_backend` above is called.
        backend = spec.execution_backend
        try:
            result = backend.run_shell(
                workspace=spec.execution_workspace,
                command=command,
                timeout_seconds=spec.timeout_seconds,
                env=None,
            )
        except Exception as exc:
            return ToolResult(
                False,
                error=f"{type(exc).__name__}: {exc}",
                isolation=isolation,
            )

        output = {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
        }
        if spec.require_zero_exit and (result.returncode != 0 or result.timed_out):
            return ToolResult(False, output=output, error="postcondition failed", isolation=isolation)
        return ToolResult(True, output=output, isolation=isolation)

    def execute(self, call: ToolCall):
        spec = self.tools.get(call.tool)
        if not spec:
            return ToolResult(False, error=f"unknown tool: {call.tool}")

        capability_error = self._check_capability(spec)
        if capability_error:
            return ToolResult(False, error=capability_error, security_violation=True)

        permission_result = self._check_permission(call, spec)
        if permission_result is not None:
            return permission_result

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

        if isinstance(spec, SandboxedCommandToolSpec):
            return self._execute_sandboxed_command(spec, call, isolation=isolation)

        # Legacy/trusted in-process tools remain available outside the strict
        # side-effect boundary. Their registration is part of the trusted harness
        # configuration and they are not described as sandboxed execution.
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
                    return ToolResult(False, output=out, error="postcondition failed", isolation=isolation)
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
) -> SandboxedCommandToolSpec:
    workspace = Path(workspace).resolve()
    backend = backend or LocalProcessBackend(inherit_env=False)
    return SandboxedCommandToolSpec(
        name="shell",
        description="Run a shell command in the configured workspace and return returncode/stdout/stderr.",
        execution_backend=backend,
        execution_workspace=workspace,
        timeout_seconds=timeout_seconds,
        side_effect=SideEffect.WRITE,
        idempotent=False,
        failure_modes=["nonzero_exit", "timeout", "invalid_command", "sandbox_violation"],
        provenance={"kind": "local_environment", "backend": backend.name},
        require_zero_exit=True,
    )
