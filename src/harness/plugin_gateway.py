from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Mapping
import copy
import re

from harness.config import PluginConfig
from harness.core.tools import (
    SandboxedArgvToolSpec,
    SandboxedCommandToolSpec,
    SandboxedSessionToolSpec,
    ToolSpec,
)


PLUGIN_API_VERSION = "harness-plugin-v1"
_PLUGIN_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
ToolLike = ToolSpec | SandboxedCommandToolSpec | SandboxedArgvToolSpec | SandboxedSessionToolSpec


class PluginError(RuntimeError):
    pass


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


class PluginGateway:
    """Explicit loader for already-installed trusted Python extensions.

    Importing a Python module executes code in the host process. For that
    reason plugins are never auto-installed or auto-discovered; only explicitly
    enabled config entries are imported. Runtime tool/capability/isolation gates
    still apply to contributed tools, but they cannot sandbox module import.
    """

    def __init__(self, configs: tuple[PluginConfig, ...]):
        self.configs = tuple(config for config in configs if config.enabled)
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

    def _load_one(self, config: PluginConfig) -> LoadedPlugin:
        existing = self.loaded.get(config.name)
        if existing is not None:
            return existing
        try:
            module = import_module(config.module)
        except Exception as exc:
            raise PluginError(f"failed to import plugin {config.name!r}: {type(exc).__name__}: {exc}") from exc
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
        loaded = LoadedPlugin(config=config, manifest=manifest)
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
                "tools": sorted((loaded.manifest.tools or {}).keys()),
            })
        return {
            "schema_version": "plugin-gateway-v1",
            "plugins": plugins,
            "auto_install": False,
            "auto_discovery": False,
            "import_authority": "explicit_trusted_extension",
        }
