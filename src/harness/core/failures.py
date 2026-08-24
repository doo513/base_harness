from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import hashlib
import re


class FailureKind(str, Enum):
    TOOL_ERROR = "tool_error"
    ENV_ERROR = "env_error"
    MISSING_INFO = "missing_info"
    HYPOTHESIS_REFUTED = "hypothesis_refuted"
    MODEL_PROVIDER_ERROR = "model_provider_error"
    MODEL_PROTOCOL_ERROR = "model_protocol_error"
    ACTOR_WORKFLOW_ERROR = "actor_workflow_error"
    IMPLEMENTATION_ERROR = "implementation_error"
    NO_PROGRESS = "no_progress"
    STRATEGY_EXHAUSTED = "strategy_exhausted"
    VERIFICATION_FAILED = "verification_failed"
    BUDGET_EXCEEDED = "budget_exceeded"
    PERSISTENCE_ERROR = "persistence_error"
    SECURITY_VIOLATION = "security_violation"


class RecoveryAction(str, Enum):
    RETRY = "retry"
    REPAIR = "repair"
    OBSERVE = "observe"
    ROLLBACK = "rollback"
    REPLAN = "replan"
    ESCALATE = "escalate"
    CHECKPOINT_STOP = "checkpoint_stop"
    SWITCH_STRATEGY = "switch_strategy"


class RecoveryStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    SUPERSEDED = "superseded"


class FailureOrigin(str, Enum):
    MODEL = "model"
    PROVIDER = "provider"
    HARNESS = "harness"
    TOOL = "tool"
    MCP = "mcp"
    PLUGIN = "plugin"
    ENVIRONMENT = "environment"
    SECURITY = "security"
    PERSISTENCE = "persistence"


class FailurePhase(str, Enum):
    CONFIG_VALIDATE = "config_validate"
    PREPARE = "prepare"
    PROVIDER_CALL = "provider_call"
    RESPONSE_NORMALIZE = "response_normalize"
    PROTOCOL_VALIDATE = "protocol_validate"
    CONTROLLER = "controller"
    WORKFLOW = "workflow"
    TOOL_EXECUTE = "tool_execute"
    VERIFY = "verify"
    PERSIST = "persist"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class FailureContext:
    """Stable policy input for failures crossing subsystem boundaries.

    Exceptions are transport details. Retry/fallback/recovery policy consumes
    this normalized record instead of inspecting Python exception classes.
    """

    kind: FailureKind
    origin: FailureOrigin
    phase: FailurePhase
    message: str
    retryable: bool = False
    fallback_safe: bool = False
    route_alias: str | None = None
    provider_id: str | None = None
    model_id: str | None = None
    call_id: str | None = None
    exit_code: int | None = None
    stderr_digest: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("failure context message must be non-empty")
        if self.exit_code is not None and (not isinstance(self.exit_code, int) or isinstance(self.exit_code, bool)):
            raise ValueError("failure context exit_code must be an integer when present")

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": "failure-context-v1",
            "kind": self.kind.value,
            "origin": self.origin.value,
            "phase": self.phase.value,
            "message": self.message,
            "retryable": bool(self.retryable),
            "fallback_safe": bool(self.fallback_safe),
            "route_alias": self.route_alias,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "call_id": self.call_id,
            "exit_code": self.exit_code,
            "stderr_digest": self.stderr_digest,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PolicyDecision:
    """One policy decision shared by Gateway and Runtime recovery layers."""

    runtime_action: RecoveryAction
    retry_same_route: bool = False
    fallback_allowed: bool = False
    terminal: bool = False
    reason: str = ""

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": "failure-policy-decision-v1",
            "runtime_action": self.runtime_action.value,
            "retry_same_route": bool(self.retry_same_route),
            "fallback_allowed": bool(self.fallback_allowed),
            "terminal": bool(self.terminal),
            "reason": self.reason,
        }


class FailurePolicyEngine:
    """Central error -> classification policy used at all retry boundaries."""

    TERMINAL_KINDS = frozenset({
        FailureKind.BUDGET_EXCEEDED,
        FailureKind.PERSISTENCE_ERROR,
        FailureKind.SECURITY_VIOLATION,
        FailureKind.STRATEGY_EXHAUSTED,
    })

    BASE_ACTIONS = {
        FailureKind.TOOL_ERROR: RecoveryAction.REPAIR,
        FailureKind.ENV_ERROR: RecoveryAction.RETRY,
        FailureKind.MISSING_INFO: RecoveryAction.OBSERVE,
        FailureKind.HYPOTHESIS_REFUTED: RecoveryAction.ROLLBACK,
        FailureKind.MODEL_PROVIDER_ERROR: RecoveryAction.OBSERVE,
        FailureKind.MODEL_PROTOCOL_ERROR: RecoveryAction.REPAIR,
        FailureKind.ACTOR_WORKFLOW_ERROR: RecoveryAction.REPLAN,
        FailureKind.IMPLEMENTATION_ERROR: RecoveryAction.REPAIR,
        FailureKind.NO_PROGRESS: RecoveryAction.REPLAN,
        FailureKind.STRATEGY_EXHAUSTED: RecoveryAction.ESCALATE,
        FailureKind.VERIFICATION_FAILED: RecoveryAction.REPLAN,
        FailureKind.BUDGET_EXCEEDED: RecoveryAction.CHECKPOINT_STOP,
        FailureKind.PERSISTENCE_ERROR: RecoveryAction.CHECKPOINT_STOP,
        FailureKind.SECURITY_VIOLATION: RecoveryAction.CHECKPOINT_STOP,
    }

    def decide(
        self,
        context: FailureContext,
        *,
        attempts_remaining: bool = False,
        fallback_available: bool = False,
        repeat_count: int = 1,
        repeat_limit: int = 3,
    ) -> PolicyDecision:
        if repeat_limit < 2:
            raise ValueError("repeat_limit must be at least 2")
        if context.kind in self.TERMINAL_KINDS:
            return PolicyDecision(
                runtime_action=self.BASE_ACTIONS[context.kind],
                terminal=True,
                reason="terminal failure kind",
            )

        if context.kind in {FailureKind.MODEL_PROVIDER_ERROR, FailureKind.MODEL_PROTOCOL_ERROR}:
            retry = bool(attempts_remaining and context.retryable)
            fallback = bool((not retry) and fallback_available and context.fallback_safe)
            return PolicyDecision(
                runtime_action=self.BASE_ACTIONS[context.kind],
                retry_same_route=retry,
                fallback_allowed=fallback,
                terminal=False,
                reason=(
                    "retry same route" if retry
                    else "fallback to next route" if fallback
                    else "return typed model failure to runtime"
                ),
            )

        if repeat_count >= repeat_limit:
            return PolicyDecision(
                runtime_action=RecoveryAction.SWITCH_STRATEGY,
                reason="repeat limit reached in current strategy generation",
            )

        action = self.BASE_ACTIONS[context.kind]
        if action == RecoveryAction.RETRY and not context.retryable:
            action = RecoveryAction.OBSERVE
        return PolicyDecision(runtime_action=action, reason="base failure policy")

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "failure-policy-v1",
            "terminal_kinds": sorted(kind.value for kind in self.TERMINAL_KINDS),
            "base_actions": {
                kind.value: action.value
                for kind, action in sorted(self.BASE_ACTIONS.items(), key=lambda item: item[0].value)
            },
            "model_policy": "retry-if-explicitly-retryable-else-fallback-if-explicitly-safe",
            "routing_input": "FailureContext-not-exception-type",
        }


@dataclass
class Failure:
    kind: FailureKind
    message: str
    action: str | None = None
    retry_safe: bool = False
    signature_key: str | None = None
    context: FailureContext | None = None

    def __post_init__(self) -> None:
        if self.context is not None:
            if self.context.kind is not self.kind:
                raise ValueError("Failure.kind must match FailureContext.kind")
            self.retry_safe = bool(self.context.retryable)

    @property
    def signature(self) -> str:
        # Recovery acts on repeat identity, so the default biases against false
        # grouping. Numeric values can be semantically meaningful (401 vs 500,
        # exit 1 vs 2) and are preserved. Callers that know which fields are
        # volatile may provide an explicit stable signature_key.
        identity = self.signature_key
        if identity is None and self.context is not None:
            identity = "|".join([
                self.context.origin.value,
                self.context.phase.value,
                self.context.route_alias or "",
                self.context.provider_id or "",
                self.context.model_id or "",
                self.context.call_id or "",
                self.context.stderr_digest or "",
                re.sub(r"\s+", " ", self.context.message.strip().lower()),
            ])
        if identity is None:
            identity = re.sub(r"\s+", " ", self.message.strip().lower())
        raw = f"{self.kind.value}|{self.action or ''}|{identity}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class RecoveryTransition:
    transition_id: str
    action: RecoveryAction
    failure_kind: FailureKind
    failure_signature: str
    repeat_count: int
    created_step: int
    strategy_generation: int
    target: str | None = None
    retry_safe: bool = False
    status: RecoveryStatus = RecoveryStatus.PENDING
    applied_step: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def dump(self) -> dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "action": self.action.value,
            "failure_kind": self.failure_kind.value,
            "failure_signature": self.failure_signature,
            "repeat_count": int(self.repeat_count),
            "created_step": int(self.created_step),
            "strategy_generation": int(self.strategy_generation),
            "target": self.target,
            "retry_safe": bool(self.retry_safe),
            "status": self.status.value,
            "applied_step": self.applied_step,
            "details": dict(self.details),
        }

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "RecoveryTransition":
        return cls(
            transition_id=str(raw["transition_id"]),
            action=RecoveryAction(raw["action"]),
            failure_kind=FailureKind(raw["failure_kind"]),
            failure_signature=str(raw["failure_signature"]),
            repeat_count=int(raw["repeat_count"]),
            created_step=int(raw["created_step"]),
            strategy_generation=int(raw.get("strategy_generation", 0)),
            target=raw.get("target"),
            retry_safe=bool(raw.get("retry_safe", False)),
            status=RecoveryStatus(raw.get("status", RecoveryStatus.PENDING.value)),
            applied_step=(
                int(raw["applied_step"])
                if raw.get("applied_step") is not None
                else None
            ),
            details=dict(raw.get("details", {})),
        )


class FailureRouter:
    """Runtime compatibility facade over the common FailurePolicyEngine."""

    ROUTES = dict(FailurePolicyEngine.BASE_ACTIONS)
    TERMINAL_KINDS = FailurePolicyEngine.TERMINAL_KINDS

    def __init__(self, repeat_limit: int = 3, *, policy: FailurePolicyEngine | None = None):
        if repeat_limit < 2:
            raise ValueError("repeat_limit must be at least 2")
        self.repeat_limit = int(repeat_limit)
        self.policy = policy or FailurePolicyEngine()

    @staticmethod
    def _context_for_legacy_failure(failure: Failure) -> FailureContext:
        if failure.context is not None:
            return failure.context
        origin = FailureOrigin.HARNESS
        phase = FailurePhase.RECOVERY
        if failure.kind == FailureKind.TOOL_ERROR:
            origin, phase = FailureOrigin.TOOL, FailurePhase.TOOL_EXECUTE
        elif failure.kind == FailureKind.ENV_ERROR:
            origin, phase = FailureOrigin.ENVIRONMENT, FailurePhase.PREPARE
        elif failure.kind == FailureKind.PERSISTENCE_ERROR:
            origin, phase = FailureOrigin.PERSISTENCE, FailurePhase.PERSIST
        elif failure.kind == FailureKind.SECURITY_VIOLATION:
            origin, phase = FailureOrigin.SECURITY, FailurePhase.TOOL_EXECUTE
        elif failure.kind == FailureKind.ACTOR_WORKFLOW_ERROR:
            origin, phase = FailureOrigin.MODEL, FailurePhase.WORKFLOW
        elif failure.kind == FailureKind.MODEL_PROTOCOL_ERROR:
            origin, phase = FailureOrigin.MODEL, FailurePhase.PROTOCOL_VALIDATE
        elif failure.kind == FailureKind.MODEL_PROVIDER_ERROR:
            origin, phase = FailureOrigin.PROVIDER, FailurePhase.PROVIDER_CALL
        return FailureContext(
            kind=failure.kind,
            origin=origin,
            phase=phase,
            message=failure.message,
            retryable=bool(failure.retry_safe),
        )

    def route(self, failure: Failure, repeat_count: int = 1) -> RecoveryAction:
        context = self._context_for_legacy_failure(failure)
        return self.policy.decide(
            context,
            repeat_count=repeat_count,
            repeat_limit=self.repeat_limit,
        ).runtime_action

    def descriptor(self) -> dict[str, Any]:
        descriptor = self.policy.descriptor()
        descriptor.update({
            "repeat_limit": self.repeat_limit,
            "failure_signature_policy": "kind+action+context-or-explicit-key",
            "repeat_scope": "current_strategy_generation",
        })
        return descriptor
