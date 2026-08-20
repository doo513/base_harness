from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field
from getpass import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from threading import Thread
from time import sleep
import tomllib

from harness.config import ConfigError, load_harness_config
from harness.skill_actions import PROVIDER_PRESETS, SkillActionError, configure_provider
from harness.tui import (
    RunLaunchSpec,
    RunView,
    _default_new_run_dir,
    _render_skill_list,
    _run_configure_mcp,
    _run_mcp_search,
)


RESET = "\033[0m"
DIM = "\033[2m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
GRAY = "\033[90m"


def _tty() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def _clear() -> None:
    if _tty():
        print("\033[2J\033[H", end="")


def _clip(text: object, width: int) -> str:
    value = str(text)
    if width <= 1:
        return value[:width]
    if len(value) <= width:
        return value
    return value[: max(0, width - 1)] + "…"


def _line(text: str, width: int) -> str:
    inner = max(1, width - 2)
    return "│" + _clip(text, inner).ljust(inner) + "│"


def _rule(width: int, left: str = "├", right: str = "┤") -> str:
    return left + "─" * max(1, width - 2) + right


def _box(lines: list[str], *, title: str = "", width: int | None = None) -> str:
    terminal = shutil.get_terminal_size((100, 30)).columns
    width = max(60, min(width or terminal, 120))
    label = f" {title} " if title else ""
    top_fill = max(0, width - 2 - len(label))
    output = ["┌" + label + "─" * top_fill + "┐"]
    output.extend(_line(item, width) for item in lines)
    output.append("└" + "─" * max(1, width - 2) + "┘")
    return "\n".join(output)


def _config_data(path: str | Path) -> dict:
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
        key = secret[4:]
        return default, model_id, bool(os.environ.get(key))
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


@dataclass
class AppState:
    workspace: str = "."
    config: str = "harness.toml"
    mode: str = "software"
    acceptance: tuple[str, ...] = ()
    session_env: dict[str, str] = field(default_factory=dict, repr=False)
    messages: deque[str] = field(default_factory=lambda: deque(maxlen=12))
    last_run: str | None = None

    def add(self, message: str) -> None:
        self.messages.append(message)


def _render_home(state: AppState) -> None:
    _clear()
    width = max(70, min(shutil.get_terminal_size((100, 30)).columns, 120))
    alias, model_id, credential_ready = _model_status(state.config)
    if alias != "not connected":
        data = _config_data(state.config)
        model = data.get("models", {}).get(alias, {}) if isinstance(data.get("models"), dict) else {}
        secret = model.get("api_key") if isinstance(model, dict) else None
        if isinstance(secret, str) and secret.startswith("env:") and secret[4:] in state.session_env:
            credential_ready = True
    status = f"{GREEN}ready{RESET}" if credential_ready else f"{YELLOW}connect model{RESET}"
    header = f"{BOLD}base_harness{RESET}  {DIM}{_clip(Path(state.workspace).resolve(), 55)}{RESET}"
    right = f"{state.mode} · {alias}/{model_id} · {status}"
    print("┌" + "─" * (width - 2) + "┐")
    print(_line(header, width))
    print(_line(right, width))
    print(_rule(width))
    body = list(state.messages)
    if not body:
        body = [
            "",
            f"  {BOLD}What do you want to build or solve?{RESET}",
            "  Type a task and press Enter.",
            "",
            f"  {DIM}/connect  /models  /mcp  /skills  /mode  /accept  /help{RESET}",
        ]
    for item in body[-12:]:
        print(_line("  " + item, width))
    for _ in range(max(1, 12 - len(body))):
        print(_line("", width))
    print(_rule(width))
    accept = ", ".join(state.acceptance) if state.acceptance else "auto-detect"
    print(_line(f"  acceptance: {accept}", width))
    print("└" + "─" * (width - 2) + "┘")
    print(f"{CYAN}›{RESET} ", end="", flush=True)


def _choose(label: str, items: list[str]) -> int | None:
    print()
    print(_box([f"{i + 1}. {item}" for i, item in enumerate(items)] + ["", "Enter to cancel"], title=label))
    raw = input("Select: ").strip()
    if not raw:
        return None
    try:
        value = int(raw) - 1
    except ValueError:
        return None
    return value if 0 <= value < len(items) else None


def _connect(state: AppState) -> None:
    names = list(PROVIDER_PRESETS)
    index = _choose("Connect provider", names)
    if index is None:
        return
    preset_name = names[index]
    preset = PROVIDER_PRESETS[preset_name]
    data = _config_data(state.config)
    existing = data.get("models") if isinstance(data.get("models"), dict) else {}

    alias = input(f"Alias [{preset_name}]: ").strip() or preset_name
    model_defaults = {
        "gemini": "gemini-3.5-flash",
        "openai": "gpt-5-mini",
        "ollama": "qwen2.5-coder:3b",
    }
    default_model = model_defaults.get(preset_name, "")
    model = input(f"Model{f' [{default_model}]' if default_model else ''}: ").strip() or default_model
    if not model:
        state.add("Connection cancelled: model is required.")
        return
    endpoint = preset.endpoint or input("Endpoint: ").strip()
    if not endpoint:
        state.add("Connection cancelled: endpoint is required.")
        return

    secret_env = preset.default_secret_env
    if secret_env:
        print()
        print(_box([
            f"1. Use existing {secret_env} environment variable",
            "2. Paste API key for this TUI session only",
            "3. Reference another environment variable",
            "",
            "The raw key is never written to harness.toml.",
        ], title="Credential"))
        method = input("Select [2]: ").strip() or "2"
        if method == "2":
            key = getpass("API key: ").strip()
            if not key:
                state.add("Connection cancelled: empty API key.")
                return
            state.session_env[secret_env] = key
        elif method == "3":
            secret_env = input(f"Environment variable [{secret_env}]: ").strip() or secret_env
        elif method != "1":
            state.add("Connection cancelled.")
            return

    try:
        if alias in existing:
            _set_default_model(state.config, alias)
        else:
            configure_provider(
                state.config,
                alias=alias,
                preset=preset_name,
                model=model,
                endpoint=endpoint,
                secret_env=secret_env,
                make_default=True,
            )
    except (SkillActionError, ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        state.add(f"Connection failed: {exc}")
        return
    state.add(f"Connected {alias} → {model}.")


def _models(state: AppState) -> None:
    data = _config_data(state.config)
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    if not models:
        state.add("No models configured. Use /connect.")
        return
    default = data.get("default_model")
    aliases = list(models)
    labels = []
    for alias in aliases:
        item = models[alias] if isinstance(models[alias], dict) else {}
        mark = "●" if alias == default else " "
        labels.append(f"{mark} {alias:18} {item.get('model', '-')}")
    index = _choose("Models", labels)
    if index is None:
        return
    try:
        _set_default_model(state.config, aliases[index])
    except (ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        state.add(f"Model selection failed: {exc}")
        return
    state.add(f"Model switched to {aliases[index]}.")


def _mode(state: AppState) -> None:
    choices = ["software", "hackathon", "ctf", "demo"]
    index = _choose("Mode", choices)
    if index is not None:
        state.mode = choices[index]
        state.add(f"Mode: {state.mode}")


def _accept(state: AppState, argument: str = "") -> None:
    if argument.strip():
        state.acceptance = (argument.strip(),)
        state.add("Acceptance command updated.")
        return
    current = ", ".join(state.acceptance) if state.acceptance else "auto-detect"
    value = input(f"Acceptance command [{current}]: ").strip()
    if value:
        state.acceptance = (value,)
        state.add("Acceptance command updated.")


def _mcp(state: AppState) -> None:
    index = _choose("MCP", ["Search official MCP Registry", "Configure reviewed stdio MCP"])
    if index == 0:
        _run_mcp_search()
        input("\nEnter to return...")
    elif index == 1:
        _run_configure_mcp(state.config)
        input("\nEnter to return...")


def _help(state: AppState) -> None:
    state.messages.clear()
    for line in (
        "/connect            connect provider; key may stay in this TUI session only",
        "/models             choose configured model",
        "/mcp                search/configure MCP",
        "/skills [query]     list SKILL.md capabilities",
        "/mode               software / hackathon / ctf / demo",
        "/accept <command>   set fixed completion command",
        "/workspace <path>   change project folder",
        "/resume <run-dir>   resume persisted run",
        "/inspect <run-dir>  show persisted run state",
        "/new                clear this UI session",
        "/exit               quit",
    ):
        state.add(line)


def _process_env(state: AppState) -> dict[str, str]:
    result = dict(os.environ)
    result.update(state.session_env)
    return result


def _render_running(state: AppState, view: RunView, stdout: deque[str], stderr: deque[str]) -> None:
    _clear()
    width = max(70, min(shutil.get_terminal_size((100, 30)).columns, 120))
    view.refresh()
    metrics = view.metrics
    summary = (
        f"steps {metrics.get('steps', 0)}  ·  tools {metrics.get('tool_calls', 0)}  ·  "
        f"failures {metrics.get('failures', 0)}  ·  recovery {metrics.get('recovery_transitions', 0)}"
    )
    print(_box([
        f"workspace  {Path(state.workspace).resolve()}",
        f"run        {view.run_dir.resolve()}",
        f"mode       {state.mode}",
        summary,
    ], title="base_harness · running", width=width))
    print()
    print(_box([
        *(f"event  {row.get('kind', '')} {row.get('reason', '')}" for row in view.last_events[-5:]),
        *(f"tool   {row.get('tool', '')} ok={row.get('ok', '')}" for row in view.last_tool_calls[-4:]),
        *(f"out    {line}" for line in list(stdout)[-4:]),
        *(f"err    {line}" for line in list(stderr)[-3:]),
    ] or ["waiting for runtime events..."], title="activity", width=width))
    print(f"\n{DIM}Ctrl+C stops the current run.{RESET}")


def _drain(stream, sink: deque[str]) -> None:
    if stream is None:
        return
    try:
        for line in stream:
            sink.append(line.rstrip())
    finally:
        stream.close()


def _run_spec(state: AppState, spec: RunLaunchSpec) -> int:
    stdout: deque[str] = deque(maxlen=12)
    stderr: deque[str] = deque(maxlen=12)
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
    view = RunView(spec.run_dir)
    try:
        while process.poll() is None:
            _render_running(state, view, stdout, stderr)
            sleep(0.5)
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=5)
    finally:
        for thread in threads:
            thread.join(timeout=1)
        _render_running(state, view, stdout, stderr)
    state.last_run = spec.run_dir
    return int(process.returncode or 0)


def _ensure_ready(state: AppState) -> bool:
    data = _config_data(state.config)
    default = data.get("default_model")
    models = data.get("models") if isinstance(data.get("models"), dict) else {}
    if not isinstance(default, str) or default not in models:
        _connect(state)
        data = _config_data(state.config)
        default = data.get("default_model")
        models = data.get("models") if isinstance(data.get("models"), dict) else {}
    return isinstance(default, str) and default in models


def _run_task(state: AppState, task: str) -> None:
    if not _ensure_ready(state):
        state.add("Task not started: connect a model first.")
        return
    acceptance = state.acceptance
    if state.mode in {"software", "hackathon"} and not acceptance:
        acceptance = _detect_acceptance(state.workspace)
        if not acceptance:
            value = input("Acceptance command required for verified completion: ").strip()
            if not value:
                state.add("Task not started: software/hackathon mode needs an acceptance command.")
                return
            acceptance = (value,)
    run_dir = _default_new_run_dir()
    state.add(f"You: {task}")
    state.add(f"Running → {run_dir}")
    spec = RunLaunchSpec(
        config=state.config,
        workspace=state.workspace,
        run_dir=run_dir,
        profile=state.mode,
        goal=task,
        acceptance_commands=acceptance,
        max_steps=30,
    )
    rc = _run_spec(state, spec)
    state.add(f"Run finished rc={rc} · {run_dir}")


def _resume(state: AppState, run_dir: str) -> None:
    if not run_dir:
        run_dir = input("Run directory: ").strip()
    if not run_dir:
        return
    spec = RunLaunchSpec(
        config=state.config,
        workspace=state.workspace,
        run_dir=run_dir,
        profile=state.mode,
        max_steps=30,
        resume=True,
    )
    rc = _run_spec(state, spec)
    state.add(f"Resume finished rc={rc} · {run_dir}")


def _command(state: AppState, raw: str) -> bool:
    command, _, argument = raw.partition(" ")
    command = command.lower()
    argument = argument.strip()
    if command in {"/exit", "/quit", "/q"}:
        return False
    if command == "/connect":
        _connect(state)
    elif command in {"/models", "/model"}:
        _models(state)
    elif command == "/mcp":
        _mcp(state)
    elif command == "/skills":
        _clear()
        _render_skill_list(argument, workspace=state.workspace)
        input("\nEnter to return...")
    elif command == "/mode":
        _mode(state)
    elif command == "/accept":
        _accept(state, argument)
    elif command == "/workspace":
        value = argument or input("Workspace: ").strip()
        if value:
            state.workspace = value
            state.add(f"Workspace: {Path(value).expanduser().resolve()}")
    elif command == "/resume":
        _resume(state, argument)
    elif command == "/inspect":
        run_dir = argument or state.last_run or input("Run directory: ").strip()
        if run_dir:
            _clear()
            print("\n".join(RunView(run_dir).refresh().summary_lines()))
            input("\nEnter to return...")
    elif command == "/new":
        state.messages.clear()
        state.last_run = None
    elif command == "/help":
        _help(state)
    else:
        state.add(f"Unknown command: {command}. Use /help.")
    return True


def run_app(*, workspace: str = ".", config: str = "harness.toml", mode: str = "software") -> int:
    state = AppState(workspace=workspace, config=config, mode=mode)
    while True:
        _render_home(state)
        try:
            raw = input().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not raw:
            continue
        if raw.startswith("/"):
            if not _command(state, raw):
                return 0
            continue
        _run_task(state, raw)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verified-State Harness visual task console")
    parser.add_argument("workspace", nargs="?", default=".", help="project workspace (default: current directory)")
    parser.add_argument("--config", default="harness.toml")
    parser.add_argument("--mode", choices=["software", "hackathon", "ctf", "demo"], default="software")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return run_app(workspace=args.workspace, config=args.config, mode=args.mode)


if __name__ == "__main__":
    raise SystemExit(main())
