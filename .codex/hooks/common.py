#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# ///
from __future__ import annotations

import json
import sys
from pathlib import Path

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class HarnessHookError(Exception):
    pass


def read_payload(path: Path | None) -> JsonValue:
    try:
        text = path.read_text(encoding="utf-8") if path else sys.stdin.read()
    except OSError as exc:
        raise HarnessHookError(f"cannot read input: {exc}") from exc
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HarnessHookError(f"invalid JSON: {exc}") from exc


def read_json_file(path: Path) -> JsonValue:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HarnessHookError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HarnessHookError(f"invalid JSON in {path}: {exc}") from exc


def require_mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise HarnessHookError(f"{label} must be a JSON object")
    return value


def require_list(value: JsonValue, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise HarnessHookError(f"{label} must be a JSON array")
    return value


def text_field(mapping: dict[str, JsonValue], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str):
        raise HarnessHookError(f"missing text field: {key}")
    return value


def print_result(token: str, message: str) -> None:
    print(f"{token}: {message}")

def print_block(token: str, message: str) -> None:
    print(f"{token}: {message}", file=sys.stderr)

if __name__ == "__main__":
    print_result("OK_COMMON", "helpers loaded")
