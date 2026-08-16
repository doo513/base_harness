from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Callable, Sequence

from harness.core.context_budget import ContextBudget, budget_as_dict
from harness.core.intake import intake_request
from harness.core.packet import build_context_packet
from harness.core.task_classifier import ARCHIVE_EXTENSIONS, PDF_EXTENSIONS, classify_task
from harness.core.tool_router import tools_for_tasks
from harness.core.trace import append_trace
from harness.core.types import JsonObject
from harness.tools.archive_tools import inspect_archive
from harness.tools.data_tools import inspect_csv, inspect_json
from harness.tools.file_tools import grep_files, inspect_file, list_files, read_file_range
from harness.tools.pdf_tools import inspect_pdf, search_pdf
from harness.tools.web_tools import search_web

ToolCall = Callable[[], JsonObject]
GREP_STOP_WORDS = frozenset(
    {
        "and",
        "the",
        "for",
        "from",
        "with",
        "this",
        "that",
        "file",
        "files",
        "input",
        "format",
        "problem",
        "source",
        "inspect",
        "search",
        "find",
        "run",
        "execute",
        "experiment",
        "benchmark",
        "verify",
        "check",
        "test",
        "validate",
    }
)


@dataclass(frozen=True, slots=True)
class FileInspectionRequest:
    path: Path
    trace_path: Path
    budget: ContextBudget
    query: str


def _grep_pattern_from_request(user_request: str) -> str | None:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z0-9_./:-]{3,}", user_request):
        normalized = token.strip(".,;:()[]{}'\"").lower()
        if normalized in GREP_STOP_WORDS or normalized.startswith(("http://", "https://")):
            continue
        terms.append(re.escape(normalized))
        if len(terms) >= 5:
            break
    if not terms:
        return None
    return "|".join(terms)


def _resolve_file(workspace: Path, file_path: str | Path) -> Path:
    path = Path(file_path)
    if path.is_absolute():
        return path
    return workspace / path


def _warnings_for_result(result: JsonObject) -> list[str]:
    warnings: list[str] = []
    error = result.get("error")
    if isinstance(error, str) and error:
        warnings.append(error)
    reason = result.get("reason")
    if result.get("supported") is False and isinstance(reason, str) and reason:
        warnings.append(reason)
    if result.get("truncated") is True:
        warnings.append("result truncated by budget")
    return warnings


def _recorded_call(trace_path: Path, tool: str, call: ToolCall) -> JsonObject:
    started = monotonic()
    result = call()
    duration_ms = int((monotonic() - started) * 1000)
    warnings = _warnings_for_result(result)
    trace_record: JsonObject = {
        "stage": "tool",
        "tool": tool,
        "ok": "error" not in result,
        "duration_ms": duration_ms,
        "warnings": warnings,
        "truncated": result.get("truncated", False),
    }
    path = result.get("path")
    if isinstance(path, str):
        trace_record["path"] = path
    supported = result.get("supported")
    if isinstance(supported, bool):
        trace_record["supported"] = supported
    append_trace(trace_path, trace_record)
    return result


def _inspect_provided_file(request: FileInspectionRequest) -> list[JsonObject]:
    outputs: list[JsonObject] = []
    path = request.path
    inspect_result = _recorded_call(
        request.trace_path,
        "inspect_file",
        lambda: inspect_file(path, budget=request.budget),
    )
    inspect_result["summary"] = f"Inspected {path.name}"
    outputs.append(inspect_result)

    suffix = path.suffix.lower()
    type_hint = inspect_result.get("type_hint")
    if isinstance(type_hint, str):
        type_hint = type_hint.lower()
    else:
        type_hint = None

    from harness.core.registry import get_inspectors
    inspectors = get_inspectors(suffix, type_hint)
    for inspect_func in inspectors:
        try:
            results = inspect_func(path, request.budget, request.trace_path, request.query, _recorded_call)
            outputs.extend(results)
        except Exception as e:
            outputs.append({
                "path": str(path),
                "summary": f"Failed inspection by registered inspector: {e}",
                "error": str(e),
                "truncated": False
            })
    return outputs


def run_intake_workflow(
    user_request: str,
    workspace_path: str | Path = ".",
    provided_files: Sequence[str | Path] | None = None,
) -> JsonObject:
    budget = ContextBudget()
    workspace = Path(workspace_path)
    trace_path = workspace / ".harness_trace.jsonl"
    files = list(provided_files or ())
    intake_started = monotonic()
    intake = intake_request(user_request, workspace_path=workspace, provided_files=files, budget=budget)
    tasks = classify_task(user_request, files, workspace_path=workspace)
    selected_tools = tools_for_tasks(tasks, workspace_path=workspace)
    append_trace(
        trace_path,
        {
            "stage": "intake",
            "action": "classify",
            "ok": True,
            "duration_ms": int((monotonic() - intake_started) * 1000),
            "warnings": intake.get("unknowns", []),
        },
    )

    tool_outputs: list[JsonObject] = []
    list_result = _recorded_call(trace_path, "list_files", lambda: list_files(workspace, budget=budget))
    list_result["summary"] = "Listed workspace files with default ignores"
    tool_outputs.append(list_result)
    grep_pattern = _grep_pattern_from_request(user_request)
    if "file_analysis" in tasks and grep_pattern is not None:
        grep_result = _recorded_call(
            trace_path,
            "grep_files",
            lambda: grep_files(grep_pattern, workspace, context_lines=1, budget=budget),
        )
        matches = grep_result.get("matches")
        match_count = len(matches) if isinstance(matches, list) else 0
        grep_result["summary"] = f"Searched workspace text for request terms ({match_count} matches)"
        tool_outputs.append(grep_result)
    for file_path in files:
        resolved_file = _resolve_file(workspace, file_path)
        tool_outputs.extend(
            _inspect_provided_file(
                FileInspectionRequest(
                    path=resolved_file,
                    trace_path=trace_path,
                    budget=budget,
                    query=user_request,
                )
            )
        )
    if "web_research" in tasks:
        web_result = _recorded_call(trace_path, "search_web", lambda: search_web(user_request, budget=budget))
        web_result["summary"] = "Checked web search support"
        tool_outputs.append(web_result)

    packet_started = monotonic()
    packet = build_context_packet(
        tasks[0] if tasks else "file_analysis",
        str(intake["objective"]),
        tool_outputs,
        unknowns=[str(item) for item in intake.get("unknowns", [])],
        next_actions=[f"Use {tool}" for tool in selected_tools[:5]],
        budget=budget,
    )
    append_trace(
        trace_path,
        {
            "stage": "packet",
            "action": "build_context_packet",
            "ok": True,
            "duration_ms": int((monotonic() - packet_started) * 1000),
            "warnings": ["packet truncated by budget"] if packet.get("truncated") is True else [],
            "truncated": packet.get("truncated", False),
        },
    )

    return {
        "intake": intake,
        "tasks": tasks,
        "selected_tools": selected_tools,
        "tool_outputs_count": len(tool_outputs),
        "packet": packet,
        "trace_path": str(trace_path),
        "budget": budget_as_dict(budget),
    }
