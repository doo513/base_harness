from __future__ import annotations

from dataclasses import dataclass
import json


MODEL_ERROR_MARKER = "HARNESS_MODEL_ERROR:"


@dataclass(frozen=True)
class EmbeddedModelError:
    kind: str
    message: str
    retryable: bool


def encode_model_error(*, kind: str, message: str, retryable: bool) -> str:
    return MODEL_ERROR_MARKER + json.dumps(
        {
            "kind": str(kind),
            "message": str(message),
            "retryable": bool(retryable),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def extract_embedded_model_error(text: str) -> EmbeddedModelError | None:
    """Recover a typed child-adapter error from wrapped stderr text.

    CommandProvider may prepend/append transport diagnostics before the adapter
    error reaches LLMController. This parser only recognizes the explicit marker
    emitted by cooperating Harness adapters; arbitrary stderr is never treated as
    typed protocol metadata.
    """
    if not isinstance(text, str):
        return None
    marker_at = text.rfind(MODEL_ERROR_MARKER)
    if marker_at < 0:
        return None
    tail = text[marker_at + len(MODEL_ERROR_MARKER):].lstrip()
    decoder = json.JSONDecoder()
    try:
        raw, _ = decoder.raw_decode(tail)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    message = raw.get("message")
    retryable = raw.get("retryable")
    if not isinstance(kind, str) or not kind:
        return None
    if not isinstance(message, str):
        return None
    if not isinstance(retryable, bool):
        return None
    return EmbeddedModelError(
        kind=kind,
        message=message,
        retryable=retryable,
    )
