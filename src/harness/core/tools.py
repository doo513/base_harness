from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any
from pathlib import Path
import atexit
import base64
import binascii
import hashlib
import uuid

from .security import Principal, CapabilityPolicy, SecurityViolation, capability_for_side_effect
from .sandbox import ExecutionBackend, LocalProcessBackend, NetworkPolicy


class SideEffect(str, Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"


class ToolSchemaError(ValueError):
    pass


def _schema_value_error(value: Any, schema: dict[str, Any], *, path: str = "$") -> str | None:
    """Validate the small JSON-Schema subset used by harness tool contracts."""
    if not isinstance(schema, dict):
        return f"{path}: schema must be an object"
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or value not in enum:
            return f"{path}: value is not in declared enum"

    expected = schema.get("type")
    type_ok = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
        None: True,
    }.get(expected)
    if type_ok is None:
        return f"{path}: unsupported schema type {expected!r}"
    if not type_ok:
        return f"{path}: expected {expected}"

    if expected == "string":
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if isinstance(min_length, int) and len(value) < min_length:
            return f"{path}: string shorter than minLength"
        if isinstance(max_length, int) and len(value) > max_length:
            return f"{path}: string longer than maxLength"

    if expected == "array":
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            return f"{path}: array shorter than minItems"
        if isinstance(max_items, int) and len(value) > max_items:
            return f"{path}: array longer than maxItems"
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                error = _schema_value_error(item, item_schema, path=f"{path}[{index}]")
                if error:
                    return error

    if expected == "object":
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            return f"{path}: invalid object schema"
        for key in required:
            if key not in value:
                return f"{path}: missing required property {key!r}"
        additional = schema.get("additionalProperties", True)
        if additional is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                return f"{path}: unsupported properties: {', '.join(extras)}"
        for key, item in value.items():
            child = properties.get(key)
            if isinstance(child, dict):
                error = _schema_value_error(item, child, path=f"{path}.{key}")
                if error:
                    return error
    return None


def validate_tool_schema_value(value: Any, schema: dict[str, Any] | None) -> str | None:
    if schema is None:
        return None
    return _schema_value_error(value, schema)


def tool_contract_descriptor(spec: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    input_schema = getattr(spec, "input_schema", None)
    output_schema = getattr(spec, "output_schema", None)
    if isinstance(input_schema, dict):
        result["input_schema"] = input_schema
    if isinstance(output_schema, dict):
        result["output_schema"] = output_schema
    return result


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    side_effect: SideEffect = SideEffect.NONE
    idempotent: bool = True
    permission: str = "auto"
    precondition: Callable[[dict], bool] | None = None
    postcondition: Callable[[Any], bool] | None = None
    failure_modes: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    execution_backend: ExecutionBackend | None = None
    execution_workspace: Path | None = None
    execution_kind: str = field(default="trusted_in_process", init=False)


@dataclass
class SandboxedCommandToolSpec:
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
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    require_zero_exit: bool = True
    execution_kind: str = field(default="sandboxed_command", init=False)

    def __post_init__(self) -> None:
        self.execution_workspace = Path(self.execution_workspace).resolve()
        if self.execution_backend is None: raise ValueError("sandboxed command tool requires an execution backend")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool): raise ValueError("timeout_seconds must be numeric")
        if float(self.timeout_seconds) <= 0: raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = float(self.timeout_seconds)
        if not isinstance(self.command_arg, str) or not self.command_arg.strip(): raise ValueError("command_arg must be a non-empty string")
        if self.side_effect not in {SideEffect.WRITE, SideEffect.EXTERNAL}: raise ValueError("sandboxed command tools must declare WRITE or EXTERNAL side effects")
        if self.input_schema is None:
            self.input_schema = {
                "type": "object",
                "properties": {self.command_arg: {"type": "string", "minLength": 1}},
                "required": [self.command_arg],
                "additionalProperties": False,
            }
        if self.output_schema is None:
            self.output_schema = {
                "type": "object",
                "properties": {
                    "returncode": {"type": "integer"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "timed_out": {"type": "boolean"},
                },
                "required": ["returncode", "stdout", "stderr", "timed_out"],
                "additionalProperties": False,
            }
        self.provenance = dict(self.provenance)
        self.provenance.update({"execution_kind": self.execution_kind, "timeout_seconds": repr(self.timeout_seconds), "command_arg": self.command_arg, "require_zero_exit": "true" if self.require_zero_exit else "false"})

    @property
    def handler(self): return None
    @property
    def precondition(self): return None
    @property
    def postcondition(self): return None


@dataclass
class SandboxedArgvToolSpec:
    name: str
    description: str
    execution_backend: ExecutionBackend
    execution_workspace: Path
    timeout_seconds: float = 60.0
    argv_arg: str = "argv"
    side_effect: SideEffect = SideEffect.WRITE
    idempotent: bool = False
    permission: str = "auto"
    failure_modes: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    require_zero_exit: bool = True
    execution_kind: str = field(default="sandboxed_argv", init=False)

    def __post_init__(self) -> None:
        self.execution_workspace = Path(self.execution_workspace).resolve()
        if self.execution_backend is None: raise ValueError("sandboxed argv tool requires an execution backend")
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool): raise ValueError("timeout_seconds must be numeric")
        if float(self.timeout_seconds) <= 0: raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = float(self.timeout_seconds)
        if not isinstance(self.argv_arg, str) or not self.argv_arg.strip(): raise ValueError("argv_arg must be a non-empty string")
        if self.side_effect not in {SideEffect.WRITE, SideEffect.EXTERNAL}: raise ValueError("sandboxed argv tools must declare WRITE or EXTERNAL side effects")
        if self.input_schema is None:
            self.input_schema = {
                "type": "object",
                "properties": {
                    self.argv_arg: {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                    }
                },
                "required": [self.argv_arg],
                "additionalProperties": False,
            }
        if self.output_schema is None:
            self.output_schema = {
                "type": "object",
                "properties": {
                    "returncode": {"type": "integer"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "timed_out": {"type": "boolean"},
                },
                "required": ["returncode", "stdout", "stderr", "timed_out"],
                "additionalProperties": False,
            }
        self.provenance = dict(self.provenance)
        self.provenance.update({"execution_kind": self.execution_kind, "timeout_seconds": repr(self.timeout_seconds), "argv_arg": self.argv_arg, "require_zero_exit": "true" if self.require_zero_exit else "false"})

    @property
    def handler(self): return None
    @property
    def precondition(self): return None
    @property
    def postcondition(self): return None


@dataclass
class SandboxedSessionToolSpec:
    """Long-lived structured-argv session whose backend owns execution/isolation."""
    name: str
    description: str
    execution_backend: ExecutionBackend
    execution_workspace: Path
    side_effect: SideEffect = SideEffect.EXTERNAL
    idempotent: bool = False
    permission: str = "auto"
    failure_modes: list[str] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    max_read_bytes: int = 1024 * 1024
    max_wait_seconds: float = 5.0
    execution_kind: str = field(default="sandboxed_session", init=False)

    def __post_init__(self) -> None:
        self.execution_workspace = Path(self.execution_workspace).resolve()
        if self.execution_backend is None: raise ValueError("sandboxed session tool requires an execution backend")
        if self.side_effect not in {SideEffect.WRITE, SideEffect.EXTERNAL}: raise ValueError("sandboxed session tools must declare WRITE or EXTERNAL side effects")
        if not isinstance(self.max_read_bytes, int) or isinstance(self.max_read_bytes, bool) or self.max_read_bytes <= 0: raise ValueError("max_read_bytes must be a positive integer")
        if not isinstance(self.max_wait_seconds, (int, float)) or isinstance(self.max_wait_seconds, bool) or self.max_wait_seconds < 0: raise ValueError("max_wait_seconds must be non-negative")
        self.max_wait_seconds = float(self.max_wait_seconds)
        if self.input_schema is None:
            self.input_schema = {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": ["create", "send", "read", "interrupt", "status", "close"]},
                    "session_id": {"type": "string", "minLength": 1},
                    "argv": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1},
                    "data_b64": {"type": "string"},
                    "max_bytes": {"type": "integer"},
                    "wait_seconds": {"type": "number"},
                },
                "required": ["op"],
                "additionalProperties": False,
            }
        self.provenance = dict(self.provenance)
        self.provenance.update({"execution_kind": self.execution_kind, "max_read_bytes": str(self.max_read_bytes), "max_wait_seconds": repr(self.max_wait_seconds), "resume_policy": "ephemeral_fail_closed"})

    @property
    def handler(self): return None
    @property
    def precondition(self): return None
    @property
    def postcondition(self): return None


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
    def __init__(
        self,
        tools: dict[str, ToolSpec | SandboxedCommandToolSpec | SandboxedArgvToolSpec | SandboxedSessionToolSpec],
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
        self._sessions: dict[str, tuple[str, Any, Any]] = {}
        atexit.register(self.close_sessions)

    def _check_capability(self, spec) -> str | None:
        try:
            self.capability_policy.require(self.principal, capability_for_side_effect(spec.side_effect.value))
        except SecurityViolation as exc:
            return str(exc)
        return None

    def _check_permission(self, call: ToolCall, spec) -> ToolResult | None:
        if spec.permission not in {"auto", "confirm", "deny"}: return ToolResult(False, error=f"invalid permission policy: {spec.permission}")
        if spec.permission == "deny": return ToolResult(False, error="permission denied")
        if spec.permission == "confirm":
            approved = bool(self.approval_checker and self.approval_checker(call, spec))
            if not approved: return ToolResult(False, error="approval required", approval_required=True)
        return None

    def _check_isolation(self, spec) -> tuple[str | None, dict[str, Any] | None]:
        if not self.strict_isolation or spec.side_effect not in {SideEffect.WRITE, SideEffect.EXTERNAL}: return None, None
        declarative = (SandboxedCommandToolSpec, SandboxedArgvToolSpec, SandboxedSessionToolSpec)
        if not isinstance(spec, declarative):
            return (
                "strict isolation forbids generic in-process WRITE/EXTERNAL tools; "
                "use SandboxedCommandToolSpec, SandboxedArgvToolSpec, or SandboxedSessionToolSpec "
                "so the attested backend owns execution",
                None,
            )
        backend = spec.execution_backend
        att = backend.isolation_attestation(workspace=spec.execution_workspace)
        att_dict = {"filesystem_isolated": att.filesystem_isolated, "network_isolated": att.network_isolated, "environment_sanitized": att.environment_sanitized, "source": att.source, "evidence": att.evidence, "execution_kind": spec.execution_kind, "backend_name": getattr(backend, "name", type(backend).__name__)}
        if att.source == "test_fixture":
            if not self.allow_test_attestation: return "test-only isolation attestation is not allowed in production mode", att_dict
        elif att.source != "runtime_probe":
            return "strict isolation requires filesystem isolation backed by a live runtime-probe attestation", att_dict
        if not att.strong_filesystem_boundary: return "strict isolation requires filesystem isolation and sanitized environment", att_dict
        if self.network_policy == NetworkPolicy.DENY and not att.network_isolated: return "network policy DENY requires network-isolated backend", att_dict
        return None, att_dict

    @staticmethod
    def _command_from_call(spec: SandboxedCommandToolSpec, call: ToolCall):
        if set(call.args) != {spec.command_arg}: return None, f"sandboxed command args must contain exactly {spec.command_arg!r}"
        command = call.args.get(spec.command_arg)
        if not isinstance(command, str) or not command.strip(): return None, "command must be a non-empty string"
        return command, None

    @staticmethod
    def _argv_value(value):
        if not isinstance(value, list) or not value: return None, "argv must be a non-empty list"
        if any(not isinstance(item, str) or not item or "\x00" in item for item in value): return None, "argv must contain non-empty NUL-free strings"
        return list(value), None

    @classmethod
    def _argv_from_call(cls, spec: SandboxedArgvToolSpec, call: ToolCall):
        if set(call.args) != {spec.argv_arg}: return None, f"sandboxed argv args must contain exactly {spec.argv_arg!r}"
        return cls._argv_value(call.args.get(spec.argv_arg))

    @staticmethod
    def _result_output(result):
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "timed_out": result.timed_out}

    @staticmethod
    def _session_output(result, *, session_id: str | None = None):
        out = {"stdout_b64": base64.b64encode(result.stdout).decode("ascii"), "stderr_b64": base64.b64encode(result.stderr).decode("ascii"), "returncode": result.returncode}
        if session_id is not None: out["session_id"] = session_id
        return out

    def _execute_sandboxed_command(self, spec, call, *, isolation):
        command, error = self._command_from_call(spec, call)
        if error: return ToolResult(False, error=error, isolation=isolation)
        try: result = spec.execution_backend.run_shell(workspace=spec.execution_workspace, command=command, timeout_seconds=spec.timeout_seconds, env=None)
        except Exception as exc: return ToolResult(False, error=f"{type(exc).__name__}: {exc}", isolation=isolation)
        output = self._result_output(result)
        if spec.require_zero_exit and (result.returncode != 0 or result.timed_out): return ToolResult(False, output=output, error="postcondition failed", isolation=isolation)
        output_error = validate_tool_schema_value(output, spec.output_schema)
        if output_error: return ToolResult(False, output=output, error=f"output schema validation failed: {output_error}", isolation=isolation)
        return ToolResult(True, output=output, isolation=isolation)

    def _execute_sandboxed_argv(self, spec, call, *, isolation):
        argv, error = self._argv_from_call(spec, call)
        if error: return ToolResult(False, error=error, isolation=isolation)
        try: result = spec.execution_backend.run_argv(workspace=spec.execution_workspace, argv=argv, timeout_seconds=spec.timeout_seconds, env=None)
        except Exception as exc: return ToolResult(False, error=f"{type(exc).__name__}: {exc}", isolation=isolation)
        output = self._result_output(result)
        if spec.require_zero_exit and (result.returncode != 0 or result.timed_out): return ToolResult(False, output=output, error="postcondition failed", isolation=isolation)
        output_error = validate_tool_schema_value(output, spec.output_schema)
        if output_error: return ToolResult(False, output=output, error=f"output schema validation failed: {output_error}", isolation=isolation)
        return ToolResult(True, output=output, isolation=isolation)

    def _owned_session(self, spec, session_id: Any):
        if not isinstance(session_id, str) or not session_id: return None, "session_id must be a non-empty string"
        bound = self._sessions.get(session_id)
        if bound is None: return None, "unknown or expired session_id"
        tool_name, backend, session = bound
        if tool_name != spec.name or backend is not spec.execution_backend: return None, "session is not owned by this tool/backend"
        return session, None

    def _execute_sandboxed_session(self, spec: SandboxedSessionToolSpec, call: ToolCall, *, isolation):
        op = call.args.get("op") if isinstance(call.args, dict) else None
        try:
            if op == "create":
                if set(call.args) != {"op", "argv"}: return ToolResult(False, error="session create requires exactly op, argv", isolation=isolation)
                argv, error = self._argv_value(call.args.get("argv"))
                if error: return ToolResult(False, error=error, isolation=isolation)
                session = spec.execution_backend.open_argv_session(workspace=spec.execution_workspace, argv=argv, env=None)
                session_id = uuid.uuid4().hex
                self._sessions[session_id] = (spec.name, spec.execution_backend, session)
                return ToolResult(True, output=self._session_output(session.status(), session_id=session_id), isolation=isolation)

            if op in {"send", "read", "interrupt", "status", "close"}:
                session, error = self._owned_session(spec, call.args.get("session_id"))
                if error:
                    security = "not owned" in error
                    return ToolResult(False, error=error, security_violation=security, isolation=isolation)
                session_id = call.args["session_id"]
                if op == "send":
                    if set(call.args) != {"op", "session_id", "data_b64"}: return ToolResult(False, error="session send requires exactly op, session_id, data_b64", isolation=isolation)
                    data_b64 = call.args.get("data_b64")
                    if not isinstance(data_b64, str): return ToolResult(False, error="data_b64 must be a string", isolation=isolation)
                    try: data = base64.b64decode(data_b64, validate=True)
                    except (binascii.Error, ValueError): return ToolResult(False, error="data_b64 is not valid base64", isolation=isolation)
                    session.send(data)
                    return ToolResult(True, output={"session_id": session_id, "input_sha256": hashlib.sha256(data).hexdigest(), "bytes_sent": len(data)}, isolation=isolation)
                if op == "read":
                    allowed = {"op", "session_id", "max_bytes", "wait_seconds"}
                    if set(call.args) - allowed: return ToolResult(False, error="session read has unsupported arguments", isolation=isolation)
                    max_bytes = call.args.get("max_bytes", 65536); wait_seconds = call.args.get("wait_seconds", 0.0)
                    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0 or max_bytes > spec.max_read_bytes: return ToolResult(False, error="max_bytes is outside tool bounds", isolation=isolation)
                    if not isinstance(wait_seconds, (int, float)) or isinstance(wait_seconds, bool) or wait_seconds < 0 or float(wait_seconds) > spec.max_wait_seconds: return ToolResult(False, error="wait_seconds is outside tool bounds", isolation=isolation)
                    return ToolResult(True, output=self._session_output(session.read(max_bytes=max_bytes, wait_seconds=float(wait_seconds)), session_id=session_id), isolation=isolation)
                if set(call.args) != {"op", "session_id"}: return ToolResult(False, error=f"session {op} requires exactly op, session_id", isolation=isolation)
                if op == "interrupt":
                    session.interrupt(); return ToolResult(True, output=self._session_output(session.status(), session_id=session_id), isolation=isolation)
                if op == "status": return ToolResult(True, output=self._session_output(session.status(), session_id=session_id), isolation=isolation)
                result = session.close(); self._sessions.pop(session_id, None)
                return ToolResult(True, output=self._session_output(result, session_id=session_id), isolation=isolation)
            return ToolResult(False, error="session op must be create|send|read|interrupt|status|close", isolation=isolation)
        except Exception as exc:
            return ToolResult(False, error=f"{type(exc).__name__}: {exc}", isolation=isolation)

    def close_sessions(self) -> None:
        for session_id, (_, _, session) in list(self._sessions.items()):
            try: session.close()
            except Exception: pass
            self._sessions.pop(session_id, None)

    def execute(self, call: ToolCall):
        spec = self.tools.get(call.tool)
        if not spec: return ToolResult(False, error=f"unknown tool: {call.tool}")
        if not isinstance(call.args, dict): return ToolResult(False, error="tool args must be an object")
        input_error = validate_tool_schema_value(call.args, getattr(spec, "input_schema", None))
        if input_error: return ToolResult(False, error=f"input schema validation failed: {input_error}")
        capability_error = self._check_capability(spec)
        if capability_error: return ToolResult(False, error=capability_error, security_violation=True)
        permission_result = self._check_permission(call, spec)
        if permission_result is not None: return permission_result
        isolation_error, isolation = self._check_isolation(spec)
        if isolation_error: return ToolResult(False, error=isolation_error, security_violation=True, isolation=isolation)
        if isinstance(spec, SandboxedCommandToolSpec): return self._execute_sandboxed_command(spec, call, isolation=isolation)
        if isinstance(spec, SandboxedArgvToolSpec): return self._execute_sandboxed_argv(spec, call, isolation=isolation)
        if isinstance(spec, SandboxedSessionToolSpec): return self._execute_sandboxed_session(spec, call, isolation=isolation)
        if spec.precondition:
            try:
                if not spec.precondition(call.args): return ToolResult(False, error="precondition failed", isolation=isolation)
            except Exception as exc: return ToolResult(False, error=f"precondition error: {type(exc).__name__}: {exc}", isolation=isolation)
        try: out = spec.handler(**call.args)
        except Exception as exc: return ToolResult(False, error=f"{type(exc).__name__}: {exc}", isolation=isolation)
        if spec.postcondition:
            try:
                if not spec.postcondition(out): return ToolResult(False, output=out, error="postcondition failed", isolation=isolation)
            except Exception as exc: return ToolResult(False, output=out, error=f"postcondition error: {type(exc).__name__}: {exc}", isolation=isolation)
        output_error = validate_tool_schema_value(out, getattr(spec, "output_schema", None))
        if output_error: return ToolResult(False, output=out, error=f"output schema validation failed: {output_error}", isolation=isolation)
        return ToolResult(True, output=out, isolation=isolation)


def make_shell_tool(workspace: str | Path, timeout_seconds: float = 60, *, backend: ExecutionBackend | None = None) -> SandboxedCommandToolSpec:
    workspace = Path(workspace).resolve(); backend = backend or LocalProcessBackend(inherit_env=False)
    return SandboxedCommandToolSpec(name="shell", description="Run a shell command in the configured workspace and return returncode/stdout/stderr.", execution_backend=backend, execution_workspace=workspace, timeout_seconds=timeout_seconds, side_effect=SideEffect.WRITE, idempotent=False, failure_modes=["nonzero_exit", "timeout", "invalid_command", "sandbox_violation"], provenance={"kind": "local_environment", "backend": backend.name}, require_zero_exit=True)


def make_argv_tool(workspace: str | Path, timeout_seconds: float = 60, *, backend: ExecutionBackend | None = None) -> SandboxedArgvToolSpec:
    workspace = Path(workspace).resolve(); backend = backend or LocalProcessBackend(inherit_env=False)
    return SandboxedArgvToolSpec(name="argv", description="Run structured argv in the configured workspace without Actor-controlled shell interpolation.", execution_backend=backend, execution_workspace=workspace, timeout_seconds=timeout_seconds, side_effect=SideEffect.WRITE, idempotent=False, failure_modes=["nonzero_exit", "timeout", "invalid_argv", "sandbox_violation"], provenance={"kind": "local_environment", "backend": backend.name}, require_zero_exit=True)


def make_session_tool(workspace: str | Path, *, backend: ExecutionBackend | None = None, side_effect: SideEffect = SideEffect.EXTERNAL) -> SandboxedSessionToolSpec:
    workspace = Path(workspace).resolve(); backend = backend or LocalProcessBackend(inherit_env=False)
    return SandboxedSessionToolSpec(name="session", description="Manage a persistent structured-argv process session through the attested backend.", execution_backend=backend, execution_workspace=workspace, side_effect=side_effect, idempotent=False, failure_modes=["process_exit", "invalid_session", "timeout", "sandbox_violation", "resume_session_expired"], provenance={"kind": "local_environment", "backend": backend.name})
