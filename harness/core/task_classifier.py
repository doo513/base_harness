from __future__ import annotations

from pathlib import Path
from typing import Sequence

TaskLabel = str

SUPPORTED_LABELS: tuple[TaskLabel, ...] = (
    "file_analysis",
    "web_research",
    "pdf_analysis",
    "data_inspection",
    "archive_inspection",
    "experiment",
    "verification",
    "problem_adapter",
)

DATA_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl", ".parquet"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz"}
PDF_EXTENSIONS = {".pdf"}
FILE_ANALYSIS_TOKENS = ("file", "files", "input", "format", "problem", "source", "find", "grep")


def classify_task(
    text: str,
    files: Sequence[str | Path] | None = None,
    workspace_path: str | Path | None = None,
) -> list[TaskLabel]:
    from harness.core.config import load_config
    config = load_config(workspace_path)
    haystack = text.lower()
    suffixes = {Path(file_path).suffix.lower() for file_path in files or ()}
    labels: list[TaskLabel] = []

    for label, rules in config.classification.items():
        keywords = rules.get("keywords", [])
        extensions = rules.get("extensions", [])
        match_keyword = any(kw in haystack for kw in keywords)
        match_extension = any(ext in suffixes for ext in extensions)
        if match_keyword or match_extension:
            labels.append(label)

    if files and "file_analysis" not in labels:
        labels.append("file_analysis")

    if not labels:
        labels.append("file_analysis")

    ordered_labels = [l for l in config.classification.keys() if l in labels]
    for l in labels:
        if l not in ordered_labels:
            ordered_labels.append(l)

    return ordered_labels or ["file_analysis"]
