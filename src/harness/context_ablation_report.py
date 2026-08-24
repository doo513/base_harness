from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from harness.core.events import EventLog
from harness.core.storage import RunManifestStore


SCHEMA_VERSION = "context-ablation-report-v1"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("payload")
    return value if isinstance(value, dict) else {}


def summarize_run_records(
    *,
    records: Iterable[dict[str, Any]],
    metrics: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    context_rows: list[dict[str, Any]] = []
    protocol_rows: list[dict[str, Any]] = []
    failures: Counter[str] = Counter()

    for record in records:
        kind = record.get("kind")
        payload = _payload(record)
        if kind == "model.context_compile":
            telemetry = payload.get("telemetry")
            if isinstance(telemetry, dict):
                context_rows.append(dict(telemetry))
        elif kind == "model.protocol_decode":
            telemetry = payload.get("telemetry")
            if isinstance(telemetry, dict):
                protocol_rows.append(dict(telemetry))
        elif kind == "failure":
            failure_kind = payload.get("kind")
            if isinstance(failure_kind, str):
                failures[failure_kind] += 1

    source_tokens = [
        int(row["source_estimated_input_tokens"])
        for row in context_rows
        if isinstance(row.get("source_estimated_input_tokens"), int)
    ]
    compiled_tokens = [
        int(row["compiled_estimated_input_tokens"])
        for row in context_rows
        if isinstance(row.get("compiled_estimated_input_tokens"), int)
    ]
    ratios = [
        float(row["estimated_reduction_ratio"])
        for row in context_rows
        if isinstance(row.get("estimated_reduction_ratio"), (int, float))
    ]
    headroom: list[int] = []
    levels: Counter[str] = Counter()
    for row in context_rows:
        levels[str(row.get("level", "unknown"))] += 1
        budget = row.get("budget")
        compiled = row.get("compiled_estimated_input_tokens")
        if isinstance(budget, dict) and isinstance(budget.get("max_input_tokens"), int) and isinstance(compiled, int):
            headroom.append(int(budget["max_input_tokens"]) - compiled)

    lexical_repairs = sum(bool(row.get("lexical_repaired")) for row in protocol_rows)
    decision_kinds = Counter(
        str(row.get("kind")) for row in protocol_rows if row.get("kind") is not None
    )

    def avg(values):
        return round(mean(values), 4) if values else None

    return {
        "model_revision": manifest.get("model_revision"),
        "task_revision": manifest.get("task_revision"),
        "config_hash": manifest.get("config_hash"),
        "completed": bool(metrics.get("completed", False)),
        "steps": int(metrics.get("steps", 0) or 0),
        "tool_calls": int(metrics.get("tool_calls", 0) or 0),
        "failure_count": int(metrics.get("failures", 0) or 0),
        "failure_kinds": dict(sorted(failures.items())),
        "model_attempts": int(metrics.get("model_attempts", len(context_rows)) or 0),
        "context": {
            "records": len(context_rows),
            "source_tokens_mean": avg(source_tokens),
            "compiled_tokens_mean": avg(compiled_tokens),
            "reduction_ratio_mean": avg(ratios),
            "minimum_estimated_headroom_tokens": min(headroom) if headroom else None,
            "levels": dict(sorted(levels.items())),
        },
        "protocol": {
            "decoded_records": len(protocol_rows),
            "lexical_repairs": lexical_repairs,
            "decision_kinds": dict(sorted(decision_kinds.items())),
        },
    }


def load_run_diagnostics(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir).expanduser().resolve()
    manifest, manifest_hash = RunManifestStore(root / "run_manifest.json").load_verified()
    records = EventLog(root / "events.jsonl").verify_chain()
    metrics = _read_json(root / "metrics.json")
    summary = summarize_run_records(
        records=records,
        metrics=metrics,
        manifest=manifest,
    )
    summary["run_dir"] = str(root)
    summary["manifest_hash"] = manifest_hash
    return summary


def compare_context_runs(
    baseline: dict[str, Any],
    variant: dict[str, Any],
) -> dict[str, Any]:
    same_model = (
        baseline.get("model_revision") is not None
        and baseline.get("model_revision") == variant.get("model_revision")
    )
    same_task = (
        baseline.get("task_revision") is not None
        and baseline.get("task_revision") == variant.get("task_revision")
    )

    def delta(path: tuple[str, ...]):
        left: Any = baseline
        right: Any = variant
        for key in path:
            left = left.get(key) if isinstance(left, dict) else None
            right = right.get(key) if isinstance(right, dict) else None
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return round(float(right) - float(left), 4)
        return None

    return {
        "schema_version": SCHEMA_VERSION,
        "causal_conclusion": "not_inferred",
        "interpretation": (
            "Observed deltas only. Attribute a difference to context policy only after a controlled ablation "
            "with the same model/task revisions and otherwise pinned experiment settings."
        ),
        "controlled_ablation_eligible": same_model and same_task,
        "same_model_revision": same_model,
        "same_task_revision": same_task,
        "baseline": baseline,
        "variant": variant,
        "observed_deltas": {
            "steps": delta(("steps",)),
            "tool_calls": delta(("tool_calls",)),
            "failures": delta(("failure_count",)),
            "context_compiled_tokens_mean": delta(("context", "compiled_tokens_mean")),
            "context_reduction_ratio_mean": delta(("context", "reduction_ratio_mean")),
            "protocol_lexical_repairs": delta(("protocol", "lexical_repairs")),
        },
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare integrity-verified Harness runs without auto-assigning causality."
    )
    parser.add_argument("baseline")
    parser.add_argument("variant")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    report = compare_context_runs(
        load_run_diagnostics(args.baseline),
        load_run_diagnostics(args.variant),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        target = Path(args.output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8", newline="")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
