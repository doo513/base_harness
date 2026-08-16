from dataclasses import dataclass
from enum import Enum
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

class RecoveryAction(str, Enum):
    RETRY = "retry"
    REPAIR = "repair"
    OBSERVE = "observe"
    ROLLBACK = "rollback"
    REPLAN = "replan"
    ESCALATE = "escalate"
    CHECKPOINT_STOP = "checkpoint_stop"
    SWITCH_STRATEGY = "switch_strategy"

@dataclass
class Failure:
    kind: FailureKind
    message: str
    action: str | None = None

    @property
    def signature(self) -> str:
        # Normalize volatile numbers/paths enough to detect repeated semantic failures.
        normalized = re.sub(r"\b\d+\b", "<n>", self.message.lower())
        raw = f"{self.kind.value}|{self.action or ''}|{normalized}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

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
    }

    def __init__(self, repeat_limit: int = 3):
        self.repeat_limit = repeat_limit

    def route(self, failure, repeat_count: int = 1):
        if repeat_count >= self.repeat_limit and failure.kind not in {
            FailureKind.BUDGET_EXCEEDED,
            FailureKind.PERSISTENCE_ERROR,
            FailureKind.MISSING_INFO,
        }:
            return RecoveryAction.SWITCH_STRATEGY
        return self.ROUTES[failure.kind]
