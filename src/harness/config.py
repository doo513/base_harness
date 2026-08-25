from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
import os
import tomllib


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SecretRef:
    provider: str
    key: str

    @classmethod
    def parse(cls, value: str) -> "SecretRef":
        if not isinstance(value, str) or ":" not in value:
            raise ConfigError("secret reference must use '<provider>:<key>' syntax")
        provider, key = value.split(":", 1)
        provider = provider.strip().lower()
        key = key.strip()
        if provider != "env":
            raise ConfigError(f"unsupported secret provider: {provider!r}")
        if not key:
            raise ConfigError("secret reference key must not be empty")
        return cls(provider=provider, key=key)

    def descriptor(self) -> str:
        return f"{self.provider}:{self.key}"


class SecretResolver:
    """Resolve explicit secret references without persisting secret values."""

    def __init__(self, environment: Mapping[str, str] | None = None):
        self.environment = os.environ if environment is None else environment

    def resolve(self, reference: SecretRef | str | None) -> str | None:
        if reference is None:
            return None
        ref = reference if isinstance(reference, SecretRef) else SecretRef.parse(reference)
        if ref.provider == "env":
            value = self.environment.get(ref.key)
            if value is None or value == "":
                raise ConfigError(f"required environment secret is missing: {ref.key}")
            return value
        raise ConfigError(f"unsupported secret provider: {ref.provider!r}")


@dataclass(frozen=True)
class WorkspaceConfig:
    root: str = "."
    temp_dir: str | None = None
    build_dir: str | None = None
    cache_dir: str | None = None


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str | None = None
    endpoint: str | None = None
    api_key: SecretRef | None = None
    command: str | None = None
    timeout_seconds: float = 120.0
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()
        if not provider:
            raise ConfigError("model provider must not be empty")
        object.__setattr__(self, "provider", provider)
        if self.timeout_seconds <= 0:
            raise ConfigError("model timeout_seconds must be positive")
        if provider == "command" and not self.command:
            raise ConfigError("command model provider requires command")
        if provider != "command" and not self.model:
            raise ConfigError("non-command model provider requires model")


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: str
    enabled: bool = True
    command: tuple[str, ...] = ()
    url: str | None = None
    env: dict[str, SecretRef] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ConfigError("MCP server name must not be empty")
        transport = self.transport.strip().lower()
        if transport not in {"stdio", "http"}:
            raise ConfigError("MCP transport must be 'stdio' or 'http'")
        object.__setattr__(self, "transport", transport)
        if transport == "stdio" and not self.command:
            raise ConfigError("stdio MCP server requires command argv")
        if transport == "http" and not self.url:
            raise ConfigError("http MCP server requires url")


@dataclass(frozen=True)
class PluginConfig:
    name: str
    module: str
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.module.strip():
            raise ConfigError("plugin name and module must not be empty")


@dataclass(frozen=True)
class MemoryConfig:
    enabled: bool = False
    root: str | None = None
    project_id: str | None = None
    reproduced_min_families: int = 2
    robust_min_families: int = 3
    robust_min_environments: int = 2
    soft_contradictions_per_demotion: int = 2
    stale_after_days: int = 180

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigError("memory.enabled must be boolean")
        if self.enabled and (not isinstance(self.root, str) or not self.root.strip()):
            raise ConfigError("enabled project memory requires memory.root")
        if self.project_id is not None and (not isinstance(self.project_id, str) or not self.project_id.strip()):
            raise ConfigError("memory.project_id must be a non-empty string when provided")
        integer_fields = (
            "reproduced_min_families",
            "robust_min_families",
            "robust_min_environments",
            "soft_contradictions_per_demotion",
            "stale_after_days",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ConfigError(f"memory.{name} must be a positive integer")
        if self.robust_min_families < self.reproduced_min_families:
            raise ConfigError("memory.robust_min_families cannot be lower than reproduced_min_families")


@dataclass(frozen=True)
class HarnessConfig:
    profile: str = "demo"
    run_dir: str = "./run"
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    default_model: str | None = None
    models: dict[str, ModelConfig] = field(default_factory=dict)
    mcp_servers: tuple[MCPServerConfig, ...] = ()
    plugins: tuple[PluginConfig, ...] = ()
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    security: dict[str, Any] = field(default_factory=dict)
    acceptance_commands: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(not isinstance(item, str) or not item for item in self.acceptance_commands):
            raise ConfigError("acceptance_commands must contain non-empty strings")
        if self.default_model is not None and self.default_model not in self.models:
            raise ConfigError(f"default_model is not declared: {self.default_model}")
        names = [item.name for item in self.mcp_servers]
        if len(names) != len(set(names)):
            raise ConfigError("MCP server names must be unique")
        plugin_names = [item.name for item in self.plugins]
        if len(plugin_names) != len(set(plugin_names)):
            raise ConfigError("plugin names must be unique")

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "harness-config-v1",
            "profile": self.profile,
            "run_dir": self.run_dir,
            "acceptance_commands": list(self.acceptance_commands),
            "workspace": {
                "root": self.workspace.root,
                "temp_dir": self.workspace.temp_dir,
                "build_dir": self.workspace.build_dir,
                "cache_dir": self.workspace.cache_dir,
            },
            "default_model": self.default_model,
            "models": {
                name: {
                    "provider": cfg.provider,
                    "model": cfg.model,
                    "endpoint": cfg.endpoint,
                    "api_key": cfg.api_key.descriptor() if cfg.api_key else None,
                    "command": cfg.command,
                    "timeout_seconds": cfg.timeout_seconds,
                    "options": dict(cfg.options),
                }
                for name, cfg in sorted(self.models.items())
            },
            "mcp_servers": [
                {
                    "name": item.name,
                    "transport": item.transport,
                    "enabled": item.enabled,
                    "command": list(item.command),
                    "url": item.url,
                    "env": {key: ref.descriptor() for key, ref in sorted(item.env.items())},
                    "options": dict(item.options),
                }
                for item in self.mcp_servers
            ],
            "plugins": [
                {
                    "name": item.name,
                    "module": item.module,
                    "enabled": item.enabled,
                    "options": dict(item.options),
                }
                for item in self.plugins
            ],
            "memory": {
                "enabled": self.memory.enabled,
                "root": self.memory.root,
                "project_id": self.memory.project_id,
                "reproduced_min_families": self.memory.reproduced_min_families,
                "robust_min_families": self.memory.robust_min_families,
                "robust_min_environments": self.memory.robust_min_environments,
                "soft_contradictions_per_demotion": self.memory.soft_contradictions_per_demotion,
                "stale_after_days": self.memory.stale_after_days,
            },
            "security": dict(self.security),
        }


def _expect_mapping(value: Any, path: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{path} must be a table/object")
    return dict(value)


def _expect_list(value: Any, path: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"{path} must be an array")
    return list(value)


def _expect_bool(value: Any, path: str, *, default: bool = True) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"{path} must be a boolean")
    return value


def _parse_secret(value: Any, path: str) -> SecretRef | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{path} must be a secret reference string")
    return SecretRef.parse(value)


def harness_config_from_mapping(raw: Mapping[str, Any]) -> HarnessConfig:
    data = dict(raw)
    allowed = {
        "profile", "run_dir", "acceptance_commands", "workspace", "default_model", "models",
        "mcp", "plugins", "memory", "security",
    }
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError("unknown top-level config keys: " + ", ".join(unknown))

    workspace_raw = _expect_mapping(data.get("workspace"), "workspace")
    workspace_unknown = sorted(set(workspace_raw) - {"root", "temp_dir", "build_dir", "cache_dir"})
    if workspace_unknown:
        raise ConfigError("unknown workspace config keys: " + ", ".join(workspace_unknown))
    workspace = WorkspaceConfig(
        root=str(workspace_raw.get("root", ".")),
        temp_dir=workspace_raw.get("temp_dir"),
        build_dir=workspace_raw.get("build_dir"),
        cache_dir=workspace_raw.get("cache_dir"),
    )

    models_raw = _expect_mapping(data.get("models"), "models")
    models: dict[str, ModelConfig] = {}
    for name, value in sorted(models_raw.items()):
        item = _expect_mapping(value, f"models.{name}")
        known = {"provider", "model", "endpoint", "api_key", "command", "timeout_seconds", "options"}
        extra = sorted(set(item) - known)
        if extra:
            raise ConfigError(f"unknown models.{name} keys: " + ", ".join(extra))
        provider = item.get("provider")
        if not isinstance(provider, str):
            raise ConfigError(f"models.{name}.provider must be a string")
        try:
            timeout_seconds = float(item.get("timeout_seconds", 120.0))
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"models.{name}.timeout_seconds must be numeric") from exc
        models[str(name)] = ModelConfig(
            provider=provider,
            model=item.get("model"),
            endpoint=item.get("endpoint"),
            api_key=_parse_secret(item.get("api_key"), f"models.{name}.api_key"),
            command=item.get("command"),
            timeout_seconds=timeout_seconds,
            options=_expect_mapping(item.get("options"), f"models.{name}.options"),
        )

    mcp_items: list[MCPServerConfig] = []
    for index, value in enumerate(_expect_list(data.get("mcp"), "mcp")):
        item = _expect_mapping(value, f"mcp[{index}]")
        known = {"name", "transport", "enabled", "command", "url", "env", "options"}
        extra = sorted(set(item) - known)
        if extra:
            raise ConfigError(f"unknown mcp[{index}] keys: " + ", ".join(extra))
        env_raw = _expect_mapping(item.get("env"), f"mcp[{index}].env")
        env = {
            str(key): _parse_secret(secret, f"mcp[{index}].env.{key}")
            for key, secret in env_raw.items()
        }
        if any(ref is None for ref in env.values()):
            raise ConfigError(f"mcp[{index}].env values must be secret references")
        command_raw = item.get("command", [])
        if not isinstance(command_raw, list) or any(not isinstance(arg, str) or not arg for arg in command_raw):
            raise ConfigError(f"mcp[{index}].command must be a list of non-empty strings")
        url = item.get("url")
        if url is not None and not isinstance(url, str):
            raise ConfigError(f"mcp[{index}].url must be a string")
        mcp_items.append(MCPServerConfig(
            name=str(item.get("name", "")),
            transport=str(item.get("transport", "")),
            enabled=_expect_bool(item.get("enabled"), f"mcp[{index}].enabled"),
            command=tuple(command_raw),
            url=url,
            env={key: ref for key, ref in env.items() if ref is not None},
            options=_expect_mapping(item.get("options"), f"mcp[{index}].options"),
        ))

    plugin_items: list[PluginConfig] = []
    for index, value in enumerate(_expect_list(data.get("plugins"), "plugins")):
        item = _expect_mapping(value, f"plugins[{index}]")
        known = {"name", "module", "enabled", "options"}
        extra = sorted(set(item) - known)
        if extra:
            raise ConfigError(f"unknown plugins[{index}] keys: " + ", ".join(extra))
        plugin_items.append(PluginConfig(
            name=str(item.get("name", "")),
            module=str(item.get("module", "")),
            enabled=_expect_bool(item.get("enabled"), f"plugins[{index}].enabled"),
            options=_expect_mapping(item.get("options"), f"plugins[{index}].options"),
        ))

    memory_raw = _expect_mapping(data.get("memory"), "memory")
    memory_fields = {
        "enabled", "root", "project_id", "reproduced_min_families",
        "robust_min_families", "robust_min_environments",
        "soft_contradictions_per_demotion", "stale_after_days",
    }
    memory_unknown = sorted(set(memory_raw) - memory_fields)
    if memory_unknown:
        raise ConfigError("unknown memory config keys: " + ", ".join(memory_unknown))
    memory_root = memory_raw.get("root")
    project_id = memory_raw.get("project_id")
    if memory_root is not None and not isinstance(memory_root, str):
        raise ConfigError("memory.root must be a string")
    if project_id is not None and not isinstance(project_id, str):
        raise ConfigError("memory.project_id must be a string")

    def memory_integer(name: str, default: int) -> int:
        value = memory_raw.get(name, default)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ConfigError(f"memory.{name} must be an integer")
        return value

    memory = MemoryConfig(
        enabled=_expect_bool(memory_raw.get("enabled"), "memory.enabled", default=False),
        root=memory_root,
        project_id=project_id,
        reproduced_min_families=memory_integer("reproduced_min_families", 2),
        robust_min_families=memory_integer("robust_min_families", 3),
        robust_min_environments=memory_integer("robust_min_environments", 2),
        soft_contradictions_per_demotion=memory_integer("soft_contradictions_per_demotion", 2),
        stale_after_days=memory_integer("stale_after_days", 180),
    )

    profile = data.get("profile", "demo")
    run_dir = data.get("run_dir", "./run")
    default_model = data.get("default_model")
    acceptance_raw = _expect_list(data.get("acceptance_commands"), "acceptance_commands")
    if any(not isinstance(item, str) or not item for item in acceptance_raw):
        raise ConfigError("acceptance_commands must be an array of non-empty strings")
    if not isinstance(profile, str) or not profile:
        raise ConfigError("profile must be a non-empty string")
    if not isinstance(run_dir, str) or not run_dir:
        raise ConfigError("run_dir must be a non-empty string")
    if default_model is not None and not isinstance(default_model, str):
        raise ConfigError("default_model must be a string")

    return HarnessConfig(
        profile=profile,
        run_dir=run_dir,
        workspace=workspace,
        default_model=default_model,
        models=models,
        mcp_servers=tuple(mcp_items),
        plugins=tuple(plugin_items),
        memory=memory,
        security=_expect_mapping(data.get("security"), "security"),
        acceptance_commands=tuple(acceptance_raw),
    )


def load_harness_config(path: str | Path) -> HarnessConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists() or not config_path.is_file():
        raise ConfigError(f"config file does not exist: {config_path}")
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return harness_config_from_mapping(raw)
