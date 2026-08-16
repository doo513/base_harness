from __future__ import annotations

import json
from pathlib import Path

DEFAULT_TASK_TOOLS: dict[str, tuple[str, ...]] = {
    "file_analysis": ("list_files", "inspect_file", "grep_files", "read_file_range"),
    "web_research": ("search_web", "fetch_relevant_page"),
    "pdf_analysis": ("inspect_pdf", "search_pdf", "read_pdf_pages"),
    "data_inspection": ("inspect_csv", "inspect_json", "sample_rows"),
    "archive_inspection": ("inspect_archive", "safe_list_archive"),
    "experiment": ("run_python", "run_command"),
    "verification": ("run_python", "run_command"),
    "problem_adapter": ("format_submission", "evaluate_submission"),
}

DEFAULT_CLASSIFICATION = {
    "file_analysis": {
        "keywords": ["file", "files", "input", "format", "problem", "source", "find", "grep"],
        "extensions": []
    },
    "pdf_analysis": {
        "keywords": ["pdf"],
        "extensions": [".pdf"]
    },
    "data_inspection": {
        "keywords": ["csv", "json", "dataset", "data"],
        "extensions": [".csv", ".tsv", ".json", ".jsonl", ".parquet"]
    },
    "archive_inspection": {
        "keywords": ["zip", "archive", "tarball"],
        "extensions": [".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz"]
    },
    "web_research": {
        "keywords": ["http://", "https://", "web", "search", "site", "url"],
        "extensions": []
    },
    "experiment": {
        "keywords": ["run", "execute", "experiment", "benchmark", "try"],
        "extensions": []
    },
    "verification": {
        "keywords": ["verify", "test", "check", "validate"],
        "extensions": []
    },
    "problem_adapter": {
        "keywords": ["submit", "submission", "judge", "evaluator", "adapter"],
        "extensions": []
    }
}


class HarnessConfig:
    def __init__(self, task_tools: dict[str, tuple[str, ...]], classification: dict[str, dict[str, list[str]]]):
        self.task_tools = task_tools
        self.classification = classification


def load_config(workspace_path: str | Path | None = None) -> HarnessConfig:
    config_file = None
    if workspace_path:
        p = Path(workspace_path) / "harness_config.json"
        if p.exists():
            config_file = p
    if not config_file:
        p = Path("harness_config.json")
        if p.exists():
            config_file = p

    if not config_file:
        return HarnessConfig(DEFAULT_TASK_TOOLS, DEFAULT_CLASSIFICATION)

    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
        task_tools = {k: tuple(v) for k, v in data.get("task_tools", {}).items()}
        merged_task_tools = dict(DEFAULT_TASK_TOOLS)
        merged_task_tools.update(task_tools)

        classification = data.get("classification_rules", {})
        merged_classification = dict(DEFAULT_CLASSIFICATION)
        for k, v in classification.items():
            if isinstance(v, dict):
                merged_classification[k] = {
                    "keywords": v.get("keywords", []),
                    "extensions": v.get("extensions", [])
                }
        return HarnessConfig(merged_task_tools, merged_classification)
    except Exception:
        return HarnessConfig(DEFAULT_TASK_TOOLS, DEFAULT_CLASSIFICATION)
