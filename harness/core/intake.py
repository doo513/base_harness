from __future__ import annotations

from pathlib import Path
from typing import Sequence

from harness.core.context_budget import BudgetInput, resolve_budget
from harness.core.task_classifier import classify_task
from harness.core.types import JsonObject, JsonValue


TASK_TOOLS: dict[str, tuple[str, ...]] = {
    "file_analysis": ("list_files", "inspect_file", "grep_files", "read_file_range"),
    "web_research": ("search_web", "fetch_relevant_page"),
    "pdf_analysis": ("inspect_pdf", "search_pdf", "read_pdf_pages"),
    "data_inspection": ("inspect_csv", "inspect_json", "sample_rows"),
    "archive_inspection": ("inspect_archive", "safe_list_archive"),
    "experiment": ("run_python", "run_command"),
    "verification": ("run_python", "run_command"),
    "problem_adapter": ("format_submission", "evaluate_submission"),
}


def _file_summary(file_path: Path, workspace: Path) -> JsonObject:
    resolved = file_path if file_path.is_absolute() else workspace / file_path
    exists = resolved.exists()
    size = resolved.stat().st_size if exists and resolved.is_file() else 0
    return {
        "path": str(file_path),
        "resolved_path": str(resolved),
        "exists": exists,
        "size": size,
        "extension": resolved.suffix.lower(),
    }


def _recommended_tools(labels: Sequence[str], workspace_path: str | Path | None = None) -> list[JsonValue]:
    from harness.core.config import load_config
    task_tools = load_config(workspace_path).task_tools
    tools: list[JsonValue] = []
    seen: set[str] = set()
    for label in labels:
        for tool in task_tools.get(label, ()):
            if tool not in seen:
                seen.add(tool)
                tools.append(tool)
    return tools


def intake_request(
    user_request: str,
    workspace_path: str | Path = ".",
    provided_files: Sequence[str | Path] | None = None,
    budget: BudgetInput = None,
) -> JsonObject:
    resolved_budget = resolve_budget(budget)
    workspace = Path(workspace_path)
    files = [Path(file_path) for file_path in provided_files or ()]
    labels = classify_task(user_request, files, workspace_path=workspace)
    summaries = [_file_summary(file_path, workspace) for file_path in files]
    missing_files = [summary["path"] for summary in summaries if summary["exists"] is False]
    unknowns: list[JsonValue] = []
    if not user_request.strip():
        unknowns.append("objective is empty")
    if missing_files:
        unknowns.append(f"provided files not found: {', '.join(str(path) for path in missing_files)}")
    return {
        "objective": user_request.strip(),
        "likely_tasks": labels,
        "provided_files": summaries[: resolved_budget.max_archive_list_entries],
        "unknowns": unknowns,
        "recommended_first_tools": _recommended_tools(labels, workspace_path=workspace),
    }
