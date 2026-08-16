from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from harness.core.context_budget import ContextBudget
from harness.core.types import JsonObject

# Type definition for a tool recording wrapper
RecordCallFunc = Callable[[Path, str, Callable[[], JsonObject]], JsonObject]

# Type definition for an inspector function
InspectorFunc = Callable[[Path, ContextBudget, Path, str, RecordCallFunc], list[JsonObject]]

_EXT_INSPECTORS: dict[str, list[InspectorFunc]] = {}
_TYPE_INSPECTORS: dict[str, list[InspectorFunc]] = {}


def register_extension_inspector(extension: str, inspector: InspectorFunc) -> None:
    ext = extension.lower()
    if ext not in _EXT_INSPECTORS:
        _EXT_INSPECTORS[ext] = []
    _EXT_INSPECTORS[ext].append(inspector)


def register_type_inspector(type_hint: str, inspector: InspectorFunc) -> None:
    t = type_hint.lower()
    if t not in _TYPE_INSPECTORS:
        _TYPE_INSPECTORS[t] = []
    _TYPE_INSPECTORS[t].append(inspector)


def get_inspectors(extension: str, type_hint: str | None) -> list[InspectorFunc]:
    inspectors: list[InspectorFunc] = []
    ext = extension.lower()
    if ext in _EXT_INSPECTORS:
        inspectors.extend(_EXT_INSPECTORS[ext])
    if type_hint:
        t = type_hint.lower()
        if t in _TYPE_INSPECTORS:
            inspectors.extend(_TYPE_INSPECTORS[t])
    return inspectors


# Initialize default inspectors
def _init_defaults() -> None:
    from harness.tools.archive_tools import inspect_archive
    from harness.tools.data_tools import inspect_csv, inspect_json
    from harness.tools.file_tools import read_file_range
    from harness.tools.pdf_tools import inspect_pdf, search_pdf

    # Text inspector (type-based)
    def text_inspector(path: Path, budget: ContextBudget, trace_path: Path, query: str, record_call: RecordCallFunc) -> list[JsonObject]:
        read_result = record_call(
            trace_path,
            "read_file_range",
            lambda: read_file_range(path, 1, budget.max_file_read_lines, budget=budget),
        )
        read_result["summary"] = f"Read bounded lines from {path.name}"
        return [read_result]

    # JSON inspector (extension-based)
    def json_inspector(path: Path, budget: ContextBudget, trace_path: Path, query: str, record_call: RecordCallFunc) -> list[JsonObject]:
        json_result = record_call(
            trace_path,
            "inspect_json",
            lambda: inspect_json(path, budget=budget),
        )
        json_result["summary"] = f"Inspected JSON structure for {path.name}"
        return [json_result]

    # CSV inspector (extension-based)
    def csv_inspector(path: Path, budget: ContextBudget, trace_path: Path, query: str, record_call: RecordCallFunc) -> list[JsonObject]:
        csv_result = record_call(
            trace_path,
            "inspect_csv",
            lambda: inspect_csv(path, budget=budget),
        )
        csv_result["summary"] = f"Inspected CSV structure for {path.name}"
        return [csv_result]

    # Archive inspector (extension-based)
    def archive_inspector(path: Path, budget: ContextBudget, trace_path: Path, query: str, record_call: RecordCallFunc) -> list[JsonObject]:
        archive_result = record_call(
            trace_path,
            "inspect_archive",
            lambda: inspect_archive(path, budget=budget),
        )
        archive_result["summary"] = f"Inspected archive entries for {path.name}"
        return [archive_result]

    # PDF inspector (extension-based)
    def pdf_inspector(path: Path, budget: ContextBudget, trace_path: Path, query: str, record_call: RecordCallFunc) -> list[JsonObject]:
        pdf_result = record_call(
            trace_path,
            "inspect_pdf",
            lambda: inspect_pdf(path, budget=budget),
        )
        pdf_result["summary"] = f"Checked PDF support for {path.name}"

        pdf_search_result = record_call(
            trace_path,
            "search_pdf",
            lambda: search_pdf(path, query, budget=budget),
        )
        pdf_search_result["summary"] = f"Checked PDF search support for {path.name}"
        return [pdf_result, pdf_search_result]

    # Register defaults
    register_type_inspector("text", text_inspector)
    for ext in (".json", ".jsonl"):
        register_extension_inspector(ext, json_inspector)
    for ext in (".csv", ".tsv"):
        register_extension_inspector(ext, csv_inspector)
    for ext in (".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz"):
        register_extension_inspector(ext, archive_inspector)
    register_extension_inspector(".pdf", pdf_inspector)


_init_defaults()
