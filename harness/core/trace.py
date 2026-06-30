from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

from harness.core.types import JsonObject, JsonValue

TRACE_KEYS = {
    "ts",
    "stage",
    "tool",
    "action",
    "path",
    "query",
    "ok",
    "duration_ms",
    "warnings",
    "truncated",
    "supported",
    "error",
}


def _compact_record(record: Mapping[str, JsonValue]) -> JsonObject:
    payload: JsonObject = {}
    for key in TRACE_KEYS:
        if key not in record:
            continue
        value = record[key]
        if key == "warnings" and isinstance(value, list):
            payload[key] = [str(item)[:160] for item in value[:5]]
        elif isinstance(value, str):
            payload[key] = value[:240]
        else:
            payload[key] = value
    return payload


def append_trace(path: str | Path, record: Mapping[str, JsonValue]) -> None:
    trace_path = Path(path)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _compact_record(record)
    if "ts" not in payload:
        payload["ts"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    with trace_path.open("a", encoding="utf-8") as trace_file:
        trace_file.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def read_trace(path: str | Path, limit: int | None = None) -> list[JsonObject]:
    trace_path = Path(path)
    if not trace_path.exists():
        return []
    records: list[JsonObject] = []
    with trace_path.open(encoding="utf-8") as trace_file:
        for line in trace_file:
            stripped = line.strip()
            if stripped:
                decoded = json.loads(stripped)
                if isinstance(decoded, dict):
                    records.append(decoded)
    if limit is None or limit >= len(records):
        return records
    return records[-limit:]
