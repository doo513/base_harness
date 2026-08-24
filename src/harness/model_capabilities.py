from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
import argparse
import json

from harness.model_protocol import OutputContract, OutputEnforcement


# These defaults describe the capability actually consumed by the current
# Harness route, not every feature the underlying vendor/model might expose.
_FEATURE_DEFAULTS: dict[str, dict[str, bool]] = {
    "command": {
        "structured_output": False,
        "native_tool_calling": False,
        "streaming": False,
        "vision": False,
        "reasoning": False,
    },
    "openai": {
        "structured_output": False,
        "native_tool_calling": False,
        "streaming": False,
        "vision": False,
        "reasoning": False,
    },
    "openai-compatible": {
        "structured_output": False,
        "native_tool_calling": False,
        "streaming": False,
        "vision": False,
        "reasoning": False,
    },
    "ollama": {
        "structured_output": True,
        "native_tool_calling": False,
        "streaming": False,
        "vision": False,
        "reasoning": True,
    },
    "lm-studio": {
        "structured_output": True,
        "native_tool_calling": False,
        "streaming": False,
        "vision": False,
        "reasoning": False,
    },
}

_ADAPTER_FEATURES: dict[str, dict[str, bool]] = {
    # The current OpenCode CLI bridge validates model text after generation and
    # exposes only one canonical Harness decision. It does not grant OpenCode
    # native/action tool authority.
    "opencode": {
        "structured_output": True,
        "native_tool_calling": False,
        "streaming": False,
        "vision": False,
        "reasoning": False,
    },
}

_CAPABILITY_OPTION_KEYS = {
    "structured_output": "capability_structured_output",
    "native_tool_calling": "capability_native_tool_calling",
    "streaming": "capability_streaming",
    "vision": "capability_vision",
    "reasoning": "capability_reasoning",
}

_OUTPUT_CONTRACT_VALUES = {item.value for item in OutputContract}
_OUTPUT_ENFORCEMENT_VALUES = {item.value for item in OutputEnforcement}


def _positive_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return int(value)
    return None


def _loopback(endpoint: Any) -> bool | None:
    if not isinstance(endpoint, str) or not endpoint.strip():
        return None
    try:
        host = (urlparse(endpoint).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    return host in {"localhost", "127.0.0.1", "::1"}


def _output_profile(
    provider: str,
    adapter: str | None,
    options: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    if adapter == "opencode":
        contract = OutputContract.JSON.value
        enforcement = OutputEnforcement.POSTHOC_VALIDATED.value
        source = "opencode_cli_text_adapter_contract"
    elif provider in {"ollama", "lm-studio"}:
        contract = OutputContract.JSON_SCHEMA.value
        enforcement = OutputEnforcement.PROVIDER_NATIVE.value
        source = "provider_native_schema_contract"
    elif provider in {"openai", "openai-compatible"}:
        response_format = options.get("response_format")
        if isinstance(response_format, dict) and response_format.get("type") == "json_schema":
            contract = OutputContract.JSON_SCHEMA.value
            enforcement = OutputEnforcement.PROVIDER_NATIVE.value
            source = "configured_response_format"
        elif (
            isinstance(response_format, dict)
            and response_format.get("type") == "json_object"
        ) or options.get("json_mode") is True:
            contract = OutputContract.JSON.value
            enforcement = OutputEnforcement.PROVIDER_NATIVE.value
            source = "configured_json_mode"
        else:
            contract = OutputContract.TEXT.value
            enforcement = OutputEnforcement.PROMPT_ONLY.value
            source = "unconstrained_text_route"
    else:
        contract = OutputContract.TEXT.value
        enforcement = OutputEnforcement.PROMPT_ONLY.value
        source = "generic_text_route"

    explicit_contract = options.get("output_contract")
    explicit_enforcement = options.get("output_enforcement")
    overridden = False
    if isinstance(explicit_contract, str) and explicit_contract in _OUTPUT_CONTRACT_VALUES:
        contract = explicit_contract
        overridden = True
    if isinstance(explicit_enforcement, str) and explicit_enforcement in _OUTPUT_ENFORCEMENT_VALUES:
        enforcement = explicit_enforcement
        overridden = True
    if overridden:
        source += "+config_override"

    return {
        "contract": contract,
        "enforcement": enforcement,
        "canonical_protocol": "harness-json-decision",
        "bounded_lexical_repair": ["raw_control_character"],
        "semantic_repair": "forbidden",
    }, source


def _feature_profile(
    provider: str,
    adapter: str | None,
    options: dict[str, Any],
    output: dict[str, Any],
) -> tuple[dict[str, bool], str]:
    key = adapter or provider
    defaults = _ADAPTER_FEATURES.get(key) or _FEATURE_DEFAULTS.get(provider) or {
        "structured_output": False,
        "native_tool_calling": False,
        "streaming": False,
        "vision": False,
        "reasoning": False,
    }
    features = dict(defaults)
    # A configured output contract stronger than text means the current route
    # consumes structured output even if the generic provider default does not.
    if output["contract"] in {OutputContract.JSON.value, OutputContract.JSON_SCHEMA.value, OutputContract.TOOL_CALL.value}:
        features["structured_output"] = True
    source = "adapter_contract" if adapter in _ADAPTER_FEATURES else (
        "provider_contract" if provider in _FEATURE_DEFAULTS else "unknown_provider_default"
    )
    overridden = False
    for feature, option_key in _CAPABILITY_OPTION_KEYS.items():
        value = options.get(option_key)
        if isinstance(value, bool):
            features[feature] = value
            overridden = True
    if overridden:
        source += "+config_override"
    return features, source


@dataclass(frozen=True)
class ModelRouteProfile:
    alias: str
    provider: str
    adapter: str | None
    model: str | None
    endpoint: str | None
    execution_location: str
    wrapper_layers: tuple[str, ...]
    features: dict[str, bool]
    input_contract: dict[str, Any]
    output_contract: dict[str, Any]
    constraints: dict[str, Any]
    feature_source: str
    output_source: str

    def dump(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "provider": self.provider,
            "adapter": self.adapter,
            "model": self.model,
            "endpoint": self.endpoint,
            "execution_location": self.execution_location,
            "wrapper_layers": list(self.wrapper_layers),
            "features": dict(self.features),
            "input": dict(self.input_contract),
            "output": dict(self.output_contract),
            "constraints": dict(self.constraints),
            "feature_source": self.feature_source,
            "output_source": self.output_source,
            "model_tier": None,
            "model_size_class": None,
        }


def _profile_from_route(alias: str, route: dict[str, Any]) -> ModelRouteProfile:
    provider = str(route.get("provider", "")).strip().lower()
    options = route.get("options")
    options = dict(options) if isinstance(options, dict) else {}
    adapter_raw = options.get("adapter")
    adapter = str(adapter_raw).strip().lower() if isinstance(adapter_raw, str) and adapter_raw.strip() else None
    output, output_source = _output_profile(provider, adapter, options)
    features, feature_source = _feature_profile(provider, adapter, options, output)

    endpoint = route.get("endpoint") if isinstance(route.get("endpoint"), str) else None
    local = _loopback(endpoint)
    if adapter == "opencode" or provider == "command":
        execution_location = "local_process"
    elif local is True:
        execution_location = "local_endpoint"
    elif local is False:
        execution_location = "remote_endpoint"
    elif provider in {"ollama", "lm-studio"}:
        execution_location = "local_endpoint"
    else:
        execution_location = "unspecified"

    context_window = _positive_int(options.get("context_window"))
    output_reserve = (
        _positive_int(options.get("reserved_output_tokens"))
        or _positive_int(options.get("num_predict"))
        or _positive_int(options.get("max_tokens"))
    )
    safety_margin = _positive_int(options.get("context_safety_margin_tokens"))
    effective_input_budget = None
    if context_window is not None and output_reserve is not None and safety_margin is not None:
        candidate = context_window - output_reserve - safety_margin
        effective_input_budget = candidate if candidate > 0 else None

    input_contract = {
        "context_window": context_window,
        "reserved_output_tokens": output_reserve,
        "context_safety_margin_tokens": safety_margin,
        "effective_input_budget": effective_input_budget,
        "context_compiler": "token-aware-working-context",
    }
    constraints = {
        **input_contract,
        "timeout_seconds": route.get("timeout_seconds"),
        "decision_protocol": "harness-json-decision",
        "tool_execution_boundary": "harness_only",
    }
    wrappers = ("opencode",) if adapter == "opencode" else ()
    return ModelRouteProfile(
        alias=alias,
        provider=provider,
        adapter=adapter,
        model=(str(route.get("model")) if route.get("model") is not None else None),
        endpoint=endpoint,
        execution_location=execution_location,
        wrapper_layers=wrappers,
        features=features,
        input_contract=input_contract,
        output_contract=output,
        constraints=constraints,
        feature_source=feature_source,
        output_source=output_source,
    )


def inspect_model_capabilities(model_gateway: Any) -> dict[str, Any]:
    """Describe route contracts/observations without assigning intelligence tiers."""
    descriptor_fn = getattr(model_gateway, "descriptor", None)
    if not callable(descriptor_fn):
        raise ValueError("model gateway does not expose descriptor()")
    descriptor = descriptor_fn()
    if not isinstance(descriptor, dict):
        raise ValueError("model gateway descriptor must be an object")
    routes = descriptor.get("models")
    if not isinstance(routes, dict):
        raise ValueError("model gateway descriptor has no models map")

    profiles = {
        str(alias): _profile_from_route(str(alias), route).dump()
        for alias, route in sorted(routes.items())
        if isinstance(route, dict)
    }

    observed: dict[str, Any] = {
        "scope": "gateway_session_aggregate",
        "requests": 0,
        "failures": 0,
        "protocol_repairs": 0,
        "failure_rate": None,
        "protocol_repair_rate": None,
    }
    telemetry_fn = getattr(model_gateway, "telemetry_snapshot", None)
    if callable(telemetry_fn):
        raw = telemetry_fn()
        if isinstance(raw, dict):
            requests = int(raw.get("requests", 0) or 0)
            failures = int(raw.get("failures", 0) or 0)
            repairs = int(raw.get("protocol_repairs", 0) or 0)
            observed.update({
                "requests": requests,
                "failures": failures,
                "protocol_repairs": repairs,
                "failure_rate": round(failures / requests, 4) if requests else None,
                "protocol_repair_rate": round(repairs / requests, 4) if requests else None,
                "last_provider": raw.get("last_provider"),
                "last_model": raw.get("last_model"),
                "last_error_kind": raw.get("last_error_kind"),
            })

    return {
        "schema_version": "model-capability-snapshot-v1",
        "policy": {
            "model_tiering": "disabled",
            "intelligence_classification": "none",
            "adaptation_basis": "route_input_output_contracts_plus_observed_failures",
        },
        "default_model": descriptor.get("default_model"),
        "routes": profiles,
        "observed": observed,
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect configured model route contracts without assigning model tiers.")
    parser.add_argument("config", help="Harness TOML config path")
    args = parser.parse_args(argv)

    from harness.config import load_harness_config
    from harness.model_gateway import ModelGateway

    config = load_harness_config(args.config)
    if not config.default_model:
        parser.error("config has no default_model")
    gateway = ModelGateway(models=config.models, default_model=config.default_model)
    print(json.dumps(inspect_model_capabilities(gateway), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
