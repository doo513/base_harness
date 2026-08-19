from __future__ import annotations

from pathlib import Path
from typing import Any

from .tools import SideEffect, ToolSpec
from .workspace import WorkspaceContract, WorkspaceContractError


DEFAULT_READ_LIMIT = 256 * 1024
DEFAULT_LIST_LIMIT = 2000
DEFAULT_SEARCH_FILE_LIMIT = 2000
DEFAULT_SEARCH_MATCH_LIMIT = 200


def _relative(contract: WorkspaceContract, path: Path) -> str:
    return str(path.relative_to(contract.root)) or "."


def make_workspace_read_tools(contract: WorkspaceContract) -> dict[str, ToolSpec]:
    """Bounded, read-only project inspection tools scoped to one workspace."""

    def file_read(path: str, max_bytes: int = DEFAULT_READ_LIMIT) -> dict[str, Any]:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0 or max_bytes > DEFAULT_READ_LIMIT:
            raise ValueError(f"max_bytes must be 1..{DEFAULT_READ_LIMIT}")
        target = contract.resolve_actor_path(path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"workspace file does not exist: {path}")
        data = target.read_bytes()
        truncated = len(data) > max_bytes
        visible = data[:max_bytes]
        try:
            text = visible.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = visible.decode("utf-8", errors="replace")
            encoding = "utf-8-replacement"
        return {
            "path": _relative(contract, target),
            "text": text,
            "encoding": encoding,
            "bytes_total": len(data),
            "bytes_visible": len(visible),
            "truncated": truncated,
        }

    def directory_list(path: str = ".", recursive: bool = False, max_entries: int = DEFAULT_LIST_LIMIT) -> dict[str, Any]:
        if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries <= 0 or max_entries > DEFAULT_LIST_LIMIT:
            raise ValueError(f"max_entries must be 1..{DEFAULT_LIST_LIMIT}")
        root = contract.resolve_actor_path(path)
        if not root.exists() or not root.is_dir():
            raise NotADirectoryError(f"workspace directory does not exist: {path}")
        iterator = root.rglob("*") if recursive else root.iterdir()
        entries: list[dict[str, Any]] = []
        truncated = False
        for candidate in sorted(iterator, key=lambda item: str(item)):
            try:
                resolved = candidate.resolve()
                if not contract.contains_path(resolved):
                    continue
                kind = "dir" if resolved.is_dir() else "file" if resolved.is_file() else "other"
                entries.append({"path": _relative(contract, resolved), "kind": kind})
            except (OSError, WorkspaceContractError):
                continue
            if len(entries) >= max_entries:
                truncated = True
                break
        return {
            "root": _relative(contract, root),
            "recursive": bool(recursive),
            "entries": entries,
            "truncated": truncated,
        }

    def file_search(query: str, path: str = ".", max_matches: int = DEFAULT_SEARCH_MATCH_LIMIT) -> dict[str, Any]:
        if not isinstance(query, str) or not query:
            raise ValueError("query must be a non-empty literal string")
        if len(query) > 1024:
            raise ValueError("query exceeds 1024 characters")
        if not isinstance(max_matches, int) or isinstance(max_matches, bool) or max_matches <= 0 or max_matches > DEFAULT_SEARCH_MATCH_LIMIT:
            raise ValueError(f"max_matches must be 1..{DEFAULT_SEARCH_MATCH_LIMIT}")
        root = contract.resolve_actor_path(path)
        if not root.exists() or not root.is_dir():
            raise NotADirectoryError(f"workspace directory does not exist: {path}")
        matches: list[dict[str, Any]] = []
        files_scanned = 0
        truncated = False
        for candidate in sorted(root.rglob("*"), key=lambda item: str(item)):
            if files_scanned >= DEFAULT_SEARCH_FILE_LIMIT:
                truncated = True
                break
            try:
                resolved = candidate.resolve()
                if not contract.contains_path(resolved) or not resolved.is_file():
                    continue
                if resolved.stat().st_size > DEFAULT_READ_LIMIT:
                    continue
                data = resolved.read_bytes()
                if b"\x00" in data:
                    continue
                text = data.decode("utf-8", errors="replace")
            except OSError:
                continue
            files_scanned += 1
            for line_number, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    matches.append({
                        "path": _relative(contract, resolved),
                        "line": line_number,
                        "preview": line[:1000],
                    })
                    if len(matches) >= max_matches:
                        truncated = True
                        break
            if len(matches) >= max_matches:
                break
        return {
            "query": query,
            "root": _relative(contract, root),
            "files_scanned": files_scanned,
            "matches": matches,
            "truncated": truncated,
        }

    common_provenance = {"kind": "workspace_read", "contract": "workspace-contract-v1"}
    return {
        "file.read": ToolSpec(
            name="file.read",
            description="Read a bounded UTF-8 preview of one file inside the configured workspace.",
            handler=file_read,
            side_effect=SideEffect.READ,
            idempotent=True,
            failure_modes=["missing_file", "path_escape", "read_error"],
            provenance={**common_provenance, "operation": "file_read"},
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "max_bytes": {"type": "integer"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
        ),
        "directory.list": ToolSpec(
            name="directory.list",
            description="List bounded workspace directory entries, optionally recursively.",
            handler=directory_list,
            side_effect=SideEffect.READ,
            idempotent=True,
            failure_modes=["missing_directory", "path_escape", "read_error"],
            provenance={**common_provenance, "operation": "directory_list"},
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "recursive": {"type": "boolean"},
                    "max_entries": {"type": "integer"},
                },
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
        ),
        "file.search": ToolSpec(
            name="file.search",
            description="Search bounded UTF-8 workspace files for a literal string and return matching line previews.",
            handler=file_search,
            side_effect=SideEffect.READ,
            idempotent=True,
            failure_modes=["missing_directory", "path_escape", "read_error", "scan_limit"],
            provenance={**common_provenance, "operation": "file_search"},
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 1024},
                    "path": {"type": "string", "minLength": 1},
                    "max_matches": {"type": "integer"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
        ),
    }
