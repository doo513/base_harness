from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import Any


DECISION_KINDS = (
    "plan",
    "task",
    "propose",
    "verify_claim",
    "tool",
    "retrieve",
    "refute",
    "complete",
)


class OutputContract(str, Enum):
    TEXT = "text"
    JSON = "json"
    JSON_SCHEMA = "json_schema"
    TOOL_CALL = "tool_call"


class OutputEnforcement(str, Enum):
    PROMPT_ONLY = "prompt_only"
    POSTHOC_VALIDATED = "posthoc_validated"
    WRAPPER_ENFORCED = "wrapper_enforced"
    PROVIDER_NATIVE = "provider_native"


class ProtocolErrorKind(str, Enum):
    INVALID_JSON = "protocol_invalid_json"
    TRUNCATED = "protocol_truncated"
    SCHEMA = "protocol_schema"


class DecisionProtocolError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        kind: ProtocolErrorKind,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.kind = kind.value
        self.retryable = bool(retryable)


@dataclass(frozen=True)
class DecodedDecision:
    kind: str
    payload: dict[str, Any]
    canonical_json: str
    lexical_repaired: bool = False
    lexical_repair_kind: str | None = None


def decision_json_schema() -> dict[str, Any]:
    """Return the provider-facing envelope schema.

    Payload semantics are still validated by ``validate_decision`` and the
    Kernel-owned workflow/runtime layers. Provider schema support must never
    become execution or truth authority.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "payload"],
        "properties": {
            "kind": {"type": "string", "enum": list(DECISION_KINDS)},
            "payload": {"type": "object"},
        },
    }


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else text


def _looks_truncated_json(text: str, exc: json.JSONDecodeError) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    if stripped.count("{") > stripped.count("}") or stripped.count("[") > stripped.count("]"):
        return True
    return exc.pos >= max(0, len(stripped) - 2)


def _is_control_character_error(exc: json.JSONDecodeError) -> bool:
    return exc.msg == "Invalid control character at"


def _load_json_object(
    content: str,
    *,
    allow_control_character_repair: bool,
) -> tuple[dict[str, Any], bool, str | None]:
    text = _strip_json_fence(content)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        if allow_control_character_repair and _is_control_character_error(exc):
            # This is the only lexical repair in v1. ``strict=False`` accepts
            # raw control characters inside JSON strings, after which the object
            # is canonicalized with json.dumps. It does not invent missing
            # syntax, fields, tool names, task IDs, or semantic content.
            try:
                value = json.loads(text, strict=False)
            except json.JSONDecodeError as repair_exc:
                kind = (
                    ProtocolErrorKind.TRUNCATED
                    if _looks_truncated_json(text, repair_exc)
                    else ProtocolErrorKind.INVALID_JSON
                )
                raise DecisionProtocolError(
                    f"decision JSON is invalid: {repair_exc.msg}",
                    kind=kind,
                ) from repair_exc
            repaired = True
            repair_kind = "raw_control_character"
        else:
            kind = (
                ProtocolErrorKind.TRUNCATED
                if _looks_truncated_json(text, exc)
                else ProtocolErrorKind.INVALID_JSON
            )
            raise DecisionProtocolError(
                f"decision JSON is invalid: {exc.msg}",
                kind=kind,
            ) from exc
    else:
        repaired = False
        repair_kind = None

    if not isinstance(value, dict):
        raise DecisionProtocolError(
            "decision must be a JSON object",
            kind=ProtocolErrorKind.SCHEMA,
        )
    return value, repaired, repair_kind


def validate_decision(kind: str, payload: Any) -> None:
    """Validate canonical Actor-decision structure without repairing meaning."""
    if kind not in DECISION_KINDS:
        raise DecisionProtocolError(
            f"unsupported decision kind: {kind}",
            kind=ProtocolErrorKind.SCHEMA,
        )
    if not isinstance(payload, dict):
        raise DecisionProtocolError(
            "decision payload must be an object",
            kind=ProtocolErrorKind.SCHEMA,
        )

    if kind == "plan":
        extras = set(payload) - {"objective", "tasks"}
        if extras:
            raise DecisionProtocolError(
                "plan payload only supports objective and tasks",
                kind=ProtocolErrorKind.SCHEMA,
            )
        objective = payload.get("objective")
        tasks = payload.get("tasks")
        if not isinstance(objective, str) or not objective.strip():
            raise DecisionProtocolError(
                "plan.objective must be a non-empty string",
                kind=ProtocolErrorKind.SCHEMA,
            )
        if not isinstance(tasks, list) or not tasks:
            raise DecisionProtocolError(
                "plan.tasks must be a non-empty list",
                kind=ProtocolErrorKind.SCHEMA,
            )

    elif kind == "task":
        extras = set(payload) - {"id", "status", "note"}
        if extras:
            raise DecisionProtocolError(
                "task payload only supports id, status, and note",
                kind=ProtocolErrorKind.SCHEMA,
            )
        task_id = payload.get("id")
        status = payload.get("status")
        note = payload.get("note")
        if not isinstance(task_id, str) or not task_id.strip():
            raise DecisionProtocolError(
                "task.id must be a non-empty string",
                kind=ProtocolErrorKind.SCHEMA,
            )
        if status not in {"pending", "active", "done", "blocked"}:
            raise DecisionProtocolError(
                "task.status must be pending|active|done|blocked",
                kind=ProtocolErrorKind.SCHEMA,
            )
        if note is not None and not isinstance(note, str):
            raise DecisionProtocolError(
                "task.note must be a string when provided",
                kind=ProtocolErrorKind.SCHEMA,
            )

    elif kind == "propose":
        key = payload.get("key")
        if not isinstance(key, str) or not key.strip():
            raise DecisionProtocolError(
                "propose.key must be a non-empty string",
                kind=ProtocolErrorKind.SCHEMA,
            )
        refs = payload.get("evidence_refs", [])
        if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
            raise DecisionProtocolError(
                "propose.evidence_refs must be a list of strings",
                kind=ProtocolErrorKind.SCHEMA,
            )

    elif kind == "verify_claim":
        key = payload.get("key")
        if not isinstance(key, str) or not key.strip():
            raise DecisionProtocolError(
                "verify_claim.key must be a non-empty string",
                kind=ProtocolErrorKind.SCHEMA,
            )

    elif kind == "tool":
        tool = payload.get("tool")
        args = payload.get("args", {})
        if not isinstance(tool, str) or not tool.strip():
            raise DecisionProtocolError(
                "tool.tool must be a non-empty string",
                kind=ProtocolErrorKind.SCHEMA,
            )
        if not isinstance(args, dict):
            raise DecisionProtocolError(
                "tool.args must be an object",
                kind=ProtocolErrorKind.SCHEMA,
            )

    elif kind == "retrieve":
        extras = set(payload) - {"query"}
        if extras:
            raise DecisionProtocolError(
                "retrieve payload only supports the query field; scope/top_k/provider/ranking are kernel-owned",
                kind=ProtocolErrorKind.SCHEMA,
            )
        query = payload.get("query")
        if not isinstance(query, str) or not query.strip():
            raise DecisionProtocolError(
                "retrieve.query must be a non-empty string",
                kind=ProtocolErrorKind.SCHEMA,
            )

    elif kind == "refute":
        key = payload.get("key")
        if not isinstance(key, str) or not key.strip():
            raise DecisionProtocolError(
                "refute.key must be a non-empty string",
                kind=ProtocolErrorKind.SCHEMA,
            )
        reason = payload.get("reason", "")
        if not isinstance(reason, str):
            raise DecisionProtocolError(
                "refute.reason must be a string",
                kind=ProtocolErrorKind.SCHEMA,
            )

    elif kind == "complete":
        reason = payload.get("reason", "")
        if not isinstance(reason, str):
            raise DecisionProtocolError(
                "complete.reason must be a string",
                kind=ProtocolErrorKind.SCHEMA,
            )


def decode_decision_text(
    content: str,
    *,
    allow_control_character_repair: bool = True,
) -> DecodedDecision:
    value, repaired, repair_kind = _load_json_object(
        content,
        allow_control_character_repair=allow_control_character_repair,
    )
    if set(value) != {"kind", "payload"}:
        raise DecisionProtocolError(
            "decision object must contain exactly kind and payload",
            kind=ProtocolErrorKind.SCHEMA,
        )
    kind = value.get("kind")
    payload = value.get("payload")
    if not isinstance(kind, str):
        raise DecisionProtocolError(
            "decision kind must be a string",
            kind=ProtocolErrorKind.SCHEMA,
        )
    validate_decision(kind, payload)
    canonical = json.dumps(
        {"kind": kind, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return DecodedDecision(
        kind=kind,
        payload=payload,
        canonical_json=canonical,
        lexical_repaired=repaired,
        lexical_repair_kind=repair_kind,
    )
