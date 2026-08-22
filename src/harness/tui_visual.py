from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shlex
import tomllib
from typing import Any
import urllib.request

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles import Style

from harness import __version__
from harness.skill_actions import (
    PROVIDER_PRESETS,
    SkillActionError,
    configure_mcp,
    configure_provider,
    search_mcp_registry,
)
from harness.skill_catalog import SkillCatalog, SkillError
from harness.task_intake import analyze_task_input
from harness.tui import RunLaunchSpec, _default_new_run_dir
from harness.tui_config import TUIConfigError, persist_tui_settings


COMMANDS = (
    "/help",
    "/status",
    "/connect",
    "/model",
    "/models",
    "/mcp",
    "/skills",
    "/domain",
    "/mode",
    "/accept",
    "/workspace",
    "/resume",
    "/inspect",
    "/permissions",
    "/new",
    "/clear",
    "/exit",
)

STYLE = Style.from_dict({
    "prompt": "ansicyan bold",
    "user": "ansicyan bold",
    "assistant": "ansiwhite",
    "muted": "ansibrightblack",
    "good": "ansigreen bold",
    "warn": "ansiyellow bold",
    "bad": "ansired bold",
    "accent": "ansimagenta bold",
    "tool": "ansiblue bold",
    "toolbar": "bg:#242424 #e0e0e0",
    "completion-menu.completion": "bg:#1e1e1e #c0c0c0",
    "completion-menu.completion.current": "bg:#383838 #ffffff bold",
    "completion-menu.meta.completion": "bg:#1e1e1e #888888",
    "completion-menu.meta.completion.current": "bg:#383838 #cccccc",
})


def _emit(*parts: tuple[str, str], end: str = "\n") -> None:
    print_formatted_text(FormattedText(list(parts)), style=STYLE, end=end)


def _discover_local_ollama_models(endpoint: str = "http://127.0.0.1:11434") -> list[str]:
    """Probe Ollama discovery only; discovery itself never creates runtime authority."""
    url = endpoint.rstrip("/") + "/api/tags"
    req = urllib.request.Request(url, headers={"User-Agent": f"base_harness/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    return [str(item["name"]) for item in data.get("models", []) if isinstance(item, dict) and item.get("name")]


def _config_data(path: str | Path) -> dict[str, Any]:
    candidate = Path(path).expanduser()
    if not candidate.exists():
        return {}
    try:
        with candidate.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_default_model(config_path: str | Path, alias: str) -> None:
    path = Path(config_path).expanduser()
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    replacement = f'default_model = {json.dumps(alias)}'
    pattern = re.compile(r"^\s*default_model\s*=.*$", re.MULTILINE)
    text = pattern.sub(replacement, text, count=1) if pattern.search(text) else replacement + "\n" + text
    tomllib.loads(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_local_alias(model: str, existing: dict[str, Any]) -> str:
    preferred = "ollama"
    if preferred not in existing:
        return preferred
    current = existing.get(preferred)
    if isinstance(current, dict) and str(current.get("model") or "") == model:
        return preferred
    suffix = re.sub(r"[^A-Za-z0-9_-]+", "-", model).strip("-").lower() or "model"
    candidate = f"ollama-{suffix}"
    index = 2
    while candidate in existing:
        current = existing.get(candidate)
        if isinstance(current, dict) and str(current.get("model") or "") == model:
            return candidate
        candidate = f"ollama-{suffix}-{index}"
        index += 1
    return candidate


def _ensure_local_ollama_route(config_path: str | Path, model: str) -> str:
    """Persist/reuse a real Ollama model route before the TUI reports it as usable."""
    data = _config_data(config_path)
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    for alias, item in models.items():
        if not isinstance(item, dict):
            continue
        endpoint = str(item.get("endpoint") or "")
        if str(item.get("model") or "") == model and ("127.0.0.1:11434" in endpoint or "localhost:11434" in endpoint):
            _write_default_model(config_path, str(alias))
            return str(alias)

    alias = _safe_local_alias(model, models)
    configure_provider(
        config_path,
        alias=alias,
        preset="ollama",
        model=model,
        make_default=True,
    )
    return alias


def _model_status(path: str | Path) -> tuple[str, str, bool]:
    """Report readiness only for a configured route; local discovery alone is not readiness."""
    data = _config_data(path)
    default = data.get("default_model")
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    if not isinstance(default, str) or default not in models:
        return "not connected", "-", False
    model_cfg = models.get(default)
    if not isinstance(model_cfg, dict):
        return default, "-", False
    model_id = str(model_cfg.get("model") or "-")
    secret = model_cfg.get("api_key")
    if isinstance(secret, str) and secret.startswith("env:"):
        return default, model_id, bool(os.environ.get(secret[4:]))
    return default, model_id, True


def _set_default_model(config_path: str | Path, alias: str, model_id: str | None = None) -> None:
    data = _config_data(config_path)
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    if alias in models:
        _write_default_model(config_path, alias)
        return

    target = model_id or alias
    if target in _discover_local_ollama_models():
        _ensure_local_ollama_route(config_path, target)
        return
    raise ValueError(f"unknown model alias: {alias}")


def _detect_acceptance(workspace: str | Path) -> tuple[str, ...]:
    root = Path(workspace).expanduser()
    py = "python" if os.name == "nt" else "python3"
    if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists() or (root / "tests").is_dir():
        return (f"{py} -m pytest -q",)
    if (root / "go.mod").exists():
        return ("go test ./...",)
    if (root / "Cargo.toml").exists():
        return ("cargo test",)
    if (root / "package.json").exists():
        return ("npm test",)
    return ()


def _secret_name_for_default(config_path: str | Path) -> str | None:
    data = _config_data(config_path)
    alias = data.get("default_model")
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    model = models.get(alias) if isinstance(alias, str) else None
    secret = model.get("api_key") if isinstance(model, dict) else None
    if isinstance(secret, str) and secret.startswith("env:") and secret[4:]:
        return secret[4:]
    return None


def _extract_target_workspace(raw_prompt: str, current_workspace: str) -> tuple[str, str]:
    """Compatibility wrapper around the shared bounded task-intake parser."""
    intake = analyze_task_input(raw_prompt)
    return intake.requested_workspace or current_workspace, raw_prompt.strip()


def _configured_models(config_path: str | Path) -> dict[str, dict[str, Any]]:
    data = _config_data(config_path)
    raw = data.get("models")
    result = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}
    for model in _discover_local_ollama_models():
        if any(str(item.get("model") or "") == model for item in result.values()):
            continue
        alias = _safe_local_alias(model, result)
        result[alias] = {
            "provider": "openai-compatible",
            "model": model,
            "endpoint": "http://127.0.0.1:11434/v1/",
            "_discovered": True,
        }
    return result


def _configured_mcp(config_path: str | Path) -> list[dict[str, Any]]:
    data = _config_data(config_path)
    raw = data.get("mcp")
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


@dataclass
class AppState:
    workspace: str = "."
    config: str = "harness.toml"
    mode: str = "software"
    acceptance: tuple[str, ...] = ()
    execution_backend: str | None = None
    strict_layout: bool | None = None
    strict_tool_isolation: bool | None = None
    network_policy: str | None = None
    require_sealed_oracle: bool | None = None
    require_oracle_isolation: bool | None = None
    session_env: dict[str, str] = field(default_factory=dict, repr=False)
    last_run: str | None = None

    def model_status(self) -> tuple[str, str, bool]:
        alias, model, ready = _model_status(self.config)
        secret_name = _secret_name_for_default(self.config)
        if secret_name and secret_name in self.session_env:
            ready = True
        return alias, model, ready

    def security_mapping(self) -> dict[str, Any]:
        values = {
            "execution_backend": self.execution_backend,
            "strict_layout": self.strict_layout,
            "strict_tool_isolation": self.strict_tool_isolation,
            "network_policy": self.network_policy,
            "require_sealed_oracle": self.require_sealed_oracle,
            "require_oracle_isolation": self.require_oracle_isolation,
        }
        return {key: value for key, value in values.items() if value is not None}


class SlashCompleter(Completer):
    def __init__(self, state: AppState):
        self.state = state

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        if " " not in text:
            for command in COMMANDS:
                if command.startswith(text):
                    yield Completion(command, start_position=-len(text))
            return
        command, fragment = text.split(" ", 1)
        choices: list[str] = []
        if command == "/connect":
            choices = list(PROVIDER_PRESETS)
        elif command in {"/model", "/models"}:
            choices = list(_configured_models(self.state.config))
        elif command in {"/domain", "/mode"}:
            choices = ["software", "hackathon", "ctf", "demo"]
        elif command == "/permissions":
            choices = ["isolated", "local"]
        elif command == "/mcp":
            choices = ["list", "search", "add"]
        elif command == "/skills":
            try:
                choices = [item.name for item in SkillCatalog.default(workspace=self.state.workspace).list()]
            except Exception:
                choices = []
        for choice in choices:
            if choice.startswith(fragment):
                yield Completion(choice, start_position=-len(fragment))


class JsonlTail:
    def __init__(self, path: Path):
        self.path = path
        self.offset = 0
        self.pending = ""

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                handle.seek(self.offset)
                chunk = handle.read()
                self.offset = handle.tell()
        except (OSError, UnicodeError):
            return []
        if not chunk:
            return []
        text = self.pending + chunk
        lines = text.split("\n")
        self.pending = lines.pop()
        rows: list[dict[str, Any]] = []
        for line in lines:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
        return rows


def _bottom_toolbar(state: AppState):
    alias, model, ready = state.model_status()
    status = "configured" if ready else "setup needed"
    cwd = Path(state.workspace).expanduser().resolve()
    return FormattedText([
        ("class:toolbar", f" {state.mode}  │  {alias}:{model}  │  {status}  │  {cwd.name or cwd}  │  /help "),
    ])


def _banner(state: AppState) -> None:
    alias, model, ready = state.model_status()
    status = "configured" if ready else "model setup needed"
    root = Path(state.workspace).expanduser().resolve()
    _emit(("class:accent", "╭─ "), ("class:assistant", f"base_harness {__version__}"))
    _emit(("class:accent", "│  "), ("class:muted", str(root)))
    _emit(("class:accent", "│  "), ("class:assistant", f"{alias}:{model}"), ("class:muted", f" · {state.mode} · {status}"))
    _emit(("class:accent", "╰─ "), ("class:muted", "type a task · /help for commands · Ctrl+C to stop a run"))
    print()


def _print_user(text: str) -> None:
    _emit(("class:user", "❯ "), ("class:assistant", text))


def _print_note(text: str) -> None:
    _emit(("class:muted", "  │ "), ("class:assistant", text))


def _print_error(text: str) -> None:
    _emit(("class:bad", "  ✕ "), ("class:assistant", text))


def _print_good(text: str) -> None:
    _emit(("class:good", "  ✓ "), ("class:assistant", text))


def _prompt_text(session: PromptSession, label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = session.prompt(FormattedText([("class:muted", f"{label}{suffix}: ")]), style=STYLE).strip()
    return value or default


def _prompt_secret(session: PromptSession, label: str = "API key") -> str:
    """Read a secret without mutating the long-lived conversation PromptSession."""
    del session  # The caller's conversation session must never enter password mode.
    secret_session: PromptSession = PromptSession()
    return secret_session.prompt(
        FormattedText([("class:muted", f"{label}: ")]),
        is_password=True,
        style=STYLE,
    ).strip()


def _connect(state: AppState, session: PromptSession, argument: str = "") -> None:
    requested = argument.strip().split()[0] if argument.strip() else ""
    if requested and requested not in PROVIDER_PRESETS:
        _print_error("Unknown provider. Use gemini, openai, openai-compatible, or ollama.")
        return

    data = _config_data(state.config)
    models = data.get("models") if isinstance(data.get("models"), dict) else {}

    if not requested:
        existing_alias, _, ready = state.model_status()
        if existing_alias != "not connected":
            if ready:
                _print_good(f"Using configured model · {existing_alias}")
                return
            secret_name = _secret_name_for_default(state.config)
            if secret_name:
                key = _prompt_secret(session)
                if key:
                    state.session_env[secret_name] = key
                    _print_good(f"Credential loaded for this TUI session · {secret_name}")
                return
        requested = _prompt_text(
            session,
            "Provider (gemini|openai|ollama|openai-compatible)",
            "ollama" if _discover_local_ollama_models() else "gemini",
        )
        if requested not in PROVIDER_PRESETS:
            _print_error("Unknown provider.")
            return

    if requested in models:
        _set_default_model(state.config, requested)
        secret_name = _secret_name_for_default(state.config)
        if secret_name and not (os.environ.get(secret_name) or state.session_env.get(secret_name)):
            key = _prompt_secret(session)
            if key:
                state.session_env[secret_name] = key
        alias, model, ready = state.model_status()
        if ready:
            _print_good(f"Using {alias} · {model}")
        else:
            _print_error("Credential is still missing.")
        return

    if requested == "ollama":
        local_models = _discover_local_ollama_models()
        if not local_models:
            _print_error("Ollama was not reachable at 127.0.0.1:11434.")
            return
        model = _prompt_text(session, "Ollama model", local_models[0])
        if model not in local_models:
            _print_error("That model is not currently reported by Ollama.")
            return
        try:
            alias = _ensure_local_ollama_route(state.config, model)
        except (OSError, SkillActionError, ValueError) as exc:
            _print_error(f"Connection failed: {exc}")
            return
        _print_good(f"Connected {alias} · {model}")
        return

    preset = PROVIDER_PRESETS[requested]
    defaults = {
        "gemini": "gemini-3.5-flash",
        "openai": "gpt-5-mini",
        "openai-compatible": "default-model",
    }
    model = _prompt_text(session, "Model", defaults.get(requested, ""))
    endpoint = preset.endpoint or _prompt_text(session, "Endpoint")
    if not model or not endpoint:
        _print_error("Model and endpoint are required.")
        return

    secret_env = preset.default_secret_env
    if requested == "openai-compatible":
        key = _prompt_secret(session, "API key (optional for local endpoints)")
        if key and secret_env:
            state.session_env[secret_env] = key
        persisted_secret = secret_env if key else ""
    else:
        key = _prompt_secret(session)
        if key and secret_env:
            state.session_env[secret_env] = key
        persisted_secret = secret_env

    try:
        configure_provider(
            state.config,
            alias=requested,
            preset=requested,
            model=model,
            endpoint=endpoint,
            secret_env=persisted_secret,
            make_default=True,
        )
    except Exception as exc:
        _print_error(f"Connection failed: {exc}")
        return
    _print_good(f"Connected {requested} · {model}")


def _models(state: AppState, session: PromptSession, argument: str = "") -> None:
    models = _configured_models(state.config)
    if not models:
        _print_note("No configured or locally discovered models. Use /connect.")
        return
    current = _config_data(state.config).get("default_model")
    requested = argument.strip()
    if not requested:
        _emit(("class:assistant", "Models"))
        for alias, item in models.items():
            active = alias == current
            marker = "●" if active else "○"
            cls = "class:good" if active else "class:muted"
            source = "local" if item.get("_discovered") or "11434" in str(item.get("endpoint") or "") else "api"
            _emit((cls, f"  {marker} {alias:<20}"), ("class:assistant", str(item.get("model") or alias)), ("class:muted", f" · {source}"))
        requested = _prompt_text(session, "Model", str(current or next(iter(models))))
    item = models.get(requested)
    if not item:
        _print_error(f"Unknown model alias: {requested}")
        return
    try:
        if item.get("_discovered"):
            alias = _ensure_local_ollama_route(state.config, str(item.get("model")))
            _print_good(f"Using {alias} · {item.get('model')}")
        else:
            _set_default_model(state.config, requested)
            _print_good(f"Using {requested} · {item.get('model', '-')}")
    except Exception as exc:
        _print_error(str(exc))


def _mcp(state: AppState, session: PromptSession, argument: str = "") -> None:
    parts = argument.strip().split(maxsplit=1)
    action = parts[0] if parts else "list"
    rest = parts[1] if len(parts) > 1 else ""
    if action == "list":
        servers = _configured_mcp(state.config)
        if not servers:
            _print_note("No MCP servers configured. Use /mcp search <query> or /mcp add.")
            return
        _emit(("class:assistant", "MCP servers"))
        for item in servers:
            enabled = bool(item.get("enabled", True))
            cls = "class:good" if enabled else "class:muted"
            _emit((cls, f"  {'●' if enabled else '○'} {item.get('name', '-')}"), ("class:muted", " · stdio"))
        return
    if action == "search":
        query = rest.strip() or _prompt_text(session, "Search MCP Registry")
        if not query:
            return
        try:
            items = search_mcp_registry(query)
        except SkillActionError as exc:
            _print_error(str(exc))
            return
        if not items:
            _print_note("No matching MCP servers found.")
            return
        for item in items:
            version = f" · {item.version}" if item.version else ""
            _emit(("class:tool", f"  ● {item.name}"), ("class:muted", version))
            if item.description:
                _emit(("class:muted", f"    {item.description}"))
        _print_note("Discovery only. Review a server before /mcp add.")
        return
    if action == "add":
        name = _prompt_text(session, "MCP name")
        command_line = _prompt_text(session, "stdio command")
        if not name or not command_line:
            _print_error("MCP name and command are required.")
            return
        try:
            argv = tuple(shlex.split(command_line, posix=os.name != "nt"))
            configure_mcp(state.config, name=name, command=argv)
        except (ValueError, SkillActionError, OSError) as exc:
            _print_error(f"MCP configuration failed: {exc}")
            return
        _print_good(f"Configured MCP {name}. Runtime permission policy still applies.")
        return
    _print_error("Use /mcp list, /mcp search <query>, or /mcp add.")


def _skills(state: AppState, query: str = "") -> None:
    try:
        items = SkillCatalog.default(workspace=state.workspace).search(query.strip())
    except (OSError, UnicodeError, SkillError) as exc:
        _print_error(f"Skill discovery failed: {exc}")
        return
    if not items:
        _print_note("No matching skills.")
        return
    for skill in items:
        _emit(("class:accent", f"  ● {skill.name:<20}"), ("class:muted", skill.description))


def _permissions(state: AppState, argument: str = "") -> None:
    requested = argument.strip().lower()
    if requested:
        if requested == "isolated":
            if os.name == "nt":
                _print_error("The isolated preset requires Linux/WSL. Run the TUI inside WSL or use the explicit local preset.")
                return
            values = {
                "execution_backend": "linux-namespace",
                "strict_layout": True,
                "strict_tool_isolation": True,
                "network_policy": "deny",
                "require_sealed_oracle": False,
                "require_oracle_isolation": True,
            }
        elif requested == "local":
            values = {
                "execution_backend": "local",
                "strict_layout": False,
                "strict_tool_isolation": False,
                "network_policy": "allow",
                "require_sealed_oracle": False,
                "require_oracle_isolation": False,
            }
        else:
            _print_error("Use /permissions isolated or /permissions local.")
            return
        try:
            persist_tui_settings(state.config, security=values)
        except (OSError, TUIConfigError) as exc:
            _print_error(f"Security settings were not saved: {exc}")
            return
        state.execution_backend = values["execution_backend"]
        state.strict_layout = values["strict_layout"]
        state.strict_tool_isolation = values["strict_tool_isolation"]
        state.network_policy = values["network_policy"]
        state.require_sealed_oracle = values["require_sealed_oracle"]
        state.require_oracle_isolation = values["require_oracle_isolation"]
        _print_good(f"Permission preset · {requested} · saved to TOML")

    _emit(("class:assistant", "Execution boundary"))
    for key, value in (
        ("execution_backend", state.execution_backend or "config default"),
        ("strict_layout", state.strict_layout if state.strict_layout is not None else "config default"),
        ("strict_tool_isolation", state.strict_tool_isolation if state.strict_tool_isolation is not None else "config default"),
        ("network_policy", state.network_policy or "config default"),
        ("require_sealed_oracle", state.require_sealed_oracle if state.require_sealed_oracle is not None else "config default"),
        ("require_oracle_isolation", state.require_oracle_isolation if state.require_oracle_isolation is not None else "config default"),
    ):
        _emit(("class:muted", f"  {key:<24}"), ("class:assistant", str(value)))
    if state.execution_backend == "local":
        _print_note("Local mode sanitizes the environment but is not an OS filesystem/network sandbox.")
    else:
        _print_note("The CLI/runtime enforces the persisted policy; the TUI does not synthesize authority.")


def _status(state: AppState) -> None:
    alias, model, ready = state.model_status()
    acceptance = state.acceptance or _detect_acceptance(state.workspace)
    _emit(("class:assistant", "Session"))
    _emit(("class:muted", "  workspace   "), ("class:assistant", str(Path(state.workspace).expanduser().resolve())))
    _emit(("class:muted", "  domain      "), ("class:assistant", state.mode))
    _emit(("class:muted", "  config      "), ("class:assistant", str(Path(state.config).expanduser().resolve())))
    _emit(("class:muted", "  backend     "), ("class:assistant", state.execution_backend or "config default"))
    _emit(("class:muted", "  model       "), ("class:assistant", f"{alias} · {model}"))
    _emit(("class:muted", "  route       "), (("class:good" if ready else "class:warn"), "configured" if ready else "setup needed"))
    _emit(("class:muted", "  fixed check "), ("class:assistant", acceptance[0] if acceptance else "profile/task contract"))
    if state.last_run:
        _emit(("class:muted", "  last run    "), ("class:assistant", state.last_run))


def _help() -> None:
    rows = (
        ("/connect [provider]", "connect a model route or load a session credential"),
        ("/model [alias]", "show or switch model"),
        ("/mcp list|search|add", "discover/configure MCP"),
        ("/skills [query]", "inspect available SKILL.md guidance"),
        ("/domain [name]", "select software / hackathon / ctf / demo and save it"),
        ("/mode [name]", "compatibility alias for /domain"),
        ("/accept [command]", "set a fixed completion command"),
        ("/workspace [path]", "switch project directory"),
        ("/resume <run-dir>", "resume a persisted run"),
        ("/inspect <run-dir>", "inspect a persisted run"),
        ("/permissions [isolated|local]", "show or persist an execution boundary preset"),
        ("/status", "show session state"),
        ("/new", "clear last-run conversation state"),
        ("/clear", "clear terminal"),
        ("/exit", "quit"),
    )
    _emit(("class:assistant", "Commands"))
    for command, description in rows:
        _emit(("class:accent", f"  {command:<24}"), ("class:muted", description))


def _process_env(state: AppState) -> dict[str, str]:
    result = dict(os.environ)
    result.update(state.session_env)
    return result


def _ensure_model_ready(state: AppState, session: PromptSession) -> bool:
    if state.model_status()[2]:
        return True
    local_models = _discover_local_ollama_models()
    if local_models:
        try:
            alias = _ensure_local_ollama_route(state.config, local_models[0])
        except (OSError, SkillActionError, ValueError) as exc:
            _print_error(f"Local model route could not be configured: {exc}")
            return False
        _print_good(f"Using local Ollama · {alias}:{local_models[0]}")
        return state.model_status()[2]
    _print_note("No usable model route is configured yet.")
    _connect(state, session)
    return state.model_status()[2]


def _task_spec(state: AppState, task: str) -> RunLaunchSpec:
    """Build a CLI request while persisted TOML remains the policy source."""
    intake = analyze_task_input(task)
    workspace = intake.requested_workspace or state.workspace
    acceptance = () if intake.artifact_target else (state.acceptance or _detect_acceptance(workspace))
    if state.mode in {"ctf", "demo"}:
        acceptance = ()
    return RunLaunchSpec(
        config=state.config if Path(state.config).expanduser().exists() else None,
        workspace=workspace,
        run_dir=_default_new_run_dir(),
        profile=state.mode,
        goal=task,
        acceptance_commands=tuple(acceptance),
        max_steps=30,
        resume=False,
    )


def _handle_command(state: AppState, session: PromptSession, raw: str) -> bool:
    command, _, argument = raw.strip().partition(" ")
    if command in {"/exit", "/quit"}:
        return False
    if command == "/help":
        _help()
    elif command == "/status":
        _status(state)
    elif command == "/connect":
        _connect(state, session, argument)
    elif command in {"/model", "/models"}:
        _models(state, session, argument)
    elif command == "/mcp":
        _mcp(state, session, argument)
    elif command == "/skills":
        _skills(state, argument)
    elif command in {"/domain", "/mode"}:
        value = argument.strip() or _prompt_text(session, "Domain", state.mode)
        if value not in {"software", "hackathon", "ctf", "demo"}:
            _print_error("Domain must be software, hackathon, ctf, or demo.")
        else:
            try:
                persist_tui_settings(state.config, profile=value)
            except (OSError, TUIConfigError) as exc:
                _print_error(f"Domain was not saved: {exc}")
            else:
                state.mode = value
                _print_good(f"Domain · {state.mode} · saved to TOML")
    elif command == "/accept":
        value = argument.strip() or _prompt_text(session, "Acceptance command", state.acceptance[0] if state.acceptance else "")
        acceptance = (value,) if value else ()
        try:
            persist_tui_settings(state.config, acceptance_commands=acceptance)
        except (OSError, TUIConfigError) as exc:
            _print_error(f"Acceptance command was not saved: {exc}")
        else:
            state.acceptance = acceptance
            _print_good("Fixed acceptance saved." if value else "Fixed acceptance reset and saved.")
    elif command == "/workspace":
        value = argument.strip() or _prompt_text(session, "Workspace", state.workspace)
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists() or not path.is_dir():
            _print_error("Workspace must be an existing directory.")
        else:
            resolved = str(path.resolve())
            try:
                persist_tui_settings(state.config, workspace=resolved)
            except (OSError, TUIConfigError) as exc:
                _print_error(f"Workspace was not saved: {exc}")
            else:
                state.workspace = resolved
                _print_good(f"Workspace · {state.workspace} · saved to TOML")
    elif command in {"/resume", "/inspect"}:
        _print_note(f"{command} is handled by the conversational frontend.")
    elif command == "/permissions":
        _permissions(state, argument)
    elif command == "/new":
        state.last_run = None
        _print_good("Fresh conversation state.")
    elif command == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        _banner(state)
    else:
        _print_error(f"Unknown command: {command}. Use /help.")
    print()
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="base_harness conversational terminal UI")
    parser.add_argument("--workspace")
    parser.add_argument("--config")
    parser.add_argument("--domain", dest="mode", choices=["software", "hackathon", "ctf", "demo"])
    parser.add_argument("--mode", dest="mode", choices=["software", "hackathon", "ctf", "demo"], help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Compatibility entrypoint. The installed TUI is the shared conversational frontend."""
    from harness.tui_conversation import main as conversation_main

    return conversation_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
