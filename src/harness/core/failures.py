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


@dataclass
class Failure:
    kind: FailureKind
    message: str
    action: str | None = None
    retry_safe: bool = False
    signature_key: str | None = None

    @property
    def signature(self) -> str:
        # Stage 05 recovery acts on repeat identity, so the default must bias
        # against false grouping. Numeric values may be semantically meaningful
        # (HTTP 401 vs 500, exit 1 vs 2) and are therefore preserved. Callers
        # that know which fields are volatile may provide an explicit stable
        # signature_key instead of relying on free-form message normalization.
        identity = self.signature_key
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
    ROUTES = {
        FailureKind.TOOL_ERROR: RecoveryAction.REPAIR,
        FailureKind.ENV_ERROR: RecoveryAction.RETRY,
        FailureKind.MISSING_INFO: RecoveryAction.OBSERVE,
        FailureKind.HYPOTHESIS_REFUTED: RecoveryAction.ROLLBACK,
        FailureKind.IMPLEMENTATION_ERROR: RecoveryAction.REPAIR,
        FailureKind.NO_PROGRESS: RecoveryAction.REPLAN,
        FailureKind.STRATEGY_EXHAUSTED: RecoveryAction.ESCALATE,
        FailureKind.VERIFICATION_FAILED: RecoveryAction.REPLAN,
        FailureKind.BUDGET_EXCEEDED: RecoveryAction.CHECKPOINT_STOP,
        FailureKind.PERSISTENCE_ERROR: RecoveryAction.CHECKPOINT_STOP,
        FailureKind.SECURITY_VIOLATION: RecoveryAction.CHECKPOINT_STOP,
    }

    TERMINAL_KINDS = frozenset({
        FailureKind.BUDGET_EXCEEDED,
        FailureKind.PERSISTENCE_ERROR,
        FailureKind.SECURITY_VIOLATION,
        FailureKind.STRATEGY_EXHAUSTED,
    })

    def __init__(self, repeat_limit: int = 3):
        if repeat_limit < 2:
            raise ValueError("repeat_limit must be at least 2")
        self.repeat_limit = int(repeat_limit)

    def route(self, failure: Failure, repeat_count: int = 1) -> RecoveryAction:
        if failure.kind in self.TERMINAL_KINDS:
            return self.ROUTES[failure.kind]
        if repeat_count >= self.repeat_limit:
            return RecoveryAction.SWITCH_STRATEGY
        action = self.ROUTES[failure.kind]
        if action == RecoveryAction.RETRY and not failure.retry_safe:
            return RecoveryAction.OBSERVE
        return action

    def descriptor(self) -> dict[str, Any]:
        return {
            "repeat_limit": self.repeat_limit,
            "routes": {
                kind.value: action.value
                for kind, action in sorted(self.ROUTES.items(), key=lambda item: item[0].value)
            },
            "terminal_kinds": sorted(kind.value for kind in self.TERMINAL_KINDS),
            "failure_signature_policy": "kind+action+explicit_key_or_whitespace_normalized_message_preserve_numbers",
        }
