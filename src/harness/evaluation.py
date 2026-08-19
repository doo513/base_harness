from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Iterable
import json

from harness.core.storage import canonical_hash


class EvaluationError(ValueError):
    pass


@dataclass(frozen=True)
class EvaluationControl:
    task_id: str
    task_revision: str
    model_revision: str
    profile: str
    toolset_revision: str
    budget_revision: str
    oracle_revision: str
    environment_revision: str

    def descriptor(self) -> dict[str, str]:
        values = {
            "task_id": self.task_id,
            "task_revision": self.task_revision,
            "model_revision": self.model_revision,
            "profile": self.profile,
            "toolset_revision": self.toolset_revision,
            "budget_revision": self.budget_revision,
            "oracle_revision": self.oracle_revision,
            "environment_revision": self.environment_revision,
        }
        if any(not isinstance(value, str) or not value for value in values.values()):
            raise EvaluationError("all matched-control revisions must be non-empty strings")
        return values

    @property
    def fingerprint(self) -> str:
        return canonical_hash(self.descriptor())


@dataclass(frozen=True)
class EvaluationRecord:
    arm: str
    repeat: int
    control: EvaluationControl
    completed: bool
    steps: int
    tool_calls: int
    failures: int
    completion_requests: int
    oracle_checks: int
    oracle_integrity_rejections: int = 0
    model_requests: int = 0
    model_failures: int = 0
    model_fallbacks: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model_latency_seconds: float = 0.0
    wall_time_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.arm, str) or not self.arm:
            raise EvaluationError("evaluation arm must be a non-empty string")
        if not isinstance(self.repeat, int) or isinstance(self.repeat, bool) or self.repeat < 0:
            raise EvaluationError("evaluation repeat must be a non-negative integer")
        for name in (
            "steps", "tool_calls", "failures", "completion_requests", "oracle_checks",
            "oracle_integrity_rejections", "model_requests", "model_failures",
            "model_fallbacks", "input_tokens", "output_tokens", "total_tokens",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise EvaluationError(f"{name} must be a non-negative integer")
        if self.model_latency_seconds < 0:
            raise EvaluationError("model_latency_seconds must be non-negative")
        if self.wall_time_seconds is not None and self.wall_time_seconds < 0:
            raise EvaluationError("wall_time_seconds must be non-negative")
        self.control.descriptor()

    @classmethod
    def from_runtime(
        cls,
        *,
        arm: str,
        repeat: int,
        control: EvaluationControl,
        runtime,
        model_gateway=None,
        wall_time_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "EvaluationRecord":
        metrics = dict(runtime.metrics)
        model = model_gateway.telemetry_snapshot() if model_gateway is not None else {}
        return cls(
            arm=arm,
            repeat=repeat,
            control=control,
            completed=bool(runtime.state.completed),
            steps=int(metrics.get("steps", runtime.state.step)),
            tool_calls=int(metrics.get("tool_calls", 0)),
            failures=int(metrics.get("failures", 0)),
            completion_requests=int(metrics.get("completion_requests", 0)),
            oracle_checks=int(metrics.get("oracle_checks", 0)),
            oracle_integrity_rejections=int(metrics.get("oracle_integrity_rejections", 0)),
            model_requests=int(model.get("requests", 0)),
            model_failures=int(model.get("failures", 0)),
            model_fallbacks=int(model.get("fallbacks", 0)),
            input_tokens=int(model.get("input_tokens", 0)),
            output_tokens=int(model.get("output_tokens", 0)),
            total_tokens=int(model.get("total_tokens", 0)),
            model_latency_seconds=float(model.get("latency_seconds", 0.0)),
            wall_time_seconds=wall_time_seconds,
            metadata=dict(metadata or {}),
        )

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": "evaluation-record-v1",
            "arm": self.arm,
            "repeat": self.repeat,
            "control": self.control.descriptor(),
            "control_fingerprint": self.control.fingerprint,
            "completed": self.completed,
            "steps": self.steps,
            "tool_calls": self.tool_calls,
            "failures": self.failures,
            "completion_requests": self.completion_requests,
            "oracle_checks": self.oracle_checks,
            "oracle_integrity_rejections": self.oracle_integrity_rejections,
            "model_requests": self.model_requests,
            "model_failures": self.model_failures,
            "model_fallbacks": self.model_fallbacks,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "model_latency_seconds": self.model_latency_seconds,
            "wall_time_seconds": self.wall_time_seconds,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def load(cls, raw: dict[str, Any]) -> "EvaluationRecord":
        if raw.get("schema_version") != "evaluation-record-v1":
            raise EvaluationError("unsupported evaluation record schema")
        control_raw = raw.get("control")
        if not isinstance(control_raw, dict):
            raise EvaluationError("evaluation record control must be an object")
        control = EvaluationControl(**control_raw)
        if raw.get("control_fingerprint") != control.fingerprint:
            raise EvaluationError("evaluation control fingerprint mismatch")
        return cls(
            arm=raw["arm"],
            repeat=raw["repeat"],
            control=control,
            completed=raw["completed"],
            steps=raw["steps"],
            tool_calls=raw["tool_calls"],
            failures=raw["failures"],
            completion_requests=raw["completion_requests"],
            oracle_checks=raw["oracle_checks"],
            oracle_integrity_rejections=raw.get("oracle_integrity_rejections", 0),
            model_requests=raw.get("model_requests", 0),
            model_failures=raw.get("model_failures", 0),
            model_fallbacks=raw.get("model_fallbacks", 0),
            input_tokens=raw.get("input_tokens", 0),
            output_tokens=raw.get("output_tokens", 0),
            total_tokens=raw.get("total_tokens", 0),
            model_latency_seconds=raw.get("model_latency_seconds", 0.0),
            wall_time_seconds=raw.get("wall_time_seconds"),
            metadata=dict(raw.get("metadata", {})),
        )


def append_evaluation_record(path: str | Path, record: EvaluationRecord) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.dump(), ensure_ascii=False, sort_keys=True) + "\n")


def load_evaluation_records(path: str | Path) -> list[EvaluationRecord]:
    target = Path(path)
    if not target.exists():
        raise EvaluationError(f"evaluation record file does not exist: {target}")
    result: list[EvaluationRecord] = []
    for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationError(f"invalid evaluation JSON at line {line_number}: {exc}") from exc
        if not isinstance(raw, dict):
            raise EvaluationError(f"evaluation line {line_number} must be an object")
        result.append(EvaluationRecord.load(raw))
    return result


class MatchedAblationReport:
    def __init__(self, records: Iterable[EvaluationRecord]):
        self.records = list(records)
        if not self.records:
            raise EvaluationError("ablation report requires at least one record")
        fingerprints = {record.control.fingerprint for record in self.records}
        if len(fingerprints) != 1:
            raise EvaluationError(
                "matched ablation rejected: task/model/profile/tools/budget/oracle/environment controls differ"
            )
        pairs = [(record.arm, record.repeat) for record in self.records]
        if len(pairs) != len(set(pairs)):
            raise EvaluationError("duplicate arm/repeat evaluation record")
        self.control_fingerprint = next(iter(fingerprints))

    @staticmethod
    def _average(records: list[EvaluationRecord], field: str) -> float:
        return mean(float(getattr(record, field)) for record in records)

    def summarize(self) -> dict[str, Any]:
        arms: dict[str, list[EvaluationRecord]] = {}
        for record in self.records:
            arms.setdefault(record.arm, []).append(record)
        output: dict[str, Any] = {}
        for arm, records in sorted(arms.items()):
            records.sort(key=lambda item: item.repeat)
            completed = sum(1 for record in records if record.completed)
            false_completion_requests = sum(
                max(0, record.completion_requests - (1 if record.completed else 0))
                for record in records
            )
            output[arm] = {
                "runs": len(records),
                "completed": completed,
                "solve_rate": completed / len(records),
                "false_completion_requests": false_completion_requests,
                "avg_steps": self._average(records, "steps"),
                "avg_tool_calls": self._average(records, "tool_calls"),
                "avg_failures": self._average(records, "failures"),
                "avg_total_tokens": self._average(records, "total_tokens"),
                "avg_model_requests": self._average(records, "model_requests"),
                "avg_model_latency_seconds": self._average(records, "model_latency_seconds"),
                "avg_wall_time_seconds": (
                    mean(record.wall_time_seconds for record in records if record.wall_time_seconds is not None)
                    if any(record.wall_time_seconds is not None for record in records)
                    else None
                ),
            }
        return {
            "schema_version": "matched-ablation-report-v1",
            "control_fingerprint": self.control_fingerprint,
            "control": self.records[0].control.descriptor(),
            "arms": output,
            "performance_claim_allowed": len(output) >= 2 and all(item["runs"] >= 2 for item in output.values()),
        }
