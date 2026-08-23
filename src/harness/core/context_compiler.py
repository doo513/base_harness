from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any
from urllib.parse import urlparse
import copy
import json


class ContextBudgetError(ValueError):
    """Raised when mandatory actor context cannot fit the selected model route."""


@dataclass(frozen=True)
class RouteContextBudget:
    context_window: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    source: str

    def __post_init__(self) -> None:
        for name in ("context_window", "reserved_output_tokens", "safety_margin_tokens"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ContextBudgetError(f"{name} must be a non-negative integer")
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
                0, self.source_estimated_input_tokens - self.compiled_estimated_input_tokens
            ),
            "estimated_reduction_ratio": round(
                max(0, source - self.compiled_estimated_input_tokens) / source,
                4,
            ),
            "budget": self.budget.dump() if self.budget is not None else None,
        }


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def estimate_tokens(value: Any) -> int:
    """Return a conservative tokenizer-independent admission estimate.

    Three UTF-8 bytes per token intentionally overestimates typical English JSON
    and remains conservative for Hangul-heavy text without coupling the Kernel to
    a provider tokenizer. It is a prompt admission guard, not usage accounting.
    """
    raw = value if isinstance(value, str) else _json_text(value)
    size = len(raw.encode("utf-8"))
    return 0 if size == 0 else max(1, ceil(size / 3))


def _positive_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return int(value)
    return None


def _endpoint_port(endpoint: Any) -> int | None:
    if not isinstance(endpoint, str) or not endpoint:
        return None
    try:
        return urlparse(endpoint).port
    except ValueError:
        return None


def resolve_model_context_budget(model: Any) -> RouteContextBudget | None:
    """Resolve a context budget from a ModelGateway-compatible descriptor.

    Remote routes remain unchanged unless they explicitly declare a context
    window. Ollama/LM Studio routes, including their common compatibility ports,
    default conservatively to 4096. Operators can override this with
    options.context_window or options.num_ctx.
    """
    descriptor_fn = getattr(model, "descriptor", None)
    if not callable(descriptor_fn):
        return None
    try:
        descriptor = descriptor_fn()
    except Exception:
        return None
    if not isinstance(descriptor, dict):
        return None

    alias = descriptor.get("default_model")
    models = descriptor.get("models")
    if not isinstance(alias, str) or not isinstance(models, dict):
        return None
    route = models.get(alias)
    if not isinstance(route, dict):
        return None
    options = route.get("options")
    options = options if isinstance(options, dict) else {}

    provider = str(route.get("provider", "")).strip().lower()
    port = _endpoint_port(route.get("endpoint"))
    local_compat = provider in {"ollama", "lm-studio"} or port in {11434, 1234}

    explicit_window = _positive_int(options.get("context_window"))
    num_ctx = _positive_int(options.get("num_ctx"))
    context_window = explicit_window or num_ctx
    source = "model_option"
    if context_window is None and local_compat:
        context_window = 4096
        source = "local_compat_default"
    if context_window is None:
        return None

    reserved = (
        _positive_int(options.get("reserved_output_tokens"))
        or _positive_int(options.get("num_predict"))
        or _positive_int(options.get("max_tokens"))
        or min(1024, max(512, context_window // 4))
    )
    safety = (
        _positive_int(options.get("context_safety_margin_tokens"))
        or min(512, max(192, context_window // 16))
    )
    return RouteContextBudget(
        context_window=context_window,
        reserved_output_tokens=reserved,
        safety_margin_tokens=safety,
        source=source,
    )


def _trim_text(value: Any, limit: int) -> Any:
    if not isinstance(value, str):
        return value
    if limit < 0:
        return value
    return value if len(value) <= limit else value[:limit]


def _copy_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _compact_failure(item: Any, message_chars: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    result: dict[str, Any] = {}
    for key in (
        "kind",
        "target",
        "repeat_count",
        "generation",
        "recommended_recovery",
        "strategy_generation",
    ):
        if key in item:
            result[key] = copy.deepcopy(item[key])
    if "message" in item:
        result["message"] = _trim_text(str(item.get("message", "")), message_chars)
    return result


def _compact_control(control: Any, *, failure_count: int, failure_chars: int) -> dict[str, Any]:
    source = _copy_mapping(control)
    failures = source.get("recent_failures")
    selected_failures: list[dict[str, Any]] = []
    if isinstance(failures, list) and failure_count > 0:
        for item in failures[-failure_count:]:
            compact = _compact_failure(item, failure_chars)
            if compact is not None:
                selected_failures.append(compact)
    return {
        "step": source.get("step"),
        "recent_failures": selected_failures,
        "recovery_directive": copy.deepcopy(source.get("recovery_directive")),
        "strategy_generation": source.get("strategy_generation"),
        "recovery_halted": source.get("recovery_halted"),
        "recovery_halt_reason": source.get("recovery_halt_reason"),
        "progress": copy.deepcopy(source.get("progress")),
    }


def _compact_tools(tools: Any, *, description_chars: int) -> dict[str, Any]:
    if not isinstance(tools, dict):
        return {}
    result: dict[str, Any] = {}
    for name in sorted(tools):
        raw = tools[name]
        item = raw if isinstance(raw, dict) else {}
        compact: dict[str, Any] = {
            "description": _trim_text(str(item.get("description", "")), description_chars),
            "side_effect": item.get("side_effect"),
            "idempotent": item.get("idempotent"),
        }
        # Tool names/safety metadata and input schemas remain visible. Output
        # schemas are execution-side validation data and are omitted here.
        if isinstance(item.get("input_schema"), dict):
            compact["input_schema"] = copy.deepcopy(item["input_schema"])
        if item.get("input_schema_validation") is not None:
            compact["input_schema_validation"] = item.get("input_schema_validation")
        result[str(name)] = compact
    return result


def _trim_preview(preview: Any, limit: int) -> Any:
    if not isinstance(preview, dict) or not isinstance(preview.get("text"), str):
        return copy.deepcopy(preview)
    result = copy.deepcopy(preview)
    original = result["text"]
    result["text"] = _trim_text(original, limit)
    result["visible_chars"] = len(result["text"])
    try:
        original_chars = int(result.get("original_chars", len(original)))
    except (TypeError, ValueError):
        original_chars = len(original)
    result["truncated"] = bool(result.get("truncated")) or original_chars > len(result["text"])
    return result


def _fact_from_active(item: Any, *, preview_chars: int) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(item, dict):
        return None
    key = item.get("key")
    if not isinstance(key, str) or not key:
        return None
    return key, {
        "key": key,
        "trust": "verified_fact",
        "instruction_authority": "none",
        "authority": item.get("authority"),
        "value_preview": _trim_preview(item.get("value_preview"), preview_chars),
        "evidence_refs": copy.deepcopy(item.get("evidence_refs", [])),
    }


def _claim_from_active(item: Any, *, preview_chars: int) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(item, dict):
        return None
    key = item.get("key")
    if not isinstance(key, str) or not key:
        return None
    return key, {
        "key": key,
        "trust": item.get("trust", "untrusted_speculation"),
        "instruction_authority": "none",
        "value_preview": _trim_preview(item.get("value_preview"), preview_chars),
        "evidence_refs": copy.deepcopy(item.get("evidence_refs", [])),
    }


def _compact_observation(item: Any, *, preview_chars: int) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    result = {
        "source": item.get("source"),
        "step": item.get("step", item.get("latest_step")),
        "ok": item.get("ok"),
        "trust": "untrusted_observation",
        "instruction_authority": "none",
        "artifact_ref": item.get("artifact_ref"),
    }
    preview = item.get("preview")
    if isinstance(preview, dict):
        text = str(preview.get("text", ""))
    elif preview is None:
        text = ""
    else:
        text = str(preview)
    result["preview"] = {
        "text": _trim_text(text, preview_chars),
        "truncated": (
            bool(preview.get("truncated")) if isinstance(preview, dict) else False
        ) or len(text) > preview_chars,
    }
    return result


def _select_verified_facts(
    context: dict[str, Any], *, limit: int, preview_chars: int
) -> dict[str, Any]:
    if limit <= 0:
        return {}
    active = context.get("active_context")
    active_facts = active.get("facts") if isinstance(active, dict) else None
    result: dict[str, Any] = {}
    if isinstance(active_facts, list):
        for item in active_facts[:limit]:
            pair = _fact_from_active(item, preview_chars=preview_chars)
            if pair is not None:
                result[pair[0]] = pair[1]
    if result:
        return result

    trusted = context.get("trusted")
    facts = trusted.get("facts") if isinstance(trusted, dict) else None
    if not isinstance(facts, dict):
        return {}
    for key in list(facts)[:limit]:
        item = copy.deepcopy(facts[key])
        if isinstance(item, dict):
            item["value_preview"] = _trim_preview(item.get("value_preview"), preview_chars)
            if "value" in item and item.get("value_preview") is not None:
                item["value"] = None
            result[str(key)] = item
    return result


def _select_hypotheses(
    context: dict[str, Any], *, limit: int, preview_chars: int
) -> dict[str, Any]:
    if limit <= 0:
        return {}
    active = context.get("active_context")
    active_items = active.get("hypotheses") if isinstance(active, dict) else None
    result: dict[str, Any] = {}
    if isinstance(active_items, list):
        for item in active_items[:limit]:
            pair = _claim_from_active(item, preview_chars=preview_chars)
            if pair is not None:
                result[pair[0]] = pair[1]
    if result:
        return result

    untrusted = context.get("untrusted")
    items = untrusted.get("hypotheses") if isinstance(untrusted, dict) else None
    if not isinstance(items, dict):
        return {}
    for key in list(items)[:limit]:
        item = copy.deepcopy(items[key])
        if isinstance(item, dict):
            item["value_preview"] = _trim_preview(item.get("value_preview"), preview_chars)
            result[str(key)] = item
    return result


def _select_observations(
    context: dict[str, Any], *, limit: int, preview_chars: int
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    active = context.get("active_context")
    active_items = active.get("observations") if isinstance(active, dict) else None
    source_items: list[Any] = []
    if isinstance(active_items, list) and active_items:
        source_items = active_items[:limit]
    else:
        untrusted = context.get("untrusted")
        raw = untrusted.get("observations") if isinstance(untrusted, dict) else None
        if isinstance(raw, list):
            source_items = raw[:limit]
    result: list[dict[str, Any]] = []
    for item in source_items:
        compact = _compact_observation(item, preview_chars=preview_chars)
        if compact is not None:
            result.append(compact)
    return result


def _select_unknowns(context: dict[str, Any], limit: int, chars: int) -> list[Any]:
    if limit <= 0:
        return []
    untrusted = context.get("untrusted")
    raw = untrusted.get("unknowns") if isinstance(untrusted, dict) else None
    if not isinstance(raw, list):
        return []
    result: list[Any] = []
    for item in raw[-limit:]:
        if isinstance(item, dict):
            copy_item = copy.deepcopy(item)
            if isinstance(copy_item.get("text"), str):
                copy_item["text"] = _trim_text(copy_item["text"], chars)
            result.append(copy_item)
        else:
            result.append(_trim_text(str(item), chars))
    return result


def _select_retrieval(
    context: dict[str, Any], *, limit: int, preview_chars: int
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    untrusted = context.get("untrusted")
    raw = untrusted.get("retrieval") if isinstance(untrusted, dict) else None
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw[:limit]:
        if not isinstance(item, dict):
            continue
        compact = {
            "item_id": item.get("item_id"),
            "content_ref": item.get("content_ref"),
            "source_id": item.get("source_id"),
            "source_revision": item.get("source_revision"),
            "source_locator": item.get("source_locator"),
            "trust": "untrusted_retrieval",
            "instruction_authority": "none",
        }
        preview = item.get("preview")
        if isinstance(preview, dict):
            text = str(preview.get("text", ""))
            compact["preview"] = {
                "text": _trim_text(text, preview_chars),
                "truncated": bool(preview.get("truncated")) or len(text) > preview_chars,
            }
        result.append(compact)
    return result


def _compact_agent_workflow(value: Any, *, task_limit: int, text_chars: int) -> Any:
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    result: dict[str, Any] = {}
    for key in ("schema_version", "objective", "active_task_id"):
        if key in value:
            result[key] = copy.deepcopy(value[key])
    if isinstance(result.get("objective"), str):
        result["objective"] = _trim_text(result["objective"], text_chars)

    tasks = value.get("tasks")
    if isinstance(tasks, list):
        selected = tasks[:task_limit]
        compact_tasks = []
        for item in selected:
            if not isinstance(item, dict):
                continue
            compact = {
                key: copy.deepcopy(item.get(key))
                for key in ("id", "status", "depends_on")
                if key in item
            }
            if isinstance(item.get("title"), str):
                compact["title"] = _trim_text(item["title"], text_chars)
            if isinstance(item.get("note"), str) and item["note"]:
                compact["note"] = _trim_text(item["note"], text_chars)
            compact_tasks.append(compact)
        result["tasks"] = compact_tasks
    elif isinstance(tasks, dict):
        compact_tasks: dict[str, Any] = {}
        for key in list(tasks)[:task_limit]:
            item = tasks[key]
            if not isinstance(item, dict):
                continue
            compact = {
                field: copy.deepcopy(item.get(field))
                for field in ("id", "status", "depends_on")
                if field in item
            }
            if isinstance(item.get("title"), str):
                compact["title"] = _trim_text(item["title"], text_chars)
            if isinstance(item.get("note"), str) and item["note"]:
                compact["note"] = _trim_text(item["note"], text_chars)
            compact_tasks[str(key)] = compact
        result["tasks"] = compact_tasks
    for key in ("plan_revision", "plan_status"):
        if key in value:
            result[key] = copy.deepcopy(value[key])
    return result


def _compact_domain_contract(value: Any, *, keep_workflow: bool, keep_evaluation: bool) -> Any:
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    result = {
        "profile": value.get("profile"),
        "authority": value.get("authority"),
        "evaluation_truth_authority": value.get("evaluation_truth_authority"),
        "evaluation_progress_authority": value.get("evaluation_progress_authority"),
        "evaluation_completion_authority": value.get("evaluation_completion_authority"),
    }
    if keep_workflow:
        result["workflow"] = copy.deepcopy(value.get("workflow"))
    if keep_evaluation:
        result["evaluation"] = copy.deepcopy(value.get("evaluation"))
    return result


_LEVELS = (
    {
        "fact_count": 12,
        "fact_chars": 600,
        "hypothesis_count": 5,
        "hypothesis_chars": 400,
        "observation_count": 5,
        "observation_chars": 500,
        "unknown_count": 4,
        "unknown_chars": 240,
        "retrieval_count": 3,
        "retrieval_chars": 500,
        "failure_count": 2,
        "failure_chars": 400,
        "tool_description_chars": 180,
        "task_limit": 12,
        "task_text_chars": 300,
        "keep_domain_workflow": True,
        "keep_domain_evaluation": True,
    },
    {
        "fact_count": 10,
        "fact_chars": 420,
        "hypothesis_count": 4,
        "hypothesis_chars": 300,
        "observation_count": 4,
        "observation_chars": 360,
        "unknown_count": 3,
        "unknown_chars": 180,
        "retrieval_count": 2,
        "retrieval_chars": 360,
        "failure_count": 2,
        "failure_chars": 300,
        "tool_description_chars": 130,
        "task_limit": 10,
        "task_text_chars": 220,
        "keep_domain_workflow": True,
        "keep_domain_evaluation": False,
    },
    {
        "fact_count": 8,
        "fact_chars": 300,
        "hypothesis_count": 2,
        "hypothesis_chars": 220,
        "observation_count": 3,
        "observation_chars": 260,
        "unknown_count": 2,
        "unknown_chars": 140,
        "retrieval_count": 1,
        "retrieval_chars": 260,
        "failure_count": 1,
        "failure_chars": 240,
        "tool_description_chars": 90,
        "task_limit": 8,
        "task_text_chars": 180,
        "keep_domain_workflow": True,
        "keep_domain_evaluation": False,
    },
    {
        "fact_count": 5,
        "fact_chars": 200,
        "hypothesis_count": 0,
        "hypothesis_chars": 0,
        "observation_count": 1,
        "observation_chars": 180,
        "unknown_count": 0,
        "unknown_chars": 0,
        "retrieval_count": 1,
        "retrieval_chars": 180,
        "failure_count": 1,
        "failure_chars": 180,
        "tool_description_chars": 60,
        "task_limit": 5,
        "task_text_chars": 140,
        "keep_domain_workflow": False,
        "keep_domain_evaluation": False,
    },
    {
        "fact_count": 2,
        "fact_chars": 120,
        "hypothesis_count": 0,
        "hypothesis_chars": 0,
        "observation_count": 0,
        "observation_chars": 0,
        "unknown_count": 0,
        "unknown_chars": 0,
        "retrieval_count": 1,
        "retrieval_chars": 120,
        "failure_count": 1,
        "failure_chars": 120,
        "tool_description_chars": 30,
        "task_limit": 3,
        "task_text_chars": 100,
        "keep_domain_workflow": False,
        "keep_domain_evaluation": False,
    },
)


def _build_compact_context(context: dict[str, Any], level: int) -> dict[str, Any]:
    policy = _LEVELS[level]
    result: dict[str, Any] = {
        "schema_version": "working-context-v1",
        "projection": {
            "source_schema_version": context.get("schema_version"),
            "compiler": "token-aware-context-compiler-v1",
            "lossy_visibility_only": True,
            "durable_state_mutated": False,
            "raw_evidence_preserved": True,
            "active_context_folded_into_primary_namespaces": True,
        },
        "goal_contract": copy.deepcopy(context.get("goal_contract", {})),
        "trusted": {
            "facts": _select_verified_facts(
                context,
                limit=policy["fact_count"],
                preview_chars=policy["fact_chars"],
            ),
            "superseded_fact_keys": [],
        },
        "untrusted": {
            "hypotheses": _select_hypotheses(
                context,
                limit=policy["hypothesis_count"],
                preview_chars=policy["hypothesis_chars"],
            ),
            "refuted_hypotheses": {},
            "observations": _select_observations(
                context,
                limit=policy["observation_count"],
                preview_chars=policy["observation_chars"],
            ),
            "unknowns": _select_unknowns(
                context,
                policy["unknown_count"],
                policy["unknown_chars"],
            ),
            "retrieval": _select_retrieval(
                context,
                limit=policy["retrieval_count"],
                preview_chars=policy["retrieval_chars"],
            ),
        },
        "control": _compact_control(
            context.get("control"),
            failure_count=policy["failure_count"],
            failure_chars=policy["failure_chars"],
        ),
        "tools": _compact_tools(
            context.get("tools"),
            description_chars=policy["tool_description_chars"],
        ),
    }
    if "agent_workflow" in context:
        result["agent_workflow"] = _compact_agent_workflow(
            context.get("agent_workflow"),
            task_limit=policy["task_limit"],
            text_chars=policy["task_text_chars"],
        )
    if "project_memory" in context:
        result["project_memory"] = copy.deepcopy(context.get("project_memory"))
    if "domain_contract" in context:
        result["domain_contract"] = _compact_domain_contract(
            context.get("domain_contract"),
            keep_workflow=policy["keep_domain_workflow"],
            keep_evaluation=policy["keep_domain_evaluation"],
        )
    return result


def compile_context_for_model(
    *, model: Any, system: str, context: Any
) -> ContextCompileResult:
    """Compile the model-visible projection into a route-bounded working context.

    The source projection remains durable and untouched. When no route budget is
    known, the existing projection is passed through unchanged. For a bounded
    route, additive active-context data is folded into the canonical namespaces
    and progressively reduced until the request fits the route budget.
    """
    visible = copy.deepcopy(dict(context)) if isinstance(context, dict) else {}
    source_user = {"context": visible}
    source_estimated = estimate_tokens(system) + estimate_tokens(source_user)
    budget = resolve_model_context_budget(model)

    if budget is None:
        return ContextCompileResult(
            context=visible,
            mode="passthrough",
            source_estimated_input_tokens=source_estimated,
            compiled_estimated_input_tokens=source_estimated,
            budget=None,
            level=0,
        )

    system_tokens = estimate_tokens(system)
    if system_tokens >= budget.max_input_tokens:
        raise ContextBudgetError(
            "system prompt alone exceeds model input budget: "
            f"estimated={system_tokens}, max_input={budget.max_input_tokens}"
        )

    for level in range(len(_LEVELS)):
        compiled = _build_compact_context(visible, level)
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
        "mandatory/compact context exceeds model input budget after all bounded "
        f"compiler levels: estimated>{budget.max_input_tokens}, "
        f"context_window={budget.context_window}"
    )
