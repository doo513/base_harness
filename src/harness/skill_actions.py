from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SkillActionError(ValueError):
    pass


_ALIAS = re.compile(r"^[A-Za-z0-9_-]+$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ProviderPreset:
    name: str
    provider: str
    endpoint: str | None
    default_secret_env: str | None
    description: str


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "gemini": ProviderPreset(
        name="gemini",
        provider="openai-compatible",
        endpoint="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_secret_env="GEMINI_API_KEY",
        description="Google Gemini through the OpenAI-compatible endpoint",
    ),
    "openai": ProviderPreset(
        name="openai",
        provider="openai",
        endpoint="https://api.openai.com/v1/",
        default_secret_env="OPENAI_API_KEY",
        description="OpenAI API",
    ),
    "openai-compatible": ProviderPreset(
        name="openai-compatible",
        provider="openai-compatible",
        endpoint=None,
        default_secret_env="LLM_API_KEY",
        description="Any OpenAI-compatible /chat/completions endpoint",
    ),
    "ollama": ProviderPreset(
        name="ollama",
        provider="openai-compatible",
        endpoint="http://127.0.0.1:11434/v1/",
        default_secret_env=None,
        description="Local Ollama OpenAI-compatible endpoint",
    ),
}


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _base_config_text() -> str:
    return (
        'profile = "software"\n'
        'run_dir = "./run"\n\n'
        '[workspace]\n'
        'root = "."\n\n'
        '[security]\n'
        'strict_layout = false\n'
        'strict_tool_isolation = false\n'
        'network_policy = "allow"\n'
        'require_sealed_oracle = false\n'
    )


def _load_text(path: Path) -> str:
    if not path.exists():
        return _base_config_text()
    if not path.is_file():
        raise SkillActionError(f"config path is not a file: {path}")
    return path.read_text(encoding="utf-8")


def _set_top_level(text: str, key: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    first_table = next(
        (index for index, line in enumerate(lines) if line.lstrip().startswith("[")),
        len(lines),
    )
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for index in range(first_table):
        if pattern.match(lines[index]):
            suffix = "\n" if lines[index].endswith("\n") else ""
            lines[index] = f"{key} = {value}{suffix}"
            return "".join(lines)
    insertion = f"{key} = {value}\n"
    lines.insert(first_table, insertion)
    if first_table < len(lines) - 1 and first_table > 0 and lines[first_table - 1].strip():
        lines.insert(first_table + 1, "\n")
    return "".join(lines)


def _validate_alias(alias: str, *, field: str = "alias") -> str:
    value = alias.strip()
    if not value or not _ALIAS.fullmatch(value):
        raise SkillActionError(f"{field} must use letters, numbers, '_' or '-'")
    return value


def _validate_env_name(value: str | None) -> str | None:
    if value is None:
        return None
    name = value.strip()
    if not name:
        return None
    if not _ENV_NAME.fullmatch(name):
        raise SkillActionError("secret environment variable name is invalid")
    return name


def _ensure_valid_toml(text: str) -> None:
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise SkillActionError(f"generated config is invalid TOML: {exc}") from exc


def configure_provider(
    config_path: str | Path,
    *,
    alias: str,
    preset: str,
    model: str,
    endpoint: str | None = None,
    secret_env: str | None = None,
    make_default: bool = True,
    timeout_seconds: float = 120.0,
) -> Path:
    """Append one model route while persisting only an env reference, never a raw key."""
    alias = _validate_alias(alias)
    model = model.strip()
    if not model:
        raise SkillActionError("model must not be empty")
    if timeout_seconds <= 0:
        raise SkillActionError("timeout_seconds must be positive")
    try:
        selected = PROVIDER_PRESETS[preset]
    except KeyError as exc:
        raise SkillActionError(f"unsupported provider preset: {preset}") from exc

    final_endpoint = (endpoint or selected.endpoint or "").strip()
    if not final_endpoint:
        raise SkillActionError("endpoint is required for this provider")
    final_secret_env = _validate_env_name(
        selected.default_secret_env if secret_env is None else secret_env
    )

    path = Path(config_path).expanduser()
    text = _load_text(path)
    parsed = tomllib.loads(text)
    models = parsed.get("models", {})
    if isinstance(models, dict) and alias in models:
        raise SkillActionError(f"model alias already exists: {alias}")

    block = [
        "",
        f"[models.{alias}]",
        f"provider = {_toml_string(selected.provider)}",
        f"model = {_toml_string(model)}",
        f"endpoint = {_toml_string(final_endpoint)}",
        f"timeout_seconds = {float(timeout_seconds):g}",
    ]
    if final_secret_env:
        block.append(f"api_key = {_toml_string('env:' + final_secret_env)}")
    block.append("")
    text = text.rstrip() + "\n" + "\n".join(block)
    if make_default:
        text = _set_top_level(text, "default_model", _toml_string(alias))
    _ensure_valid_toml(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _toml_array(values: Iterable[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def configure_mcp(
    config_path: str | Path,
    *,
    name: str,
    transport: str,
    command: Iterable[str] = (),
    url: str | None = None,
    env_refs: dict[str, str] | None = None,
    enabled: bool = True,
) -> Path:
    """Append an MCP connection using commands/URLs and env references only."""
    name = _validate_alias(name, field="MCP name")
    transport = transport.strip().lower()
    if transport not in {"stdio", "http"}:
        raise SkillActionError("MCP transport must be stdio or http")
    argv = tuple(item.strip() for item in command if item.strip())
    if transport == "stdio" and not argv:
        raise SkillActionError("stdio MCP requires command argv")
    final_url = (url or "").strip()
    if transport == "http" and not final_url:
        raise SkillActionError("http MCP requires a URL")

    refs = env_refs or {}
    normalized_refs: dict[str, str] = {}
    for target_name, source_env in refs.items():
        target = _validate_env_name(target_name)
        source = _validate_env_name(source_env)
        if target is None or source is None:
            raise SkillActionError("MCP env reference names must not be empty")
        normalized_refs[target] = source

    path = Path(config_path).expanduser()
    text = _load_text(path)
    parsed = tomllib.loads(text)
    for item in parsed.get("mcp", []) if isinstance(parsed.get("mcp", []), list) else []:
        if isinstance(item, dict) and item.get("name") == name:
            raise SkillActionError(f"MCP name already exists: {name}")

    block = [
        "",
        "[[mcp]]",
        f"name = {_toml_string(name)}",
        f"transport = {_toml_string(transport)}",
        f"enabled = {'true' if enabled else 'false'}",
    ]
    if transport == "stdio":
        block.append(f"command = {_toml_array(argv)}")
    else:
        block.append(f"url = {_toml_string(final_url)}")
    if normalized_refs:
        block.append("")
        block.append("[mcp.env]")
        for target, source in sorted(normalized_refs.items()):
            block.append(f"{target} = {_toml_string('env:' + source)}")
    block.append("")
    text = text.rstrip() + "\n" + "\n".join(block)
    _ensure_valid_toml(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@dataclass(frozen=True)
class MCPRegistryItem:
    name: str
    version: str | None
    description: str
    repository_url: str | None = None
    package_hints: tuple[str, ...] = ()


def _registry_item(raw: Any) -> MCPRegistryItem | None:
    if not isinstance(raw, dict):
        return None
    server = raw.get("server") if isinstance(raw.get("server"), dict) else raw
    if not isinstance(server, dict):
        return None
    name = server.get("name")
    if not isinstance(name, str) or not name:
        return None
    description = server.get("description") if isinstance(server.get("description"), str) else ""
    version = server.get("version") if isinstance(server.get("version"), str) else None
    repository = server.get("repository")
    repository_url = repository.get("url") if isinstance(repository, dict) and isinstance(repository.get("url"), str) else None
    hints: list[str] = []
    packages = server.get("packages")
    if isinstance(packages, list):
        for package in packages[:4]:
            if not isinstance(package, dict):
                continue
            registry_type = package.get("registryType")
            identifier = package.get("identifier")
            if isinstance(identifier, str):
                prefix = f"{registry_type}:" if isinstance(registry_type, str) else ""
                hints.append(prefix + identifier)
    remotes = server.get("remotes")
    if isinstance(remotes, list):
        for remote in remotes[:2]:
            if isinstance(remote, dict) and isinstance(remote.get("url"), str):
                hints.append("remote:" + remote["url"])
    return MCPRegistryItem(
        name=name,
        version=version,
        description=description,
        repository_url=repository_url,
        package_hints=tuple(hints),
    )


def search_mcp_registry(
    query: str,
    *,
    limit: int = 8,
    timeout_seconds: float = 10.0,
    opener: Callable[..., Any] = urlopen,
) -> tuple[MCPRegistryItem, ...]:
    """Search the official MCP Registry; discovery never installs or enables a server."""
    query = query.strip()
    if not query:
        raise SkillActionError("MCP search query must not be empty")
    if limit <= 0 or limit > 100:
        raise SkillActionError("MCP search limit must be between 1 and 100")
    params = urlencode({"search": query, "version": "latest", "limit": limit})
    request = Request(
        "https://registry.modelcontextprotocol.io/v0.1/servers?" + params,
        headers={"Accept": "application/json", "User-Agent": "verified-state-harness/skill-mcp-search"},
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise SkillActionError(f"MCP Registry search failed: {exc}") from exc
    servers = payload.get("servers") if isinstance(payload, dict) else None
    if not isinstance(servers, list):
        raise SkillActionError("MCP Registry response has no server list")
    items = [item for item in (_registry_item(raw) for raw in servers) if item is not None]
    return tuple(items[:limit])
