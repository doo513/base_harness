from __future__ import annotations

import fnmatch
import re
from collections import deque
from pathlib import Path
from typing import Iterable, Sequence

from harness.core.cache import get_cached_value, set_cached_value
from harness.core.context_budget import BudgetInput, resolve_budget
from harness.core.types import JsonObject, JsonValue

DEFAULT_CACHE_DIR = Path(".harness_cache")
DEFAULT_IGNORED_DIRS = (
    ".git",
    ".codegraph",
    ".harness_cache",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
)


def _path_value(path: str | Path) -> Path:
    return Path(path)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_ignored(path: Path, root: Path, patterns: Sequence[str]) -> bool:
    relative = _relative(path, root)
    parts = path.relative_to(root).parts if path.is_relative_to(root) else path.parts
    if any(part in DEFAULT_IGNORED_DIRS for part in parts):
        return True
    return any(fnmatch.fnmatch(path.name, pattern) or fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as source:
            chunk = source.read(1024)
    except OSError:
        return False
    if b"\x00" in chunk:
        return True
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _type_hint(path: Path) -> str:
    if path.is_dir():
        return "directory"
    if _is_binary(path):
        return "binary"
    return "text"


def _file_entry(path: Path, root: Path) -> JsonObject:
    stat = path.stat()
    return {
        "path": _relative(path, root),
        "size": stat.st_size,
        "extension": path.suffix.lower(),
        "type_hint": _type_hint(path),
    }


def list_files(
    path: str | Path,
    max_depth: int = 4,
    ignore: Sequence[str] | None = None,
    budget: BudgetInput = None,
) -> JsonObject:
    root = _path_value(path)
    resolved_budget = resolve_budget(budget)
    patterns = tuple(ignore or ())
    files: list[JsonValue] = []
    truncated = False
    limit = resolved_budget.max_archive_list_entries

    if not root.exists():
        return {"path": str(root), "files": [], "truncated": False, "error": "path not found"}

    for file_path in sorted(item for item in root.rglob("*") if item.is_file()):
        depth = len(file_path.relative_to(root).parts)
        if depth > max_depth or _is_ignored(file_path, root, patterns):
            continue
        if len(files) >= limit:
            truncated = True
            break
        files.append(_file_entry(file_path, root))
    return {"path": str(root), "files": files, "truncated": truncated}


def inspect_file(path: str | Path, budget: BudgetInput = None) -> JsonObject:
    file_path = _path_value(path)
    cache_key = f"inspect_file:{file_path.resolve()}"
    cached = get_cached_value(DEFAULT_CACHE_DIR, cache_key, check_file=file_path) if file_path.exists() else None
    if cached is not None:
        return cached
    if not file_path.exists():
        return {"path": str(file_path), "exists": False, "truncated": False}
    stat = file_path.stat()
    type_hint = _type_hint(file_path)
    line_count = 0
    if type_hint == "text":
        with file_path.open(encoding="utf-8", errors="replace") as source:
            for line_count, _line in enumerate(source, start=1):
                if line_count >= resolve_budget(budget).max_file_read_lines:
                    break
    result: JsonObject = {
        "path": str(file_path),
        "exists": True,
        "size": stat.st_size,
        "extension": file_path.suffix.lower(),
        "type_hint": type_hint,
        "line_count_sample": line_count,
        "truncated": type_hint == "text" and line_count >= resolve_budget(budget).max_file_read_lines,
    }
    set_cached_value(DEFAULT_CACHE_DIR, cache_key, result, check_file=file_path)
    return result


def _iter_text_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        yield file_path


def grep_files(
    pattern: str,
    path: str | Path,
    max_results: int | None = None,
    context_lines: int = 2,
    ignore: Sequence[str] | None = None,
    budget: BudgetInput = None,
) -> JsonObject:
    root = _path_value(path)
    resolved_budget = resolve_budget(budget)
    limit = max_results if max_results is not None else resolved_budget.max_grep_results
    matches: list[JsonValue] = []
    compiled = re.compile(pattern)
    patterns = tuple(ignore or ())

    for file_path in _iter_text_files(root):
        if _is_ignored(file_path, root, patterns):
            continue
        if _is_binary(file_path):
            continue
        before: deque[JsonObject] = deque(maxlen=max(0, context_lines))
        with file_path.open(encoding="utf-8", errors="replace") as source:
            for line_number, line in enumerate(source, start=1):
                text = line.rstrip("\n")
                if compiled.search(text):
                    matches.append(
                        {
                            "path": str(file_path),
                            "line_number": line_number,
                            "line": text,
                            "context": list(before),
                        }
                    )
                    if len(matches) >= limit:
                        return {
                            "pattern": pattern,
                            "matches": matches,
                            "truncated": True,
                            "source_refs": [{"source": str(file_path), "location": f"line {line_number}"}],
                        }
                before.append({"line_number": line_number, "text": text})
    return {"pattern": pattern, "matches": matches, "truncated": False}


def read_file_range(path: str | Path, start_line: int, end_line: int, budget: BudgetInput = None) -> JsonObject:
    file_path = _path_value(path)
    resolved_budget = resolve_budget(budget)
    if not file_path.exists():
        return {"path": str(file_path), "lines": [], "truncated": False, "error": "path not found"}
    if _is_binary(file_path):
        return {"path": str(file_path), "lines": [], "truncated": False, "error": "binary file"}
    start = max(1, start_line)
    end = max(start, end_line)
    max_lines = resolved_budget.max_file_read_lines
    requested_count = end - start + 1
    return_count = min(requested_count, max_lines)
    lines: list[JsonValue] = []

    with file_path.open(encoding="utf-8", errors="replace") as source:
        for line_number, line in enumerate(source, start=1):
            if line_number < start:
                continue
            if len(lines) >= return_count:
                break
            lines.append({"line_number": line_number, "text": line.rstrip("\n")})
    truncated_by_budget = requested_count > max_lines and len(lines) >= max_lines
    end_of_file_reached = len(lines) < min(requested_count, max_lines)
    returned_end = start + len(lines) - 1 if lines else start
    return {
        "path": str(file_path),
        "start_line": start,
        "end_line": end,
        "lines": lines,
        "truncated": truncated_by_budget or end_of_file_reached,
        "truncated_by_budget": truncated_by_budget,
        "end_of_file_reached": end_of_file_reached,
        "source_refs": [{"source": str(file_path), "location": f"lines {start}-{returned_end}"}],
    }
