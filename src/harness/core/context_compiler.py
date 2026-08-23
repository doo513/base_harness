from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any
from urllib.parse import urlparse
import copy
import json


class ContextBudgetError(ValueError):
    """Selected model route cannot fit the mandatory working context."""


@dataclass(frozen=True)
class RouteContextBudget:
    context_window: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    source: str

    def __post_init__(self) -> None:
        values = (
            self.context_window,
            self.reserved_output_tokens,
            self.safety_margin_tokens,
        )
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in values):
            raise ContextBudgetError("context budget values must be non-negative integers")
        if self.context_window < 1:
            raise ContextBudgetError("context_window must be positive")
        if self.reserved_output_tokens + self.safety_margin_tokens >= self.context_window:
            raise ContextBudgetError("context reserve leaves no input budget")

    @property
    def max_input_tokens(self) -> int:
        return self.context_window - self.reserved_output_tokens - self.safety_margin_tokens

    def dump(self) -> dict[str, Any]:
        return {
            "context_window": self.context_window,
            "reserved_output_tokens": self.reserved_output_tokens,
            "safety_margin_tokens": self.safety_margin_tokens,
            "max_input_tokens": self.max_input_tokens,
            "source": self.source,
        }


@dataclass(frozen=True)
class ContextCompileResult:
    context: dict[str, Any]
    mode: str
    source_estimated_input_tokens: int
    compiled_estimated_input_tokens: int
    budget: RouteContextBudget | None
    level: int = 0

    def telemetry(self) -> dict[str, Any]:
        source = max(1, self.source_estimated_input_tokens)
        return {
            "schema_version": "context-compile-telemetry-v1",
            "mode": self.mode,
            "level": self.level,
            "source_estimated_input_tokens": self.source_estimated_input_tokens,
            "compiled_estimated_input_tokens": self.compiled_estimated_input_tokens,
            "estimated_reduction_tokens": max(
                0,
                self.source_estimated_input_tokens - self.compiled_estimated_input_tokens,
            ),
            "estimated_reduction_ratio": round(
                max(0, source - self.compiled_estimated_input_tokens) / source,
                4,
            ),
            "budget": self.budget.dump() if self.budget else None,
        }


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def estimate_tokens(value: Any) -> int:
    """Conservative tokenizer-independent admission estimate.

    The compiler uses UTF-8 bytes / 3 as a guard. It intentionally does not
    claim exact provider token accounting.
    """
    text = value if isinstance(value, str) else _json(value)
    size = len(text.encode("utf-8"))
    return 0 if size == 0 else max(1, ceil(size / 3))


def _positive_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _port(endpoint: Any) -> int | None:
    if not isinstance(endpoint, str) or not endpoint:
        return None
    try:
        return urlparse(endpoint).port
    except ValueError:
        return None


def resolve_model_context_budget(model: Any) -> RouteContextBudget | None:
    """Read route budget metadata without querying mutable provider state."""
    descriptor = getattr(model, "descriptor", None)
    if not callable(descriptor):
        return None
    try:
        raw = descriptor()
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None

    alias = raw.get("default_model")
    models = raw.get("models")
    route = models.get(alias) if isinstance(alias, str) and isinstance(models, dict) else None
    if not isinstance(route, dict):
        return None

    options = route.get("options")
    options = options if isinstance(options, dict) else {}
    provider = str(route.get("provider", "")).strip().lower()
    local = provider in {"ollama", "lm-studio"} or _port(route.get("endpoint")) in {11434, 1234}

    window = _positive_int(options.get("context_window"))
    source = "model_option"
    if window is None and local:
        window = 4096
        source = "local_compat_default"
    if window is None:
        return None

    reserved = (
        _positive_int(options.get("reserved_output_tokens"))
        or _positive_int(options.get("num_predict"))
        or _positive_int(options.get("max_tokens"))
        or min(1024, max(512, window // 4))
    )
    safety = (
        _positive_int(options.get("context_safety_margin_tokens"))
        or min(512, max(192, window // 16))
    )
    return RouteContextBudget(window, reserved, safety, source)


def _text(value: Any, limit: int) -> str:
    raw = "" if value is None else str(value)
    return raw if len(raw) <= limit else raw[:limit]


def _preview(value: Any, limit: int) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    raw = str(value.get("text", ""))
    visible = _text(raw, limit)
    result = {
        "text": visible,
        "visible_chars": len(visible),
        "truncated": bool(value.get("truncated")) or len(raw) > len(visible),
    }
    if value.get("original_chars") is not None:
        result["original_chars"] = value.get("original_chars")
    return result


def _active_by_key(context: dict[str, Any], kind: str, limit: int) -> dict[str, dict[str, Any]]:
    active = context.get("active_context")
    items = active.get(kind) if isinstance(active, dict) else None
    result: dict[str, dict[str, Any]] = {}
    if isinstance(items, list):
        for item in items[:limit]:
            if isinstance(item, dict) and isinstance(item.get("key"), str):
                result[item["key"]] = item
    return result


def _facts(context: dict[str, Any], *, active_limit: int, active_chars: int, rich_stub: bool):
    trusted = context.get("trusted")
    raw_facts = trusted.get("facts") if isinstance(trusted, dict) else None
    if not isinstance(raw_facts, dict):
        return {}

    active = _active_by_key(context, "facts", active_limit)
    output: dict[str, Any] = {}
    for key, raw in raw_facts.items():
        if not isinstance(raw, dict):
            continue
        focus = active.get(str(key))
        item: dict[str, Any] = {
            "key": raw.get("key", str(key)),
            "status": raw.get("status"),
            "authority": raw.get("authority"),
            "trust": "verified_fact",
            "instruction_authority": "none",
        }
        if focus is not None:
            item["value_preview"] = _preview(
                focus.get("value_preview", raw.get("value_preview")),
                active_chars,
            )
            refs = focus.get("evidence_refs")
            if not isinstance(refs, list):
                refs = raw.get("evidence_refs")
            if isinstance(refs, list) and refs:
                item["evidence_refs"] = copy.deepcopy(refs[:2])
            if raw.get("value_hash") is not None:
                item["value_hash"] = raw.get("value_hash")
        elif rich_stub:
            item["value_preview"] = _preview(raw.get("value_preview"), min(80, active_chars))
            if raw.get("value_hash") is not None:
                item["value_hash"] = raw.get("value_hash")
        if raw.get("valid_until") is not None:
            item["valid_until"] = raw.get("valid_until")
        output[str(key)] = item
    return output


def _hypotheses(context: dict[str, Any], *, count: int, chars: int):
    if count <= 0:
        return {}
    active = _active_by_key(context, "hypotheses", count)
    output: dict[str, Any] = {}
    for key, item in active.items():
        output[key] = {
            "key": key,
            "trust": "untrusted_speculation",
            "instruction_authority": "none",
            "value_preview": _preview(item.get("value_preview"), chars),
            "evidence_refs": copy.deepcopy(item.get("evidence_refs", [])[:2])
            if isinstance(item.get("evidence_refs"), list)
            else [],
        }
    if output:
        return output

    untrusted = context.get("untrusted")
    raw = untrusted.get("hypotheses") if isinstance(untrusted, dict) else None
    if not isinstance(raw, dict):
        return {}
    for key in list(raw)[:count]:
        item = raw[key]
        if not isinstance(item, dict):
            continue
        output[str(key)] = {
            "key": item.get("key", str(key)),
            "trust": "untrusted_speculation",
            "instruction_authority": "none",
            "value_preview": _preview(item.get("value_preview"), chars),
        }
    return output


def _observations(context: dict[str, Any], *, count: int, chars: int):
    if count <= 0:
        return []
    active = context.get("active_context")
    items = active.get("observations") if isinstance(active, dict) else None
    if not isinstance(items, list) or not items:
        untrusted = context.get("untrusted")
        items = untrusted.get("observations") if isinstance(untrusted, dict) else None
    if not isinstance(items, list):
        return []

    output = []
    for raw in items[:count]:
        if not isinstance(raw, dict):
            continue
        p = raw.get("preview")
        p_text = p.get("text") if isinstance(p, dict) else p
        output.append({
            "source": raw.get("source"),
            "step": raw.get("step", raw.get("latest_step")),
            "ok": raw.get("ok"),
            "artifact_ref": raw.get("artifact_ref"),
            "trust": "untrusted_observation",
            "instruction_authority": "none",
            "preview": {
                "text": _text(p_text, chars),
                "truncated": (
                    bool(p.get("truncated")) if isinstance(p, dict) else False
                ) or len(str(p_text or "")) > chars,
            },
        })
    return output


def _retrieval(context: dict[str, Any], *, count: int, chars: int):
    if count <= 0:
        return []
    untrusted = context.get("untrusted")
    items = untrusted.get("retrieval") if isinstance(untrusted, dict) else None
    if not isinstance(items, list):
        return []

    output = []
    for raw in items[:count]:
        if not isinstance(raw, dict):
            continue
        p = raw.get("preview")
        text = p.get("text") if isinstance(p, dict) else ""
        output.append({
            "item_id": raw.get("item_id"),
            "content_ref": raw.get("content_ref"),
            "source_id": raw.get("source_id"),
            "source_revision": raw.get("source_revision"),
            "source_locator": raw.get("source_locator"),
            "trust": "untrusted_retrieval",
            "instruction_authority": "none",
            "preview": {
                "text": _text(text, chars),
                "truncated": (
                    bool(p.get("truncated")) if isinstance(p, dict) else False
                ) or len(str(text or "")) > chars,
            },
        })
    return output


def _control(context: dict[str, Any], *, failure_chars: int):
    raw = context.get("control")
    raw = raw if isinstance(raw, dict) else {}
    failures = raw.get("recent_failures")
    recent = []
    if isinstance(failures, list) and failures:
        item = failures[-1]
        if isinstance(item, dict):
            recent.append({
                key: copy.deepcopy(item.get(key))
                for key in ("kind", "target", "repeat_count", "recommended_recovery")
                if key in item
            })
            recent[-1]["message"] = _text(item.get("message"), failure_chars)
    return {
        "step": raw.get("step"),
        "recent_failures": recent,
        "recovery_directive": copy.deepcopy(raw.get("recovery_directive")),
        "strategy_generation": raw.get("strategy_generation"),
        "recovery_halted": raw.get("recovery_halted"),
        "recovery_halt_reason": raw.get("recovery_halt_reason"),
        "progress": copy.deepcopy(raw.get("progress")),
    }


def _tools(context: dict[str, Any], *, description_chars: int):
    raw = context.get("tools")
    if not isinstance(raw, dict):
        return {}
    output: dict[str, Any] = {}
    for name in sorted(raw):
        item = raw[name] if isinstance(raw[name], dict) else {}
        value = {
            "description": _text(item.get("description"), description_chars),
            "side_effect": item.get("side_effect"),
            "idempotent": item.get("idempotent"),
        }
        if isinstance(item.get("input_schema"), dict):
            value["input_schema"] = copy.deepcopy(item["input_schema"])
        if item.get("input_schema_validation") is not None:
            value["input_schema_validation"] = item.get("input_schema_validation")
        output[name] = value
    return output


def _workflow(context: dict[str, Any], *, task_count: int, chars: int):
    raw = context.get("agent_workflow")
    if not isinstance(raw, dict):
        return None
    output = {
        "objective": _text(raw.get("objective"), chars),
        "active_task_id": raw.get("active_task_id"),
    }
    tasks = raw.get("tasks")
    if isinstance(tasks, list):
        output["tasks"] = [
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "title": _text(item.get("title"), chars),
                "depends_on": copy.deepcopy(item.get("depends_on", [])),
            }
            for item in tasks[:task_count]
            if isinstance(item, dict)
        ]
    elif isinstance(tasks, dict):
        selected = []
        for key in list(tasks)[:task_count]:
            item = tasks[key]
            if isinstance(item, dict):
                selected.append({
                    "id": item.get("id", key),
                    "status": item.get("status"),
                    "title": _text(item.get("title"), chars),
                    "depends_on": copy.deepcopy(item.get("depends_on", [])),
                })
        output["tasks"] = selected
    return output


_LEVELS = (
    (12, 500, True, 4, 320, 4, 360, 2, 320, 260, 160, 10, 220, True),
    (10, 360, True, 3, 240, 3, 260, 1, 240, 220, 120, 8, 180, False),
    (8, 260, True, 2, 180, 2, 200, 1, 180, 180, 80, 6, 140, False),
    (5, 180, False, 0, 0, 1, 140, 1, 120, 140, 40, 4, 110, False),
    (3, 120, False, 0, 0, 0, 0, 1, 80, 100, 0, 3, 90, False),
)


def _build(context: dict[str, Any], level: int):
    (
        fact_active_count,
        fact_chars,
        rich_fact_stub,
        hypothesis_count,
        hypothesis_chars,
        observation_count,
        observation_chars,
        retrieval_count,
        retrieval_chars,
        failure_chars,
        tool_description_chars,
        task_count,
        task_chars,
        keep_domain_workflow,
    ) = _LEVELS[level]

    trusted_source = context.get("trusted")
    superseded = (
        copy.deepcopy(trusted_source.get("superseded_fact_keys", []))
        if isinstance(trusted_source, dict)
        else []
    )
    output: dict[str, Any] = {
        "schema_version": "working-context-v1",
        "projection": {
            "compiler": "token-aware-context-compiler-v1",
            "source_schema_version": context.get("schema_version"),
            "lossy_visibility_only": True,
            "raw_evidence_preserved": True,
            "durable_state_mutated": False,
            "active_context_folded": True,
        },
        "goal_contract": copy.deepcopy(context.get("goal_contract", {})),
        "trusted": {
            "facts": _facts(
                context,
                active_limit=fact_active_count,
                active_chars=fact_chars,
                rich_stub=rich_fact_stub,
            ),
            "superseded_fact_keys": superseded,
        },
        "untrusted": {
            "hypotheses": _hypotheses(
                context,
                count=hypothesis_count,
                chars=hypothesis_chars,
            ),
            "refuted_hypotheses": {},
            "observations": _observations(
                context,
                count=observation_count,
                chars=observation_chars,
            ),
            "unknowns": [],
            "retrieval": _retrieval(
                context,
                count=retrieval_count,
                chars=retrieval_chars,
            ),
        },
        "control": _control(context, failure_chars=failure_chars),
        "tools": _tools(context, description_chars=tool_description_chars),
    }

    workflow = _workflow(context, task_count=task_count, chars=task_chars)
    if workflow is not None:
        output["agent_workflow"] = workflow

    memory = context.get("project_memory")
    if isinstance(memory, dict):
        output["project_memory"] = {
            key: copy.deepcopy(memory.get(key))
            for key in ("enabled", "trust", "instruction_authority", "read_protocol")
            if key in memory
        }

    domain = context.get("domain_contract")
    if isinstance(domain, dict):
        output["domain_contract"] = {
            "profile": domain.get("profile"),
            "authority": domain.get("authority"),
        }
        if keep_domain_workflow:
            output["domain_contract"]["workflow"] = copy.deepcopy(domain.get("workflow"))

    return output


def compile_context_for_model(*, model: Any, system: str, context: Any) -> ContextCompileResult:
    """Create the model working set without mutating durable ContextProjection."""
    visible = copy.deepcopy(dict(context)) if isinstance(context, dict) else {}
    source_estimated = estimate_tokens(system) + estimate_tokens({"context": visible})
    budget = resolve_model_context_budget(model)

    if budget is None:
        return ContextCompileResult(
            context=visible,
            mode="passthrough",
            source_estimated_input_tokens=source_estimated,
            compiled_estimated_input_tokens=source_estimated,
            budget=None,
        )

    system_tokens = estimate_tokens(system)
    if system_tokens >= budget.max_input_tokens:
        raise ContextBudgetError(
            f"system prompt estimated={system_tokens} exceeds max_input={budget.max_input_tokens}"
        )

    for level in range(len(_LEVELS)):
        compiled = _build(visible, level)
        estimated = system_tokens + estimate_tokens({"context": compiled})
        if estimated <= budget.max_input_tokens:
            return ContextCompileResult(
                context=compiled,
                mode="selective",
                source_estimated_input_tokens=source_estimated,
                compiled_estimated_input_tokens=estimated,
                budget=budget,
                level=level,
            )

    raise ContextBudgetError(
        "mandatory working context cannot fit selected model route: "
        f"max_input={budget.max_input_tokens}, context_window={budget.context_window}"
    )