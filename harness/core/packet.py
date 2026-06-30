from __future__ import annotations

from typing import Mapping, Sequence

from harness.core.context_budget import BudgetInput, resolve_budget, truncate_text
from harness.core.types import JsonObject, JsonValue


def _stringify_snippet(value: JsonValue) -> str:
    match value:
        case str():
            return value
        case list():
            return "\n".join(str(item) for item in value[:20])
        case dict():
            return "\n".join(f"{key}: {item}" for key, item in list(value.items())[:20])
        case int() | float() | bool() | None:
            return str(value)


def _source_refs(output: Mapping[str, JsonValue]) -> list[JsonValue]:
    refs = output.get("source_refs")
    if isinstance(refs, list):
        return refs
    source = output.get("path") or output.get("source") or output.get("url")
    if isinstance(source, str):
        location = output.get("location")
        return [{"source": source, "location": location if isinstance(location, str) else ""}]
    return []


def _summary(output: Mapping[str, JsonValue]) -> str:
    for key in ("summary", "output_summary", "status"):
        value = output.get(key)
        if isinstance(value, str) and value:
            return value
    return "tool output summarized"


def _snippet(output: Mapping[str, JsonValue]) -> str | None:
    for key in ("snippet", "content", "text", "stdout"):
        value = output.get(key)
        if value is not None:
            return _stringify_snippet(value)
    lines = output.get("lines")
    if isinstance(lines, list):
        rendered: list[str] = []
        for item in lines:
            if isinstance(item, dict):
                number = item.get("line_number")
                text = item.get("text")
                rendered.append(f"{number}: {text}")
        return "\n".join(rendered)
    return None


def build_context_packet(
    task: str,
    objective: str,
    tool_outputs: Sequence[Mapping[str, JsonValue]],
    unknowns: Sequence[str] | None = None,
    next_actions: Sequence[str] | None = None,
    budget: BudgetInput = None,
) -> JsonObject:
    resolved_budget = resolve_budget(budget)
    summaries: list[JsonValue] = []
    refs: list[JsonValue] = []
    snippets: list[JsonValue] = []
    truncated = False

    for output in tool_outputs:
        summaries.append(_summary(output))
        output_refs = _source_refs(output)
        remaining_refs = resolved_budget.max_source_refs - len(refs)
        if remaining_refs > 0:
            refs.extend(output_refs[:remaining_refs])
        truncated = truncated or len(output_refs) > max(0, remaining_refs)
        snippet = _snippet(output)
        if snippet is not None and len(snippets) < resolved_budget.max_packet_snippets:
            limited = truncate_text(snippet, resolved_budget.max_tool_result_chars)
            snippets.append({"text": limited["value"], "truncated": limited["truncated"]})
            truncated = truncated or limited["truncated"]
        elif snippet is not None:
            truncated = True
        truncated = truncated or bool(output.get("truncated"))

    return {
        "task": task,
        "objective": objective,
        "summary": " ".join(str(item) for item in summaries),
        "source_refs": refs,
        "snippets": snippets,
        "unknowns": list(unknowns or ()),
        "next_actions": list(next_actions or ()),
        "truncated": truncated,
    }
