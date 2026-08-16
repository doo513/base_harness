from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import re

from .storage import canonical_hash


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def normalize_progress_value(value: Any) -> Any:
    """Return an inspectable deterministic value for decision identity.

    This is deliberately syntactic. It removes cosmetic representation changes
    but does not claim semantic equivalence.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, Path):
        return str(value.expanduser())
    if isinstance(value, bytes):
        return {"bytes_sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
    if isinstance(value, dict):
        return {
            str(key): normalize_progress_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [normalize_progress_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized = [normalize_progress_value(item) for item in value]
        return sorted(normalized, key=canonical_hash)
    return {"type": f"{type(value).__module__}.{type(value).__qualname__}"}


def decision_progress_signatures(decision) -> tuple[str, str]:
    """Return (family_signature, exact_signature) for a validated Decision."""
    kind = str(decision.kind)
    payload = dict(decision.payload)

    if kind == "tool":
        tool = _normalize_text(str(payload.get("tool", "")))
        family = f"tool:{tool}"
        exact_body = {
            "kind": kind,
            "tool": tool,
            "args": normalize_progress_value(payload.get("args", {})),
        }
    elif kind in {"propose", "verify_claim", "refute"}:
        key = _normalize_text(str(payload.get("key", "")))
        family = f"{kind}:{key}"
        exact_body = {"kind": kind, "key": key}
        if kind == "propose":
            exact_body["value"] = normalize_progress_value(payload.get("value"))
            exact_body["evidence_refs"] = sorted(
                _normalize_text(str(ref)) for ref in payload.get("evidence_refs", [])
            )
        # refute.reason is intentionally excluded. It is Actor narrative and
        # changing it must not create a new repetition identity.
    elif kind == "complete":
        family = "complete"
        # complete.reason is Actor narrative and intentionally excluded.
        exact_body = {"kind": kind}
    else:
        family = kind
        exact_body = {"kind": kind, "payload": normalize_progress_value(payload)}

    return family, canonical_hash(exact_body)[:24]


@dataclass(frozen=True)
class ProgressPolicy:
    family_repeat_limit: int = 3
    no_progress_streak_limit: int = 5
    max_strategy_generations_without_progress: int = 3

    def __post_init__(self) -> None:
        if self.family_repeat_limit < 2:
            raise ValueError("family_repeat_limit must be at least 2")
        if self.no_progress_streak_limit < 2:
            raise ValueError("no_progress_streak_limit must be at least 2")
        if self.max_strategy_generations_without_progress < 1:
            raise ValueError("max_strategy_generations_without_progress must be at least 1")

    def descriptor(self) -> dict[str, Any]:
        return {
            "family_repeat_limit": int(self.family_repeat_limit),
            "no_progress_streak_limit": int(self.no_progress_streak_limit),
            "max_strategy_generations_without_progress": int(
                self.max_strategy_generations_without_progress
            ),
            "progress_authority": [
                "verified_fact_hash_change",
                "novel_integrity_checked_successful_observation_digest",
            ],
            "speculative_state_counts_as_progress": False,
            "failed_observation_counts_as_progress": False,
            "decision_identity": "normalized_exact_plus_coarse_family",
            "specific_failure_precedence": True,
            "recovery_steps_are_actor_samples": False,
        }


@dataclass
class ProgressState:
    strategy_generation: int = 0
    no_progress_streak: int = 0
    last_family_signature: str | None = None
    family_repeat_count: int = 0
    evaluations: int = 0
    progress_events: int = 0
    last_progress_step: int | None = None
    last_progress_generation: int = 0
    last_progress_reasons: list[str] = field(default_factory=list)
    threshold_triggers: int = 0

    def dump(self) -> dict[str, Any]:
        return {
            "strategy_generation": int(self.strategy_generation),
            "no_progress_streak": int(self.no_progress_streak),
            "last_family_signature": self.last_family_signature,
            "family_repeat_count": int(self.family_repeat_count),
            "evaluations": int(self.evaluations),
            "progress_events": int(self.progress_events),
            "last_progress_step": self.last_progress_step,
            "last_progress_generation": int(self.last_progress_generation),
            "last_progress_reasons": list(self.last_progress_reasons),
            "threshold_triggers": int(self.threshold_triggers),
        }

    @classmethod
    def load(cls, raw: Any) -> "ProgressState":
        if not isinstance(raw, dict):
            return cls()
        last_step = raw.get("last_progress_step")
        return cls(
            strategy_generation=int(raw.get("strategy_generation", 0)),
            no_progress_streak=int(raw.get("no_progress_streak", 0)),
            last_family_signature=(
                str(raw["last_family_signature"])
                if raw.get("last_family_signature") is not None
                else None
            ),
            family_repeat_count=int(raw.get("family_repeat_count", 0)),
            evaluations=int(raw.get("evaluations", 0)),
            progress_events=int(raw.get("progress_events", 0)),
            last_progress_step=(int(last_step) if last_step is not None else None),
            last_progress_generation=int(raw.get("last_progress_generation", 0)),
            last_progress_reasons=[str(item) for item in raw.get("last_progress_reasons", [])],
            threshold_triggers=int(raw.get("threshold_triggers", 0)),
        )
