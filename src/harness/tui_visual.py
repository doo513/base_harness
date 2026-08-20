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
from time import sleep
import tomllib
from typing import Any

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
    "good": "ansigreen",
    "warn": "ansiyellow",
    "bad": "ansired",
    "accent": "ansimagenta",
    "tool": "ansiblue",
    "toolbar": "bg:#303030 #d0d0d0",
    "completion-menu.completion": "bg:#202020 #b0b0b0",
    "completion-menu.completion.current": "bg:#3a3a3a #ffffff bold",
    "completion-menu.meta.completion": "bg:#202020 #777777",
    "completion-menu.meta.completion.current": "bg:#3a3a3a #bbbbbb",
})


def _emit(*parts: tuple[str, str], end: str = "\n") -> None:
    print_formatted_text(FormattedText(list(parts)), style=STYLE, end=end)


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
    if not isinstance(default, str) or default not in models:
        return "not connected", "-", False
    model = models.get(default, {})
    if not isinstance(model, dict):
        return default, "-", False
    model_id = str(model.get("model") or "-")
    secret = model.get("api_key")
    if isinstance(secret, str) and secret.startswith("env:"):
        return default, model_id, bool(os.environ.get(secret[4:]))
    return default, model_id, True


def _set_default_model(config_path: str | Path, alias: str) -> None:
    path = Path(config_path).expanduser()
    data = _config_data(path)
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    if alias not in models:
        raise ValueError(f"unknown model alias: {alias}")
    text = path.read_text(encoding="utf-8")
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


def _configured_models(config_path: str | Path) -> dict[str, dict[str, Any]]:
    data = _config_data(config_path)
    raw = data.get("models")
    if not isinstance(raw, dict):
        return {}
    return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}


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
    status = "ready" if ready else "credential needed"
    acceptance = state.acceptance or _detect_acceptance(state.workspace)
    accept_text = acceptance[0] if acceptance else "no acceptance command"
    cwd = Path(state.workspace).expanduser().resolve()
    return FormattedText([
        ("class:toolbar", f" {state.mode}  │  {alias}/{model}  │  {status}  │  {cwd.name or cwd}  │  {accept_text} "),
    ])


def _banner(state: AppState) -> None:
    alias, model, ready = state.model_status()
    _emit(("class:accent", "╭─ "), ("class:assistant", f"base_harness {__version__}"))
    _emit(("class:accent", "│  "), ("class:muted", str(Path(state.workspace).expanduser().resolve())))
    model_status = "ready" if ready else "connect required"
    model_class = "class:good" if ready else "class:warn"
    _emit(
        ("class:accent", "│  "),
        ("class:assistant", f"{state.mode} · {alias}/{model} · "),
        (model_class, model_status),
    )
    _emit(("class:accent", "╰─ "), ("class:muted", "/help for commands · Ctrl+C interrupts a running task"))
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


def _prompt_secret(session: PromptSession, label: str = "API key") -> str:
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
        existing_alias, _, _ = state.model_status()
        if existing_alias != "not connected":
            secret_name = _secret_name_for_default(state.config)
            if secret_name and not os.environ.get(secret_name) and secret_name not in state.session_env:
                key = _prompt_secret(session)
                if key:
                    state.session_env[secret_name] = key
                    _print_good(f"Credential loaded for this TUI session ({secret_name}).")
                return
        requested = _prompt_text(session, "Provider", "gemini")
        if requested not in PROVIDER_PRESETS:
            _print_error("Unknown provider.")
            return

    preset = PROVIDER_PRESETS[requested]
    data = _config_data(state.config)
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    if requested in models:
        try:
            _set_default_model(state.config, requested)
        except Exception as exc:
            _print_error(str(exc))
            return
        secret_name = _secret_name_for_default(state.config)
        if secret_name and not os.environ.get(secret_name):
            key = _prompt_secret(session)
            if key:
                state.session_env[secret_name] = key
        alias, model, ready = state.model_status()
        if ready:
            _print_good(f"Using {alias} · {model}")
        else:
            _print_error("Credential is still missing.")
        return

    defaults = {
        "gemini": "gemini-3.5-flash",
        "openai": "gpt-5-mini",
        "ollama": "qwen2.5-coder:3b",
    }
    model = _prompt_text(session, "Model", defaults.get(requested, ""))
    if not model:
        _print_error("Model is required.")
        return
    endpoint = preset.endpoint or _prompt_text(session, "Endpoint")
    if not endpoint:
        _print_error("Endpoint is required.")
        return
    secret_env = preset.default_secret_env
    if secret_env:
        key = _prompt_secret(session)
        if not key:
            _print_error("API key is required for this session.")
            return
        state.session_env[secret_env] = key
    try:
        configure_provider(
            state.config,
            alias=requested,
            preset=requested,
            model=model,
            endpoint=endpoint,
            secret_env=secret_env,
            make_default=True,
        )
    except (SkillActionError, OSError, tomllib.TOMLDecodeError) as exc:
        _print_error(f"Connection failed: {exc}")
        return
    _print_good(f"Connected {requested} · {model}")
    if secret_env:
        _print_note("API key is held only in this TUI process; harness.toml stores only env reference metadata.")


def _models(state: AppState, session: PromptSession, argument: str = "") -> None:
    models = _configured_models(state.config)
    if not models:
        _print_note("No models configured. Use /connect.")
        return
    data = _config_data(state.config)
    current = data.get("default_model")
    requested = argument.strip()
    if not requested:
        _emit(("class:assistant", "Configured models"))
        for alias, item in models.items():
            marker = "●" if alias == current else "○"
            cls = "class:good" if alias == current else "class:muted"
            _emit((cls, f"  {marker} {alias:<18}"), ("class:assistant", str(item.get("model") or "-")))
        requested = _prompt_text(session, "Model", str(current or next(iter(models))))
    if requested not in models:
        _print_error(f"Unknown model alias: {requested}")
        return
    try:
        _set_default_model(state.config, requested)
    except Exception as exc:
        _print_error(str(exc))
        return
    _print_good(f"Model switched to {requested} · {models[requested].get('model', '-')}")


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
    reason = str(row.get("reason") or "").strip()
    text = kind + (f" · {reason}" if reason else "")
    lowered = kind.lower()
    if "completion.accepted" in lowered or "verified" in lowered or "verification" in lowered:
        _emit(("class:good", "  ◆ "), ("class:assistant", text))
    elif "failure" in lowered or "error" in lowered or "rejected" in lowered:
        _emit(("class:bad", "  ✕ "), ("class:assistant", text))
    elif "recovery" in lowered or "strategy" in lowered:
        _emit(("class:warn", "  ↻ "), ("class:assistant", text))
    elif "plan" in lowered or "task" in lowered:
        _emit(("class:accent", "  ◇ "), ("class:assistant", text))
    else:
        _emit(("class:muted", "  · "), ("class:assistant", text))


def _render_tool(row: dict[str, Any]) -> None:
    tool = str(row.get("tool") or "tool")
    ok = row.get("ok")
    permission = row.get("permission")
    suffix: list[str] = []
    if ok is not None:
        suffix.append("ok" if ok else "failed")
    if permission:
        suffix.append(str(permission))
    detail = f" · {' · '.join(suffix)}" if suffix else ""
    cls = "class:tool" if ok is not False else "class:bad"
    _emit((cls, f"  ● {tool}"), ("class:muted", detail))


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

    _emit(("class:accent", "  ✻ "), ("class:muted", f"Working · {run_dir}"))
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

    state.last_run = spec.run_dir
    view = RunView(spec.run_dir).refresh()
    metrics = view.metrics
    if process.returncode == 0:
        completed = metrics.get("completed")
        steps = metrics.get("steps", metrics.get("step", "?"))
        tools = metrics.get("tool_calls", "?")
        if completed:
            _print_good(f"Completed · steps {steps} · tools {tools} · {spec.run_dir}")
        else:
            _emit(("class:warn", "  ◇ "), ("class:assistant", f"Run ended without accepted completion · steps {steps} · tools {tools}"))
    else:
        message = next((line for line in reversed(stderr) if line.strip()), "runtime failed")
        _print_error(message)
    print()
    return int(process.returncode or 0)


def _ensure_model_ready(state: AppState, session: PromptSession) -> bool:
    alias, _, ready = state.model_status()
    if alias == "not connected":
        _print_note("No model configured. Connecting before the first task.")
        _connect(state, session)
        alias, _, ready = state.model_status()
    if ready:
        return True
    secret_name = _secret_name_for_default(state.config)
    if not secret_name:
        return False
    key = _prompt_secret(session)
    if not key:
        _print_error("Credential required to run the configured model.")
        return False
    state.session_env[secret_name] = key
    return True


def _task_spec(state: AppState, task: str) -> RunLaunchSpec:
    acceptance = state.acceptance or _detect_acceptance(state.workspace)
    if state.mode in {"ctf", "demo"}:
        acceptance = ()
    return RunLaunchSpec(
        config=state.config if Path(state.config).expanduser().exists() else None,
        workspace=state.workspace,
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
            state.workspace = str(path)
            _print_good(f"Workspace · {path.resolve()}")
    elif command == "/resume":
        _resume(state, argument.strip())
    elif command == "/inspect":
        _inspect(argument.strip())
    elif command == "/permissions":
        _permissions(state)
    elif command == "/new":
        state.last_run = None
        _emit(("class:accent", "  ── "), ("class:muted", "new conversation"))
    elif command == "/clear":
        os.system("cls" if os.name == "nt" else "clear")
        _banner(state)
    else:
        _print_error(f"Unknown command: {command}. Use /help.")
    print()
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verified-State Harness conversational terminal UI")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--config", default="harness.toml")
    parser.add_argument("--mode", choices=["software", "hackathon", "ctf", "demo"], default="software")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    state = AppState(workspace=args.workspace, config=args.config, mode=args.mode)
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
            raw = session.prompt(FormattedText([("class:prompt", "❯ ")]))
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
        spec = _task_spec(state, text)
        if state.mode in {"software", "hackathon"} and not spec.acceptance_commands:
            _emit(("class:warn", "  ! "), ("class:muted", "No acceptance command auto-detected; completion may remain unaccepted. Use /accept <command>."))
        _run_spec(state, spec)


if __name__ == "__main__":
    raise SystemExit(main())
