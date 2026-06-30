from __future__ import annotations

from collections.abc import Mapping, Sequence

from harness.core.types import JsonValue


def format_submission(value: str | Sequence[JsonValue] | Mapping[str, JsonValue]) -> str:
    if isinstance(value, str):
        return value.rstrip() + "\n"
    if isinstance(value, Mapping):
        return "\n".join(f"{key}: {item}" for key, item in value.items()) + "\n"
    return "\n".join(str(item) for item in value) + "\n"
