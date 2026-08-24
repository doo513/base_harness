from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Mapping
import copy
import re

from harness.config import PluginConfig
from harness.config_contracts import validate_plugin_config_contract
from harness.core.tools import (
    SandboxedArgvToolSpec,
    SandboxedCommandToolSpec,
    SandboxedSessionToolSpec,
    ToolSpec,
)


PLUGIN_API_VERSION = "harness-plugin-v1"
_PLUGIN_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_OPTION_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
ToolLike = ToolSpec | SandboxedCommandToolSpec | SandboxedArgvToolSpec | SandboxedSessionToolSpec


class PluginError(RuntimeError):
    pass


@dataclass(frozen=True)
class PluginStaticContract:
    """Option contract read after import but before option-consuming factory call."""

    api_version: str = PLUGIN_API_VERSION
    allowed_options: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.api_version != PLUGIN_API_VERSION:
            raise PluginError(
                f"unsupported plugin static contract API: {self.api_version!r}; expected {PLUGIN_API_VERSION!r}"
            )
        if len(self.allowed_options) != len(set(self.allowed_options)):
            raise PluginError("plugin allowed_options must be unique")
        for key in self.allowed_options:
            if not isinstance(key, str) or not _OPTION_NAME_RE.fullmatch(key):
                raise PluginError(f"invalid plugin option name in static contract: {key!r}")


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    api_version: str = PLUGIN_API_VERSION
    tools: Mapping[str, ToolLike] | None = None

    def validate(self) -> None:
        if not _PLUGIN_NAME_RE.fullmatch(self.name):
            raise PluginError(f"invalid plugin name: {self.name!r}")
        if not isinstance(self.version, str) or not self.version.strip():
            raise PluginError("plugin version must be a non-empty string")
        if self.api_version != PLUGIN_API_VERSION:
            raise PluginError(
                f"unsupported plugin API version: {self.api_version!r}; expected {PLUGIN_API_VERSION!r}"
            )
        if self.tools is not None:
            if not isinstance(self.tools, Mapping):
                raise PluginError("plugin tools must be a mapping")
            for name, spec in self.tools.items():
                if not isinstance(name, str) or not _PLUGIN_NAME_RE.fullmatch(name):
                    raise PluginError(f"invalid plugin tool name: {name!r}")
                if not isinstance(spec, (ToolSpec, SandboxedCommandToolSpec, SandboxedArgvToolSpec, SandboxedSessionToolSpec)):
                    raise PluginError(f"plugin tool {name!r} has unsupported spec type")


@dataclass(frozen=True)
class LoadedPlugin:
    config: PluginConfig
    manifest: PluginManifest
    static_contract: PluginStaticContract


class PluginGateway:
    """Explicit loader for already-installed trusted Python extensions.

    Importing a Python module executes code in the host process. This gateway
    reduces configuration ambiguity but does NOT sandbox module import. Strict
    host isolation therefore rejects Python plugins at the CLI/runtime boundary.
    """

    def __init__(self, configs: tuple[PluginConfig, ...]):
        self.configs = tuple(config for config in configs if config.enabled)
        for config in self.configs:
            validate_plugin_config_contract(config)
        self.loaded: dict[str, LoadedPlugin] = {}
        self._tools: dict[str, ToolLike] | None = None

    @staticmethod
    def _manifest_from_raw(raw: Any) -> PluginManifest:
        if isinstance(raw, PluginManifest):
            raw.validate()
            return raw
        if not isinstance(raw, dict):
            raise PluginError("harness_plugin() must return PluginManifest or an object mapping")
        manifest = PluginManifest(
            name=str(raw.get("name", "")),
            version=str(raw.get("version", "")),
            api_version=str(raw.get("api_version", PLUGIN_API_VERSION)),
            tools=raw.get("tools"),
        )
        manifest.validate()
        return manifest

    @staticmethod
    def _static_contract_from_module(module: Any, config: PluginConfig) -> PluginStaticContract:
        provider = getattr(module, "harness_plugin_contract", None)
        if provider is None:
            if config.options:
                raise PluginError(
                    f"plugin {config.name!r} uses options but module {config.module!r} does not expose "
                    "harness_plugin_contract() for pre-factory validation"
                )
            return PluginStaticContract()
        if not callable(provider):
            raise PluginError("harness_plugin_contract must be callable when present")
        try:
            raw = provider()
        except Exception as exc:
            raise PluginError(
                f"plugin {config.name!r} static contract failed: {type(exc).__name__}: {exc}"
            ) from exc
        if isinstance(raw, PluginStaticContract):
            contract = raw
        elif isinstance(raw, Mapping):
            allowed = raw.get("allowed_options", ())
            if not isinstance(allowed, (list, tuple)) or any(not isinstance(item, str) for item in allowed):
                raise PluginError("plugin static contract allowed_options must be a list/tuple of strings")
            contract = PluginStaticContract(
                api_version=str(raw.get("api_version", PLUGIN_API_VERSION)),
                allowed_options=tuple(allowed),
            )
        else:
            raise PluginError("harness_plugin_contract() must return PluginStaticContract or an object mapping")
        contract.validate()
        unknown = sorted(set(config.options) - set(contract.allowed_options))
        if unknown:
            raise PluginError(
                f"unsupported plugin options for {config.name!r}: " + ", ".join(unknown)
            )
        return contract

    def _load_one(self, config: PluginConfig) -> LoadedPlugin:
        existing = self.loaded.get(config.name)
        if existing is not None:
            return existing
        try:
            module = import_module(config.module)
        except Exception as exc:
            raise PluginError(f"failed to import plugin {config.name!r}: {type(exc).__name__}: {exc}") from exc

        static_contract = self._static_contract_from_module(module, config)
        factory = getattr(module, "harness_plugin", None)
        if not callable(factory):
            raise PluginError(f"plugin module {config.module!r} must expose harness_plugin(options=...)")
        try:
            raw = factory(options=dict(config.options))
        except Exception as exc:
            raise PluginError(f"plugin {config.name!r} factory failed: {type(exc).__name__}: {exc}") from exc
        manifest = self._manifest_from_raw(raw)
        if manifest.name != config.name:
            raise PluginError(
                f"plugin config/manifest name mismatch: config={config.name!r}, manifest={manifest.name!r}"
            )
        loaded = LoadedPlugin(config=config, manifest=manifest, static_contract=static_contract)
        self.loaded[config.name] = loaded
        return loaded

    def discover_tools(self) -> dict[str, ToolLike]:
        if self._tools is not None:
            return dict(self._tools)
        result: dict[str, ToolLike] = {}
        for config in self.configs:
            loaded = self._load_one(config)
            for local_name, original in sorted((loaded.manifest.tools or {}).items()):
                public_name = f"plugin.{loaded.manifest.name}.{local_name}"
                if public_name in result:
                    raise PluginError(f"duplicate normalized plugin tool name: {public_name}")
                spec = copy.copy(original)
                spec.name = public_name
                provenance = dict(getattr(spec, "provenance", {}) or {})
                provenance.update({
                    "kind": "plugin",
                    "plugin": loaded.manifest.name,
                    "plugin_version": loaded.manifest.version,
                    "plugin_api_version": loaded.manifest.api_version,
                    "module": config.module,
                    "import_authority": "explicit_trusted_extension",
                    "host_process_import": True,
                    "static_option_contract": list(loaded.static_contract.allowed_options),
                })
                spec.provenance = provenance
                result[public_name] = spec
        self._tools = result
        return dict(result)

    def descriptor(self) -> dict[str, Any]:
        plugins: list[dict[str, Any]] = []
        for config in self.configs:
            loaded = self._load_one(config)
            plugins.append({
                "name": loaded.manifest.name,
                "version": loaded.manifest.version,
                "api_version": loaded.manifest.api_version,
                "module": config.module,
                "options": dict(config.options),
                "allowed_options": list(loaded.static_contract.allowed_options),
                "tools": sorted((loaded.manifest.tools or {}).keys()),
            })
        return {
            "schema_version": "plugin-gateway-v2",
            "plugins": plugins,
            "auto_install": False,
            "auto_discovery": False,
            "import_authority": "explicit_trusted_extension",
            "host_process_import": True,
            "host_isolation": "none-for-module-import",
            "strict_isolation_compatible": False,
        }
