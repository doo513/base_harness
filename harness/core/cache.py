from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

from harness.core.types import JsonObject, JsonValue


def _cache_path(cache_dir: str | Path, key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return Path(cache_dir) / f"{digest}.json"


def _file_meta(path: Path) -> JsonObject:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def _is_same_file_meta(record: Mapping[str, JsonValue], check_file: Path) -> bool:
    if not check_file.exists():
        return False
    current = _file_meta(check_file)
    return (
        record.get("path") == current["path"]
        and record.get("mtime_ns") == current["mtime_ns"]
        and record.get("size") == current["size"]
    )


def get_cached_value(cache_dir: str | Path, key: str, check_file: str | Path | None = None) -> JsonObject | None:
    path = _cache_path(cache_dir, key)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as cache_file:
        decoded = json.load(cache_file)
    if not isinstance(decoded, dict):
        return None
    meta = decoded.get("check_file")
    if check_file is not None:
        if not isinstance(meta, dict) or not _is_same_file_meta(meta, Path(check_file)):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return None
    value = decoded.get("value")
    return value if isinstance(value, dict) else None


def set_cached_value(
    cache_dir: str | Path,
    key: str,
    value: Mapping[str, JsonValue],
    check_file: str | Path | None = None,
) -> None:
    path = _cache_path(cache_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: JsonObject = {"value": dict(value)}
    if check_file is not None:
        payload["check_file"] = _file_meta(Path(check_file))
    with path.open("w", encoding="utf-8") as cache_file:
        json.dump(payload, cache_file, sort_keys=True, separators=(",", ":"))
