from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from statistics import mean
from time import monotonic
import tomllib
from typing import Any, Callable

from harness.opencode_adapter import (
    DEFAULT_OPENCODE_AGENT,
    OpenCodeAdapterError,
    OpenCodeRunResult,
    run_opencode_decision,
)


BENCHMARK_SCHEMA = "model-protocol-benchmark-v1"


@dataclass(frozen=True)
class ProtocolCase:
    case_id: str
    system: str
    user: str


@dataclass(frozen=True)
class ProbeOutcome:
    ok: bool
    error_kind: str | None
    lexical_repaired: bool
    lexical_repair_kind: str | None
    structured_output_tool_uses: int
    external_tool_uses: int
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    latency_seconds: float


_CASES: tuple[ProtocolCase, ...] = (
    ProtocolCase(
        "complete-simple",
        "Return exactly one Harness Decision JSON object and no commentary.",
        'Return a complete decision with reason "protocol probe complete".',
    ),
    ProtocolCase(
        "complete-string-escaping",
        "Return exactly one Harness Decision JSON object and no commentary.",
        "Return a complete decision. The reason should communicate two short lines of text while remaining valid JSON.",
    ),
    ProtocolCase(
        "tool-shape",
        "Return exactly one Harness Decision JSON object and no commentary. Do not execute tools.",
        'Return a tool decision requesting tool "directory.list" with args {"path":"."}. Return the request only.',
    ),
    ProtocolCase(
        "plan-shape",
        "Return exactly one Harness Decision JSON object and no commentary.",
        "Return a plan decision with objective 'inspect safely' and exactly two tasks t1 then t2, where t2 depends on t1.",
    ),
    ProtocolCase(
        "retrieve-shape",
        "Return exactly one Harness Decision JSON object and no commentary.",
        'Return a retrieve decision with query "current verified evidence".',
    ),
)


def protocol_cases() -> tuple[ProtocolCase, ...]:
    return _CASES


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * p))))
    return ordered[index]


def _probe(
    invoke: Callable[[ProtocolCase], OpenCodeRunResult],
    case: ProtocolCase,
) -> ProbeOutcome:
    started = monotonic()
    try:
        result = invoke(case)
    except OpenCodeAdapterError as exc:
        return ProbeOutcome(
            ok=False,
            error_kind=exc.kind,
            lexical_repaired=False,
            lexical_repair_kind=None,
            structured_output_tool_uses=0,
            external_tool_uses=1 if exc.kind == "protocol_boundary_violation" else 0,
            input_tokens=None,
            output_tokens=None,
            reasoning_tokens=None,
            latency_seconds=monotonic() - started,
        )
    return ProbeOutcome(
        ok=True,
        error_kind=None,
        lexical_repaired=result.protocol_repaired,
        lexical_repair_kind=result.protocol_repair_kind,
        structured_output_tool_uses=result.structured_output_tool_uses,
        external_tool_uses=result.external_tool_uses,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        reasoning_tokens=result.reasoning_tokens,
        latency_seconds=monotonic() - started,
    )


def run_protocol_benchmark(
    *,
    model_ref: str,
    invoke: Callable[[ProtocolCase], OpenCodeRunResult],
    samples: int,
    transport: str = "opencode-cli-text",
) -> dict[str, Any]:
    if samples < 1:
        raise ValueError("samples must be positive")
    cases = protocol_cases()
    outcomes: list[ProbeOutcome] = []
    per_case: dict[str, Counter[str]] = {case.case_id: Counter() for case in cases}

    for index in range(samples):
        case = cases[index % len(cases)]
        outcome = _probe(invoke, case)
        outcomes.append(outcome)
        if outcome.ok:
            per_case[case.case_id]["valid"] += 1
            if outcome.lexical_repaired:
                per_case[case.case_id]["lexical_repaired"] += 1
        else:
            per_case[case.case_id][outcome.error_kind or "unknown_error"] += 1

    valid = sum(item.ok for item in outcomes)
    lexical_repairs = sum(item.lexical_repaired for item in outcomes)
    external_tool_uses = sum(item.external_tool_uses for item in outcomes)
    structured_tool_uses = sum(item.structured_output_tool_uses for item in outcomes)
    error_kinds = Counter(
        item.error_kind for item in outcomes if item.error_kind is not None
    )
    latencies = [item.latency_seconds for item in outcomes]

    def token_sum(field: str) -> int | None:
        values = [getattr(item, field) for item in outcomes]
        known = [value for value in values if isinstance(value, int)]
        return sum(known) if known else None

    protocol_errors = sum(
        count for kind, count in error_kinds.items()
        if kind.startswith("protocol_")
    )
    return {
        "schema_version": BENCHMARK_SCHEMA,
        "scope": "protocol_compatibility_not_task_competence",
        "route": {
            "model_ref": model_ref,
            "transport": transport,
            "fixed_model": True,
            "fallback_disabled": True,
            "harness_tool_execution": False,
        },
        "samples": {
            "requested": samples,
            "valid": valid,
            "valid_rate": round(valid / samples, 4),
            "lexical_repairs": lexical_repairs,
            "lexical_repair_rate": round(lexical_repairs / samples, 4),
            "protocol_failures": protocol_errors,
            "protocol_failure_rate": round(protocol_errors / samples, 4),
            "external_tool_violations": external_tool_uses,
            "structured_output_internal_uses": structured_tool_uses,
            "error_kinds": dict(sorted(error_kinds.items())),
        },
        "cases": {
            case_id: dict(sorted(counts.items()))
            for case_id, counts in sorted(per_case.items())
        },
        "usage": {
            "input_tokens": token_sum("input_tokens"),
            "output_tokens": token_sum("output_tokens"),
            "reasoning_tokens": token_sum("reasoning_tokens"),
        },
        "latency_seconds": {
            "mean": round(mean(latencies), 6) if latencies else None,
            "p95": round(_percentile(latencies, 0.95), 6) if latencies else None,
            "max": round(max(latencies), 6) if latencies else None,
        },
    }


def _load_opencode_route(config_path: str | Path, alias: str) -> dict[str, Any]:
    path = Path(config_path).expanduser()
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    route = models.get(alias) if isinstance(models, dict) else None
    if not isinstance(route, dict):
        raise ValueError(f"model alias is not configured: {alias}")
    options = route.get("options") if isinstance(route.get("options"), dict) else {}
    model_ref = route.get("model")
    if options.get("adapter") != "opencode" or not isinstance(model_ref, str) or not model_ref:
        raise ValueError(f"model alias is not an OpenCode route: {alias}")
    return {
        "model_ref": model_ref,
        "binary": str(options.get("opencode_binary") or "opencode"),
        "agent": str(options.get("opencode_agent") or DEFAULT_OPENCODE_AGENT),
        "timeout_seconds": float(route.get("timeout_seconds") or 240.0),
        "catalog_name": options.get("catalog_name"),
        "catalog_explicitly_free": options.get("catalog_explicitly_free"),
        "context_window": options.get("context_window"),
    }


def benchmark_configured_opencode(
    config_path: str | Path,
    *,
    alias: str = "opencode",
    samples: int = 100,
) -> dict[str, Any]:
    route = _load_opencode_route(config_path, alias)

    def invoke(case: ProtocolCase) -> OpenCodeRunResult:
        return run_opencode_decision(
            system=case.system,
            user=case.user,
            binary=route["binary"],
            model=route["model_ref"],
            agent=route["agent"],
            timeout_seconds=route["timeout_seconds"],
        )

    report = run_protocol_benchmark(
        model_ref=route["model_ref"],
        invoke=invoke,
        samples=samples,
    )
    report["route"]["alias"] = alias
    report["route"]["catalog_name"] = route["catalog_name"]
    report["route"]["catalog_explicitly_free"] = route["catalog_explicitly_free"]
    report["route"]["context_window"] = route["context_window"]
    return report


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure OpenCode model protocol compatibility without executing Harness tools."
    )
    parser.add_argument("config", nargs="?", default="harness.toml")
    parser.add_argument("--alias", default="opencode")
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    try:
        report = benchmark_configured_opencode(
            args.config,
            alias=args.alias,
            samples=args.samples,
        )
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        parser.error(str(exc))
        raise AssertionError("argparse.error terminates")

    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        path = Path(args.output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8", newline="")
    print(rendered)
    return 0 if report["samples"]["external_tool_violations"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(_main())
