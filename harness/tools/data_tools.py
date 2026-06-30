from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from harness.core.cache import get_cached_value, set_cached_value
from harness.core.context_budget import BudgetInput, resolve_budget
from harness.core.types import JsonObject, JsonValue

DEFAULT_CACHE_DIR = Path(".harness_cache")
JSON_KEY_PATTERN = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*:')


def _infer_scalar(value: str) -> str:
    stripped = value.strip()
    if stripped == "":
        return "empty"
    if stripped.lower() in {"true", "false"}:
        return "boolean"
    try:
        int(stripped)
    except ValueError:
        pass
    else:
        return "integer"
    try:
        float(stripped)
    except ValueError:
        return "string"
    return "number"


def _merge_types(values: list[str]) -> str:
    non_empty = [value for value in values if value != "empty"]
    unique = sorted(set(non_empty or values))
    return unique[0] if len(unique) == 1 else "mixed"


def _read_csv_sample(path: Path, row_limit: int) -> tuple[list[str], list[JsonObject], bool]:
    rows: list[JsonObject] = []
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        columns = list(reader.fieldnames or [])
        for row in reader:
            if len(rows) >= row_limit:
                return columns, rows, True
            rows.append({key: value for key, value in row.items()})
    return columns, rows, False


def inspect_csv(path: str | Path, budget: BudgetInput = None) -> JsonObject:
    csv_path = Path(path)
    resolved_budget = resolve_budget(budget)
    cache_key = f"inspect_csv:{csv_path.resolve()}:{resolved_budget.max_csv_sample_rows}"
    cached = get_cached_value(DEFAULT_CACHE_DIR, cache_key, check_file=csv_path) if csv_path.exists() else None
    if cached is not None:
        return cached
    columns, rows, truncated = _read_csv_sample(csv_path, resolved_budget.max_csv_sample_rows)
    schema: JsonObject = {}
    for column in columns:
        schema[column] = _merge_types([_infer_scalar(str(row.get(column, ""))) for row in rows])
    result: JsonObject = {
        "path": str(csv_path),
        "columns": columns,
        "schema": schema,
        "sample_rows": rows,
        "truncated": truncated,
    }
    set_cached_value(DEFAULT_CACHE_DIR, cache_key, result, check_file=csv_path)
    return result


def sample_rows(path: str | Path, n: int | None = None, budget: BudgetInput = None) -> JsonObject:
    csv_path = Path(path)
    resolved_budget = resolve_budget(budget)
    limit = min(n if n is not None else resolved_budget.max_csv_sample_rows, resolved_budget.max_csv_sample_rows)
    columns, rows, truncated = _read_csv_sample(csv_path, limit)
    return {
        "path": str(csv_path),
        "columns": columns,
        "rows": rows,
        "truncated": truncated,
    }


def _json_type(value: JsonValue) -> str:
    match value:
        case dict():
            return "object"
        case list():
            return "array"
        case str():
            return "string"
        case bool():
            return "boolean"
        case int():
            return "integer"
        case float():
            return "number"
        case None:
            return "null"


def _top_level_type_from_prefix(prefix: str) -> str:
    stripped = prefix.lstrip()
    if not stripped:
        return "unknown"
    first = stripped[0]
    if first == "{":
        return "object"
    if first == "[":
        return "array"
    if first == '"':
        return "string"
    if first in "-0123456789":
        return "number"
    if stripped.startswith(("true", "false")):
        return "boolean"
    if stripped.startswith("null"):
        return "null"
    return "unknown"


def _extract_object_keys(prefix: str, limit: int) -> list[JsonValue]:
    keys: list[JsonValue] = []
    seen: set[str] = set()
    for match in JSON_KEY_PATTERN.finditer(prefix):
        key = match.group(1)
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
        if len(keys) >= limit:
            break
    return keys


def _inspect_large_json(path: Path, sample_chars: int, key_limit: int) -> JsonObject:
    with path.open(encoding="utf-8", errors="replace") as json_file:
        prefix = json_file.read(max(1, sample_chars))
    top_level_type = _top_level_type_from_prefix(prefix)
    result: JsonObject = {
        "path": str(path),
        "top_level_type": top_level_type,
        "partial": True,
        "truncated": True,
        "sample_bytes": len(prefix.encode("utf-8")),
    }
    if top_level_type == "object":
        result["keys"] = _extract_object_keys(prefix, key_limit)
        result["schema"] = {}
    return result


def _inspect_jsonl(path: Path, row_limit: int) -> JsonObject:
    sample: list[JsonValue] = []
    element_types: set[str] = set()
    truncated = False
    with path.open(encoding="utf-8") as jsonl_file:
        for line_number, line in enumerate(jsonl_file, start=1):
            if line_number > row_limit:
                truncated = True
                break
            stripped = line.strip()
            if not stripped:
                continue
            decoded = json.loads(stripped)
            match decoded:
                case dict() | list() | str() | int() | float() | bool() | None:
                    sample.append(decoded)
                    element_types.add(_json_type(decoded))
    return {
        "path": str(path),
        "top_level_type": "jsonl",
        "sample": sample,
        "element_types": sorted(element_types),
        "line_count_sample": len(sample),
        "partial": truncated,
        "truncated": truncated,
    }


def inspect_json(path: str | Path, budget: BudgetInput = None) -> JsonObject:
    json_path = Path(path)
    resolved_budget = resolve_budget(budget)
    cache_key = (
        f"inspect_json:{json_path.resolve()}:{resolved_budget.max_csv_sample_rows}:"
        f"{resolved_budget.max_tool_result_chars}"
    )
    cached = get_cached_value(DEFAULT_CACHE_DIR, cache_key, check_file=json_path) if json_path.exists() else None
    if cached is not None:
        return cached
    if json_path.suffix.lower() == ".jsonl":
        result = _inspect_jsonl(json_path, resolved_budget.max_csv_sample_rows)
        set_cached_value(DEFAULT_CACHE_DIR, cache_key, result, check_file=json_path)
        return result
    if json_path.stat().st_size > resolved_budget.max_tool_result_chars:
        result = _inspect_large_json(json_path, resolved_budget.max_tool_result_chars, resolved_budget.max_csv_sample_rows)
        set_cached_value(DEFAULT_CACHE_DIR, cache_key, result, check_file=json_path)
        return result

    with json_path.open(encoding="utf-8") as json_file:
        decoded = json.load(json_file)
    result: JsonObject = {"path": str(json_path), "truncated": False, "partial": False}
    match decoded:
        case dict():
            keys = sorted(str(key) for key in decoded.keys())
            result.update(
                {
                    "top_level_type": "object",
                    "keys": keys[: resolved_budget.max_csv_sample_rows],
                    "schema": {str(key): _json_type(value) for key, value in decoded.items()},
                    "truncated": len(keys) > resolved_budget.max_csv_sample_rows,
                }
            )
        case list():
            sample = decoded[: resolved_budget.max_csv_sample_rows]
            result.update(
                {
                    "top_level_type": "array",
                    "length": len(decoded),
                    "sample": sample,
                    "element_types": sorted({_json_type(item) for item in sample}),
                    "truncated": len(decoded) > resolved_budget.max_csv_sample_rows,
                }
            )
        case str() | int() | float() | bool() | None:
            result.update({"top_level_type": _json_type(decoded), "sample": decoded})
    set_cached_value(DEFAULT_CACHE_DIR, cache_key, result, check_file=json_path)
    return result
