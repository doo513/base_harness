from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence, TypedDict

from harness.core.types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class ContextBudget:
    max_tool_result_chars: int = 12_000
    max_file_read_lines: int = 160
    max_grep_results: int = 50
    max_pdf_pages_per_read: int = 3
    max_web_results: int = 5
    max_passages_per_page: int = 5
    max_csv_sample_rows: int = 50
    max_archive_list_entries: int = 300
    max_packet_snippets: int = 5
    max_source_refs: int = 20


class TextLimitResult(TypedDict):
    value: str
    truncated: bool
    original_count_or_length: int
    returned_count_or_length: int


class ItemLimitResult(TypedDict):
    value: list[JsonValue]
    truncated: bool
    original_count_or_length: int
    returned_count_or_length: int


BudgetInput = ContextBudget | Mapping[str, int] | None


def resolve_budget(budget: BudgetInput = None) -> ContextBudget:
    if budget is None:
        return ContextBudget()
    if isinstance(budget, ContextBudget):
        return budget
    values = asdict(ContextBudget())
    for key, value in budget.items():
        if key in values:
            values[key] = max(0, int(value))
    return ContextBudget(**values)


def budget_as_dict(budget: BudgetInput = None) -> JsonObject:
    return {key: value for key, value in asdict(resolve_budget(budget)).items()}


def truncate_text(text: str, max_chars: int) -> TextLimitResult:
    original_length = len(text)
    if original_length <= max_chars:
        return {
            "value": text,
            "truncated": False,
            "original_count_or_length": original_length,
            "returned_count_or_length": original_length,
        }
    if max_chars <= 0:
        return {
            "value": "",
            "truncated": True,
            "original_count_or_length": original_length,
            "returned_count_or_length": 0,
        }

    marker = "[Truncated: omitted chars]"
    if len(marker) >= max_chars:
        value = marker[:max_chars]
        return {
            "value": value,
            "truncated": True,
            "original_count_or_length": original_length,
            "returned_count_or_length": len(value),
        }

    available = max_chars - len(marker)
    start_count = available // 2
    end_count = available - start_count
    omitted = original_length - start_count - end_count
    marker = f"[Truncated: {omitted} chars omitted. Showing first {start_count} and last {end_count}]"
    if len(marker) >= max_chars:
        value = marker[:max_chars]
    else:
        available = max_chars - len(marker)
        start_count = available // 2
        end_count = available - start_count
        value = f"{text[:start_count]}{marker}{text[-end_count:] if end_count else ''}"
    return {
        "value": value,
        "truncated": True,
        "original_count_or_length": original_length,
        "returned_count_or_length": len(value),
    }


def limit_items(items: Sequence[JsonValue], max_items: int) -> ItemLimitResult:
    original_count = len(items)
    if original_count <= max_items:
        return {
            "value": list(items),
            "truncated": False,
            "original_count_or_length": original_count,
            "returned_count_or_length": original_count,
        }
    if max_items <= 0:
        return {
            "value": [],
            "truncated": True,
            "original_count_or_length": original_count,
            "returned_count_or_length": 0,
        }
    if max_items == 1:
        omitted = original_count
        value: list[JsonValue] = [f"[Truncated: {omitted} elements omitted. Showing first 0 and last 0]"]
        return {
            "value": value,
            "truncated": True,
            "original_count_or_length": original_count,
            "returned_count_or_length": 1,
        }

    marker_slots = 1
    edge_slots = max_items - marker_slots
    start_count = edge_slots // 2
    end_count = edge_slots - start_count
    omitted = original_count - start_count - end_count
    marker = f"[Truncated: {omitted} elements omitted. Showing first {start_count} and last {end_count}]"
    value = [*items[:start_count], marker, *items[original_count - end_count :]]
    return {
        "value": value,
        "truncated": True,
        "original_count_or_length": original_count,
        "returned_count_or_length": len(value),
    }
