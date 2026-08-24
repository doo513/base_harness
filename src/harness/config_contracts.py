from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlparse

from harness.config import ConfigError, MCPServerConfig, ModelConfig, PluginConfig
from harness.model_protocol import OutputContract, OutputEnforcement


_COMMON_MODEL_OPTIONS = {
    "context_window",
    "reserved_output_tokens",
    "context_safety_margin_tokens",
    "context_safety_margin_source",
    "fallback_models",
    "output_contract",
    "output_enforcement",
    "capability_structured_output",
    "capability_native_tool_calling",
    "capability_streaming",
    "capability_vision",
    "capability_reasoning",
}

_PROVIDER_OPTIONS = {
    "command": {
        "command_env_allowlist",
        "command_inherit_env",
        "adapter",
        "catalog_provider",
        "catalog_model_id",
        "catalog_name",
        "catalog_input_limit",
        "catalog_output_limit",
        "catalog_explicitly_free",
        "catalog_cost_input",
        "catalog_cost_output",
        "opencode_binary",
        "opencode_agent",
    },
    "openai": {
        "temperature", "max_tokens", "top_p", "reasoning_effort",
        "response_format", "json_mode", "ollama_compat", "seed",
    },
    "openai-compatible": {
        "temperature", "max_tokens", "top_p", "reasoning_effort",
        "response_format", "json_mode", "ollama_compat", "seed",
    },
    "ollama": {"temperature", "top_p", "num_predict", "max_tokens", "think", "seed"},
    "lm-studio": {"temperature", "max_tokens", "top_p", "seed"},
}

_MCP_STDIO_OPTIONS = {
    "request_timeout_seconds",
    "probe_timeout_seconds",
    "tool_policies",
}


def _positive_number(value: Any, path: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) <= 0:
        raise ConfigError(f"{path} must be a positive number")


def _validate_url(value: str | None, path: str) -> None:
    if value is None:
        return
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise ConfigError(f"{path} is not a valid URL: {exc}") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError(f"{path} must use http/https and include a host")


def validate_model_config_contract(config: ModelConfig) -> None:
    """Reject unsupported built-in route fields before the first model call."""
    provider = config.provider
    allowed = _PROVIDER_OPTIONS.get(provider)
    if allowed is not None:
        unknown = sorted(set(config.options) - _COMMON_MODEL_OPTIONS - allowed)
        if unknown:
            raise ConfigError(
                f"unsupported options for model provider {provider!r}: " + ", ".join(unknown)
            )

    fallback = config.options.get("fallback_models")
    if fallback is not None:
        if not isinstance(fallback, list) or any(not isinstance(item, str) or not item for item in fallback):
            raise ConfigError("options.fallback_models must be a list of non-empty model aliases")

    for key in ("context_window", "reserved_output_tokens", "context_safety_margin_tokens"):
        value = config.options.get(key)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
            raise ConfigError(f"options.{key} must be a positive integer")

    seed = config.options.get("seed")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise ConfigError("options.seed must be an integer when provided")

    output_contract = config.options.get("output_contract")
    if output_contract is not None and output_contract not in {item.value for item in OutputContract}:
        raise ConfigError(f"options.output_contract is invalid: {output_contract!r}")
    output_enforcement = config.options.get("output_enforcement")
    if output_enforcement is not None and output_enforcement not in {item.value for item in OutputEnforcement}:
        raise ConfigError(f"options.output_enforcement is invalid: {output_enforcement!r}")

    if provider == "command":
        allowlist = config.options.get("command_env_allowlist", [])
        if not isinstance(allowlist, list) or any(not isinstance(item, str) or not item for item in allowlist):
            raise ConfigError("options.command_env_allowlist must be a list of non-empty strings")
        inherit = config.options.get("command_inherit_env", False)
        if not isinstance(inherit, bool):
            raise ConfigError("options.command_inherit_env must be boolean")
        adapter = config.options.get("adapter")
        if adapter is not None and adapter != "opencode":
            raise ConfigError(f"unsupported command adapter: {adapter!r}")
    elif provider in {"openai", "openai-compatible"}:
        _validate_url(config.endpoint, "model endpoint")
        if config.endpoint is None:
            raise ConfigError(f"provider {provider!r} requires endpoint")
    elif provider in {"ollama", "lm-studio"}:
        _validate_url(config.endpoint, "model endpoint")


def validate_mcp_server_contract(config: MCPServerConfig) -> None:
    if config.transport != "stdio":
        raise ConfigError(
            f"MCP transport {config.transport!r} is not implemented by mcp-gateway-v2"
        )
    unknown = sorted(set(config.options) - _MCP_STDIO_OPTIONS)
    if unknown:
        raise ConfigError(
            f"unsupported MCP options for {config.name!r}: " + ", ".join(unknown)
        )
    for key, default in (("request_timeout_seconds", 15.0), ("probe_timeout_seconds", 2.0)):
        _positive_number(config.options.get(key, default), f"MCP {config.name} options.{key}")

    policies = config.options.get("tool_policies", {})
    if not isinstance(policies, Mapping):
        raise ConfigError(f"MCP {config.name} options.tool_policies must be an object")
    for tool, raw in policies.items():
        if not isinstance(tool, str) or not tool:
            raise ConfigError(f"MCP {config.name} tool policy name must be non-empty")
        if not isinstance(raw, Mapping):
            raise ConfigError(f"MCP {config.name}.{tool} policy must be an object")
        unknown_policy = sorted(set(raw) - {"side_effect", "permission", "idempotent"})
        if unknown_policy:
            raise ConfigError(
                f"unsupported MCP tool policy keys for {config.name}.{tool}: "
                + ", ".join(unknown_policy)
            )
        permission = raw.get("permission", "confirm")
        if permission not in {"auto", "confirm", "deny"}:
            raise ConfigError(f"invalid MCP permission for {config.name}.{tool}: {permission!r}")
        if "idempotent" in raw and not isinstance(raw["idempotent"], bool):
            raise ConfigError(f"MCP {config.name}.{tool}.idempotent must be boolean")


def validate_plugin_config_contract(config: PluginConfig) -> None:
    if not isinstance(config.options, dict):
        raise ConfigError(f"plugin {config.name} options must be an object")
