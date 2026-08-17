from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable


@dataclass(frozen=True, slots=True)
class BenchmarkRecord:
    task_id: str
    mode: str
    success: bool
    elapsed_ms: int
    tool_calls: int = 0
    files_read: int = 0
    commands_run: int = 0
    retry_count: int = 0
    verification_attempts: int = 0
    context_chars: int = 0
    final_result_valid: bool = False


def append_benchmark_record(path: str | Path, record: BenchmarkRecord) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")


def load_benchmark_records(path: str | Path) -> list[BenchmarkRecord]:
    records: list[BenchmarkRecord] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(BenchmarkRecord(**json.loads(line)))
    return records


def summarize_benchmarks(records: Iterable[BenchmarkRecord]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[BenchmarkRecord]] = {}
    for record in records:
        grouped.setdefault(record.mode, []).append(record)

    summary: dict[str, dict[str, float | int]] = {}
    for mode, items in grouped.items():
        summary[mode] = {
            "runs": len(items),
            "success_rate": mean(1.0 if item.success else 0.0 for item in items),
            "valid_result_rate": mean(1.0 if item.final_result_valid else 0.0 for item in items),
            "mean_elapsed_ms": mean(item.elapsed_ms for item in items),
            "mean_tool_calls": mean(item.tool_calls for item in items),
            "mean_files_read": mean(item.files_read for item in items),
            "mean_commands_run": mean(item.commands_run for item in items),
            "mean_retry_count": mean(item.retry_count for item in items),
            "mean_verification_attempts": mean(item.verification_attempts for item in items),
            "mean_context_chars": mean(item.context_chars for item in items),
        }
    return summary


def compare_modes(
    records: Iterable[BenchmarkRecord],
    *,
    baseline_mode: str = "baseline",
    harness_mode: str = "harness",
) -> dict[str, object]:
    summary = summarize_benchmarks(records)
    baseline = summary.get(baseline_mode)
    harness = summary.get(harness_mode)
    if baseline is None or harness is None:
        return {
            "comparable": False,
            "reason": "both baseline and harness records are required",
            "summary": summary,
        }

    return {
        "comparable": True,
        "baseline_mode": baseline_mode,
        "harness_mode": harness_mode,
        "success_rate_delta": float(harness["success_rate"]) - float(baseline["success_rate"]),
        "valid_result_rate_delta": float(harness["valid_result_rate"]) - float(baseline["valid_result_rate"]),
        "elapsed_ms_delta": float(harness["mean_elapsed_ms"]) - float(baseline["mean_elapsed_ms"]),
        "tool_calls_delta": float(harness["mean_tool_calls"]) - float(baseline["mean_tool_calls"]),
        "context_chars_delta": float(harness["mean_context_chars"]) - float(baseline["mean_context_chars"]),
        "summary": summary,
    }
