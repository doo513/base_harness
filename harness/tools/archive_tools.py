from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from harness.core.cache import get_cached_value, set_cached_value
from harness.core.context_budget import BudgetInput, resolve_budget
from harness.core.types import JsonObject, JsonValue

DEFAULT_CACHE_DIR = Path(".harness_cache")


def _has_path_traversal(name: str) -> bool:
    posix_name = name.replace("\\", "/")
    path = PurePosixPath(posix_name)
    return path.is_absolute() or ".." in path.parts or (":" in path.parts[0] if path.parts else False)


def _zip_entries(path: Path) -> list[JsonObject]:
    entries: list[JsonObject] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            entries.append(
                {
                    "name": info.filename,
                    "size": info.file_size,
                    "compressed_size": info.compress_size,
                    "is_dir": info.is_dir(),
                    "path_traversal": _has_path_traversal(info.filename),
                }
            )
    return entries


def _tar_entries(path: Path) -> list[JsonObject]:
    entries: list[JsonObject] = []
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            entries.append(
                {
                    "name": member.name,
                    "size": member.size,
                    "compressed_size": member.size,
                    "is_dir": member.isdir(),
                    "path_traversal": _has_path_traversal(member.name),
                }
            )
    return entries


def _all_entries(path: Path) -> list[JsonObject]:
    if zipfile.is_zipfile(path):
        return _zip_entries(path)
    if tarfile.is_tarfile(path):
        return _tar_entries(path)
    return []


def safe_list_archive(path: str | Path, budget: BudgetInput = None) -> JsonObject:
    archive_path = Path(path)
    resolved_budget = resolve_budget(budget)
    if not archive_path.exists():
        return {"path": str(archive_path), "supported": False, "entries": [], "truncated": False, "error": "path not found"}
    cache_key = f"safe_list_archive:{archive_path.resolve()}:{resolved_budget.max_archive_list_entries}"
    cached = get_cached_value(DEFAULT_CACHE_DIR, cache_key, check_file=archive_path)
    if cached is not None:
        return cached

    entries = _all_entries(archive_path)
    if not entries:
        return {"path": str(archive_path), "supported": False, "entries": [], "truncated": False, "error": "unsupported archive"}
    limit = resolved_budget.max_archive_list_entries
    limited_entries: list[JsonValue] = entries[:limit]
    total_size = sum(int(entry["size"]) for entry in entries)
    largest = sorted(entries, key=lambda entry: int(entry["size"]), reverse=True)[:5]
    result: JsonObject = {
        "path": str(archive_path),
        "supported": True,
        "file_count": len(entries),
        "entries": limited_entries,
        "largest_entries": largest,
        "total_uncompressed_size": total_size,
        "has_path_traversal": any(entry["path_traversal"] is True for entry in entries),
        "truncated": len(entries) > limit,
    }
    set_cached_value(DEFAULT_CACHE_DIR, cache_key, result, check_file=archive_path)
    return result


def inspect_archive(path: str | Path, budget: BudgetInput = None) -> JsonObject:
    return safe_list_archive(path, budget=budget)
