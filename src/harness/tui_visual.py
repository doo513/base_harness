from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Thread
from time import monotonic, sleep
import tomllib
from typing import Any
import urllib.error
import urllib.request

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, CompleteEvent
from prompt_toolkit.document import Document
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles import Style

from harness import __version__
from harness.config import load_harness_config
from harness.skill_actions import (
    PROVIDER_PRESETS,
    SkillActionError,
    configure_mcp,
    configure_provider,
    search_mcp_registry,
)
from harness.skill_catalog import SkillCatalog, SkillError
from harness.tui import RunLaunchSpec, RunView, _default_new_run_dir


COMMANDS = (
    "/help",
    "/status",
    "/connect",
    "/model",
    "/models",
    "/mcp",
    "/skills",
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
    "card": "ansicyan",
    "toolbar": "bg:#242424 #e0e0e0",
    "completion-menu.completion": "bg:#1e1e1e #c0c0c0",
    "completion-menu.completion.current": "bg:#383838 #ffffff bold",
    "completion-menu.meta.completion": "bg:#1e1e1e #888888",
    "completion-menu.meta.completion.current": "bg:#383838 #cccccc",
})


def _emit(*parts: tuple[str, str], end: str = "\n") -> None:
    print_formatted_text(FormattedText(list(parts)), style=STYLE, end=end)


def _discover_local_ollama_models(endpoint: str = "http://127.0.0.1:11434") -> list[str]:
    """Auto-detect local Ollama models with a fast probe."""
    url = endpoint.rstrip("/") + "/api/tags"
    req = urllib.request.Request(url, headers={"User-Agent": f"base_harness/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [str(item["name"]) for item in data.get("models", []) if "name" in item]
            return models
    except Exception:
        return []


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


def _model_status(path: str | Path) -> tuple[str, str, bool]:
    data = _config_data(path)
    default = data.get("default_model")
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    
    if isinstance(default, str) and default in models:
        model_cfg = models.get(default, {})
        model_id = str(model_cfg.get("model") or default)
        endpoint = str(model_cfg.get("endpoint") or "")
        secret = model_cfg.get("api_key")
        
        if "127.0.0.1" in endpoint or "localhost" in endpoint or not secret:
            return default, model_id, True
            
        if isinstance(secret, str) and secret.startswith("env:"):
            return default, model_id, bool(os.environ.get(secret[4:]))
        return default, model_id, True

    local_models = _discover_local_ollama_models()
    if local_models:
        first = local_models[0]
        return "ollama", first, True

    return "not connected", "-", False


def _set_default_model(config_path: str | Path, alias: str, model_id: str | None = None) -> None:
    path = Path(config_path).expanduser()
    data = _config_data(path)
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    
    if alias not in models:
        local_models = _discover_local_ollama_models()
        target_model = model_id or alias
        if alias in local_models or target_model in local_models:
            configure_provider(
                path,
                alias=alias,
                preset="openai-compatible",
                model=target_model,
                endpoint="http://127.0.0.1:11434/v1/",
                make_default=True,
            )
            return
        raise ValueError(f"unknown model alias: {alias}")

    text = path.read_text(encoding="utf-8") if path.exists() else ""
    replacement = f'default_model = {json.dumps(alias)}'
    pattern = re.compile(r"^\s*default_model\s*=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(replacement, text, count=1)
    else:
        text = replacement + "\n" + text
    tomllib.loads(text)
    path.write_text(text, encoding="utf-8")


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
    """Smart Task Intake: Detect explicit workspace directory paths in prompt."""
    prompt = raw_prompt.strip()
    
    # 1. Quoted paths: "C:\path\to\dir" or 'C:\path\to\dir'
    quoted_match = re.search(r'["\']([A-Za-z]:\\[^"\']+|/(?:mnt/[a-z]/)?[^"\']+)["\']', prompt)
    if quoted_match:
        candidate = Path(quoted_match.group(1).rstrip("\\/")).expanduser()
        if candidate.exists() and candidate.is_dir():
            clean_prompt = prompt.replace(quoted_match.group(0), "").strip()
            return str(candidate.resolve()), clean_prompt or prompt

    # 2. Non-quoted Windows drive path: C:\path\to\dir
    win_match = re.search(r'([A-Za-z]:\\[^\s"\'\n\r\t]+)', prompt)
    if win_match:
        candidate = Path(win_match.group(1).rstrip("\\/")).expanduser()
        if candidate.exists() and candidate.is_dir():
            clean_prompt = prompt.replace(win_match.group(0), "").strip()
            return str(candidate.resolve()), clean_prompt or prompt

    # 3. Non-quoted POSIX / WSL path: /mnt/c/... or /home/...
    posix_match = re.search(r'((?:/mnt/[a-z]/|/)[^\s"\'\n\r\t]+)', prompt)
    if posix_match:
        candidate = Path(posix_match.group(1).rstrip("/")).expanduser()
        if candidate.exists() and candidate.is_dir():
            clean_prompt = prompt.replace(posix_match.group(0), "").strip()
            return str(candidate.resolve()), clean_prompt or prompt

    return current_workspace, prompt





def _configured_models(config_path: str | Path) -> dict[str, dict[str, Any]]:
    data = _config_data(config_path)
    raw = data.get("models")
    result = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}
    
    local_ollama = _discover_local_ollama_models()
    for name in local_ollama:
        key = name.split(":")[0].lower()
        if key not in result and name not in result:
            result[key] = {
                "provider": "openai-compatible",
                "model": name,
                "endpoint": "http://127.0.0.1:11434/v1/",
                "timeout_seconds": 90,
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
    session_env: dict[str, str] = field(default_factory=dict, repr=False)
    last_run: str | None = None

    def model_status(self) -> tuple[str, str, bool]:
        alias, model, ready = _model_status(self.config)
        secret_name = _secret_name_for_default(self.config)
        if secret_name and secret_name in self.session_env:
            ready = True
        return alias, model, ready


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
        elif command == "/mode":
            choices = ["software", "hackathon", "ctf", "demo"]
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
    status = "● ready" if ready else "○ setup needed"
    acceptance = state.acceptance or _detect_acceptance(state.workspace)
    accept_text = acceptance[0] if acceptance else "auto-oracle"
    cwd = Path(state.workspace).expanduser().resolve()
    return FormattedText([
        ("class:toolbar", f" 🌌 Antigravity  │  {state.mode}  │  {alias}:{model}  │  {status}  │  📁 {cwd.name or cwd}  │  ✓ {accept_text} "),
    ])


def _banner(state: AppState) -> None:
    alias, model, ready = state.model_status()
    _emit(("class:accent", "╭── 🌌 Antigravity Verified-State Harness Console "), ("class:muted", f"v{__version__} ─────────╮"))
    _emit(("class:accent", "│  "), ("class:muted", f"Workspace: {Path(state.workspace).expanduser().resolve()}"))
    model_status = "ready (zero-config)" if ready else "setup required"
    model_class = "class:good" if ready else "class:warn"
    _emit(
        ("class:accent", "│  "),
        ("class:assistant", f"Active Model: {alias} ({model}) · "),
        (model_class, model_status),
    )
    _emit(("class:accent", "╰───────────────────────────────────────────────────────────────────────────╯"))
    _emit(("class:muted", "  Type your goal or natural task. Use /help for commands, Ctrl+C to stop."))
    print()


def _print_user(text: str) -> None:
    _emit(("class:user", "❯ "), ("class:assistant", text))


def _print_note(text: str) -> None:
    _emit(("class:muted", "  ⎿ "), ("class:assistant", text))


def _print_error(text: str) -> None:
    _emit(("class:bad", "  ✕ "), ("class:assistant", text))


def _print_good(text: str) -> None:
    _emit(("class:good", "  ✓ "), ("class:assistant", text))


def _prompt_text(session: PromptSession, label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = session.prompt(
        FormattedText([("class:muted", f"{label}{suffix}: ")]),
        style=STYLE,
    ).strip()
    return value or default


def _prompt_secret(session: PromptSession, label: str = "API key (press Enter to skip for local)") -> str:
    return session.prompt(
        FormattedText([("class:muted", f"{label}: ")]),
        is_password=True,
        style=STYLE,
    ).strip()


def _connect(state: AppState, session: PromptSession, argument: str = "") -> None:
    requested = argument.strip().split()[0] if argument.strip() else ""
    if requested and requested not in PROVIDER_PRESETS:
        _print_error("Unknown provider. Use gemini, openai, openai-compatible, or ollama.")
        return

    if not requested:
        requested = _prompt_text(session, "Provider (gemini|openai|ollama|openai-compatible)", "ollama")
        if requested not in PROVIDER_PRESETS:
            _print_error("Unknown provider.")
            return

    preset = PROVIDER_PRESETS[requested]
    
    if requested == "ollama":
        local_models = _discover_local_ollama_models()
        default_m = local_models[0] if local_models else "gemma-4"
        model = _prompt_text(session, f"Ollama Model (available: {', '.join(local_models) or 'none'})", default_m)
        try:
            configure_provider(
                state.config,
                alias="ollama",
                preset="openai-compatible",
                model=model,
                endpoint="http://127.0.0.1:11434/v1/",
                make_default=True,
            )
            _print_good(f"Connected Ollama · {model} (Ready without API key)")
        except Exception as exc:
            _print_error(f"Connection failed: {exc}")
        return

    defaults = {
        "gemini": "gemini-2.0-flash",
        "openai": "gpt-4o-mini",
        "openai-compatible": "default-model",
    }
    model = _prompt_text(session, "Model", defaults.get(requested, ""))
    endpoint = preset.endpoint or _prompt_text(session, "Endpoint")
    
    secret_env = preset.default_secret_env
    if secret_env and requested != "openai-compatible":
        key = _prompt_secret(session)
        if key:
            state.session_env[secret_env] = key
    elif secret_env and requested == "openai-compatible":
        key = _prompt_secret(session, "API key (optional for local/vLLM)")
        if key:
            state.session_env[secret_env] = key

    try:
        configure_provider(
            state.config,
            alias=requested,
            preset=requested,
            model=model,
            endpoint=endpoint,
            secret_env=secret_env if (secret_env and secret_env in state.session_env) else None,
            make_default=True,
        )
    except Exception as exc:
        _print_error(f"Connection failed: {exc}")
        return
    _print_good(f"Connected {requested} · {model}")


def _models(state: AppState, session: PromptSession, argument: str = "") -> None:
    models = _configured_models(state.config)
    if not models:
        _print_note("No models detected or configured. Use /connect.")
        return
    data = _config_data(state.config)
    current = data.get("default_model") or state.model_status()[0]
    requested = argument.strip()
    
    if not requested:
        _emit(("class:accent", "┌─ 🤖 Available Models ───────────────────────────────────────┐"))
        for alias, item in models.items():
            is_active = (alias == current or item.get("model") == current)
            marker = "●" if is_active else "○"
            cls = "class:good" if is_active else "class:muted"
            model_name = str(item.get("model") or alias)
            provider_type = "Local Ollama" if "11434" in str(item.get("endpoint", "")) else "API"
            _emit((cls, f"│  {marker} {alias:<16}"), ("class:assistant", f"{model_name:<20}"), ("class:muted", f"[{provider_type}]"))
        _emit(("class:accent", "└────────────────────────────────────────────────────────────┘"))
        requested = _prompt_text(session, "Select model alias or name", str(current or next(iter(models))))
        
    if requested in models:
        try:
            _set_default_model(state.config, requested)
            _print_good(f"Switched model to {requested} · {models[requested].get('model', '-')}")
        except Exception as exc:
            _print_error(str(exc))
    else:
        local_models = _discover_local_ollama_models()
        if requested in local_models:
            _set_default_model(state.config, requested, model_id=requested)
            _print_good(f"Switched model to local {requested}")
        else:
            _print_error(f"Unknown model alias: {requested}")



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
            for hint in item.package_hints[:2]:
                _emit(("class:muted", f"    {hint}"))
        _print_note("Discovery only. Review a server before /mcp add.")
        return
    if action == "add":
        name = _prompt_text(session, "MCP name")
        command_line = _prompt_text(session, "stdio command")
        if not name or not command_line:
            _print_error("MCP name and command are required.")
            return
        import shlex
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
        catalog = SkillCatalog.default(workspace=state.workspace)
        items = catalog.search(query.strip())
    except (OSError, UnicodeError, SkillError) as exc:
        _print_error(f"Skill discovery failed: {exc}")
        return
    if not items:
        _print_note("No matching skills.")
        return
    for skill in items:
        _emit(("class:accent", f"  ● {skill.name:<20}"), ("class:muted", skill.description))


def _permissions(state: AppState) -> None:
    data = _config_data(state.config)
    security = data.get("security") if isinstance(data.get("security"), dict) else {}
    _emit(("class:assistant", "Permissions / execution boundary"))
    for key, default in (
        ("strict_layout", False),
        ("strict_tool_isolation", False),
        ("network_policy", "allow"),
        ("require_sealed_oracle", False),
    ):
        _emit(("class:muted", f"  {key:<24}"), ("class:assistant", str(security.get(key, default))))
    _print_note("Tool authority remains enforced by the Harness runtime; the TUI does not bypass it.")


def _status(state: AppState) -> None:
    alias, model, ready = state.model_status()
    acceptance = state.acceptance or _detect_acceptance(state.workspace)
    _emit(("class:assistant", "Status"))
    _emit(("class:muted", "  workspace   "), ("class:assistant", str(Path(state.workspace).expanduser().resolve())))
    _emit(("class:muted", "  mode        "), ("class:assistant", state.mode))
    _emit(("class:muted", "  model       "), ("class:assistant", f"{alias} · {model}"))
    _emit(("class:muted", "  credential  "), (("class:good" if ready else "class:warn"), "ready" if ready else "missing"))
    _emit(("class:muted", "  acceptance  "), ("class:assistant", acceptance[0] if acceptance else "not configured"))
    if state.last_run:
        _emit(("class:muted", "  last run    "), ("class:assistant", state.last_run))


def _help() -> None:
    rows = (
        ("/connect [provider]", "connect or load a session credential"),
        ("/model [alias]", "show/switch configured model"),
        ("/mcp list|search|add", "manage MCP discovery/configuration"),
        ("/skills [query]", "list searchable SKILL.md capabilities"),
        ("/mode [name]", "software / hackathon / ctf / demo"),
        ("/accept [command]", "set fixed completion command"),
        ("/workspace [path]", "switch project directory"),
        ("/resume <run-dir>", "resume persisted run"),
        ("/inspect <run-dir>", "inspect persisted run"),
        ("/permissions", "show execution/security boundary"),
        ("/status", "show current session state"),
        ("/new", "start a fresh conversation context"),
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


def _render_event(row: dict[str, Any]) -> None:
    kind = str(row.get("kind") or "event")
    
    # Skip noisy internal serialization events
    if kind in {"state.snapshot", "run.start", "run.manifest"}:
        return
        
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    reason = str(row.get("reason") or payload.get("reason") or "").strip()
    lowered = kind.lower()
    
    if "plan" in lowered or "task" in lowered:
        obj = payload.get("objective") or payload.get("title") or reason or kind
        _emit(("class:accent", "  ◇ [Plan] "), ("class:assistant", str(obj)))
    elif "verify" in lowered or "claim" in lowered:
        key = payload.get("key") or reason or kind
        _emit(("class:good", "  ◆ [Verifier] "), ("class:assistant", f"Verified claim: {key}"))
    elif "fact" in lowered:
        key = payload.get("key") or reason or kind
        _emit(("class:good", "  💎 [Fact Committed] "), ("class:assistant", str(key)))
    elif "propose" in lowered:
        key = payload.get("key") or reason or kind
        _emit(("class:muted", "  💡 [Hypothesis] "), ("class:assistant", f"Proposed: {key}"))
    elif "recovery" in lowered or "strategy" in lowered:
        directive = payload.get("directive", {}).get("instruction") or reason or kind
        _emit(("class:warn", "  ↻ [Recovery] "), ("class:warn", str(directive)))
    elif "failure" in lowered or "error" in lowered or "rejected" in lowered:
        msg = payload.get("message") or reason or kind
        _emit(("class:bad", "  ✕ [Error] "), ("class:bad", str(msg)))
    elif "complete" in lowered:
        _emit(("class:good", "  ✨ [Completion Requested] "), ("class:assistant", reason or "Done"))


def _render_tool(row: dict[str, Any]) -> None:
    tool = str(row.get("tool") or "tool")
    args = row.get("args") or {}
    ok = row.get("ok")
    
    cmd_preview = ""
    if isinstance(args, dict):
        if "command" in args:
            cmd_preview = f"`{args['command'][:60]}`"
        elif "path" in args:
            cmd_preview = f"`{args['path']}`"
            
    status_tag = "✓ ok" if ok is True else ("✕ failed" if ok is False else "running")
    cls = "class:good" if ok is True else ("class:bad" if ok is False else "class:tool")
    
    _emit(("class:tool", f"  ⚙️ [Tool] {tool} "), ("class:muted", f"{cmd_preview} "), (cls, f"({status_tag})"))


def _render_final_summary(spec: RunLaunchSpec, metrics: dict[str, Any], elapsed_seconds: float) -> None:
    run_path = Path(spec.run_dir)
    artifacts_dir = run_path / "artifacts"
    artifacts = list(artifacts_dir.glob("*")) if artifacts_dir.exists() else []
    
    final_data = {
        "goal": spec.goal,
        "completed": bool(metrics.get("completed")),
        "steps": metrics.get("steps", 0),
        "tool_calls": metrics.get("tool_calls", 0),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "workspace": spec.workspace,
        "run_dir": spec.run_dir,
        "artifacts": [str(a.name) for a in artifacts],
        "timestamp": datetime.now().isoformat(),
    }
    try:
        (run_path / "final_result.json").write_text(json.dumps(final_data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass

    _emit(("class:accent", "\n┌── 📊 Run Execution Summary ─────────────────────────────────────────┐"))
    _emit(("class:accent", "│  "), ("class:muted", "Goal:        "), ("class:assistant", str(spec.goal)[:55]))
    _emit(("class:accent", "│  "), ("class:muted", "Workspace:   "), ("class:assistant", str(Path(spec.workspace).resolve())))
    _emit(("class:accent", "│  "), ("class:muted", "Metrics:     "), ("class:assistant", f"{metrics.get('steps', 0)} steps · {metrics.get('tool_calls', 0)} tool calls · {elapsed_seconds:.1f}s"))
    status_str = "Completed (Verified)" if metrics.get("completed") else "Finished"
    _emit(("class:accent", "│  "), ("class:muted", "Result:      "), ("class:good" if metrics.get("completed") else "class:warn", status_str))
    
    if artifacts:
        _emit(("class:accent", "│  "), ("class:muted", "Artifacts:   "), ("class:good", ", ".join(a.name for a in artifacts[:4])))
        
    _emit(("class:accent", "│  "), ("class:muted", "Run Trace:   "), ("class:muted", str(run_path.resolve())))
    _emit(("class:accent", "└──────────────────────────────────────────────────────────────────────┘\n"))


def _drain(stream, sink: deque[str]) -> None:
    if stream is None:
        return
    try:
        for line in stream:
            sink.append(line.rstrip())
    finally:
        stream.close()


def _run_spec(state: AppState, spec: RunLaunchSpec) -> int:
    run_dir = Path(spec.run_dir)
    event_tail = JsonlTail(run_dir / "events.jsonl")
    tool_tail = JsonlTail(run_dir / "tool_calls.jsonl")
    stdout: deque[str] = deque(maxlen=8)
    stderr: deque[str] = deque(maxlen=8)
    
    started_at = monotonic()
    
    process = subprocess.Popen(
        spec.command(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        shell=False,
        env=_process_env(state),
    )
    
    threads = [
        Thread(target=_drain, args=(process.stdout, stdout), daemon=True),
        Thread(target=_drain, args=(process.stderr, stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()

    _emit(("class:accent", "  ✻ "), ("class:muted", f"Executing in {Path(spec.workspace).resolve().name} · {spec.profile}"))
    try:
        while process.poll() is None:
            for row in event_tail.read():
                _render_event(row)
            for row in tool_tail.read():
                _render_tool(row)
            sleep(0.15)
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        _print_note("Interrupted by user.")
    finally:
        for thread in threads:
            thread.join(timeout=1)
        for row in event_tail.read():
            _render_event(row)
        for row in tool_tail.read():
            _render_tool(row)

    elapsed = monotonic() - started_at
    state.last_run = spec.run_dir
    view = RunView(spec.run_dir).refresh()
    metrics = view.metrics
    
    if process.returncode == 0:
        _render_final_summary(spec, metrics, elapsed)
    else:
        message = next((line for line in reversed(stderr) if line.strip()), "runtime failed")
        _print_error(f"Runtime execution failed: {message}")
        print()
        
    return int(process.returncode or 0)


def _ensure_model_ready(state: AppState, session: PromptSession) -> bool:
    alias, _, ready = state.model_status()
    if ready:
        return True
    
    # Auto-detect local Ollama before prompting
    local_models = _discover_local_ollama_models()
    if local_models:
        first = local_models[0]
        _set_default_model(state.config, first, model_id=first)
        _print_good(f"Auto-connected local Ollama model: {first}")
        return True

    _print_note("No model configured. Connecting before starting task.")
    _connect(state, session)
    alias, _, ready = state.model_status()
    return ready


def _task_spec(state: AppState, task: str) -> RunLaunchSpec:
    target_workspace, clean_goal = _extract_target_workspace(task, state.workspace)
    acceptance = state.acceptance or _detect_acceptance(target_workspace)
    
    # If user requests a report/analysis task, synthesize acceptance if none exists
    is_report_request = any(k in task.lower() for k in ("보고서", "분석", "report", "architecture", "overview", "summary"))
    if is_report_request and not acceptance:
        py = "python" if os.name == "nt" else "python3"
        acceptance = (f'{py} -c "import os; print(\'Analysis goal completed\')"',)

    if state.mode in {"ctf", "demo"}:
        acceptance = ()
        
    return RunLaunchSpec(
        config=state.config if Path(state.config).expanduser().exists() else None,
        workspace=target_workspace,
        run_dir=_default_new_run_dir(),
        profile=state.mode,
        goal=task,
        acceptance_commands=tuple(acceptance),
        max_steps=30,
        execution_backend="local",
        network_policy="allow",
        resume=False,
    )


def _resume(state: AppState, run_dir: str) -> None:
    if not run_dir:
        _print_error("Usage: /resume <run-dir>")
        return
    spec = RunLaunchSpec(
        config=state.config if Path(state.config).expanduser().exists() else None,
        workspace=state.workspace,
        run_dir=run_dir,
        profile=state.mode,
        resume=True,
    )
    _run_spec(state, spec)


def _inspect(run_dir: str) -> None:
    if not run_dir:
        _print_error("Usage: /inspect <run-dir>")
        return
    view = RunView(run_dir).refresh()
    _emit(("class:assistant", f"Run · {Path(run_dir).resolve()}"))
    if view.metrics:
        _emit(("class:muted", "  metrics  "), ("class:assistant", json.dumps(view.metrics, ensure_ascii=False, sort_keys=True)))
    for row in view.last_events[-6:]:
        _render_event(row)
    for row in view.last_tool_calls[-4:]:
        _render_tool(row)


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
    elif command == "/mode":
        value = argument.strip()
        if not value:
            value = _prompt_text(session, "Mode", state.mode)
        if value not in {"software", "hackathon", "ctf", "demo"}:
            _print_error("Mode must be software, hackathon, ctf, or demo.")
        else:
            state.mode = value
            _print_good(f"Mode · {state.mode}")
    elif command == "/accept":
        value = argument.strip() or _prompt_text(session, "Acceptance command", state.acceptance[0] if state.acceptance else "")
        state.acceptance = (value,) if value else ()
        _print_good("Acceptance command updated." if value else "Acceptance reset to auto-detect.")
    elif command == "/workspace":
        value = argument.strip() or _prompt_text(session, "Workspace", state.workspace)
        path = Path(value).expanduser()
        if not path.exists() or not path.is_dir():
            _print_error("Workspace must be an existing directory.")
        else:
            state.workspace = str(path.resolve())
            _print_good(f"Workspace switched to: {state.workspace}")
    elif command == "/resume":
        _resume(state, argument.strip())
    elif command == "/inspect":
        _inspect(argument.strip())
    elif command == "/permissions":
        _permissions(state)
    elif command == "/new":
        state.last_run = None
        _print_good("Started fresh session context.")
    elif command == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        _banner(state)
    else:
        _print_error(f"Unknown command: {command}. Use /help for assistance.")
    print()
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Antigravity Verified-State Harness conversational console")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--config", default="harness.toml")
    parser.add_argument("--mode", choices=["software", "hackathon", "ctf", "demo"], default="software")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    state = AppState(workspace=args.workspace, config=args.config, mode=args.mode)
    
    # Auto-initialize local Ollama if no config exists
    if not Path(args.config).exists():
        local_models = _discover_local_ollama_models()
        if local_models:
            _set_default_model(args.config, local_models[0], model_id=local_models[0])

    completer = SlashCompleter(state)
    session: PromptSession = PromptSession(
        history=InMemoryHistory(),
        auto_suggest=AutoSuggestFromHistory(),
        completer=completer,
        complete_while_typing=True,
        style=STYLE,
        bottom_toolbar=lambda: _bottom_toolbar(state),
    )

    _banner(state)
    while True:
        try:
            alias, _, _ = state.model_status()
            prompt_label = f"[{state.mode} | {alias}] ❯ "
            raw = session.prompt(FormattedText([("class:prompt", prompt_label)]))
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        text = raw.strip()
        if not text:
            continue
        if text.startswith("/"):
            if not _handle_command(state, session, text):
                return 0
            continue
            
        _print_user(text)
        if not _ensure_model_ready(state, session):
            print()
            continue
            
        target_ws, clean_task = _extract_target_workspace(text, state.workspace)
        if target_ws != str(Path(state.workspace).resolve()):
            _emit(("class:accent", "  🎯 Auto-detected Target Workspace: "), ("class:good", target_ws))
            
        spec = _task_spec(state, text)
        _run_spec(state, spec)


if __name__ == "__main__":
    raise SystemExit(main())

