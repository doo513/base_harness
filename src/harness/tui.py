from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from threading import Thread
from time import sleep
from typing import Any, Iterable, TextIO

from harness.skill_actions import (
    PROVIDER_PRESETS,
    SkillActionError,
    configure_mcp,
    configure_provider,
    search_mcp_registry,
)
from harness.skill_catalog import SkillCatalog, SkillError


@dataclass(frozen=True)
class RunLaunchSpec:
    """Declarative TUI launch request translated to the existing CLI boundary."""

    config: str | None = None
    workspace: str = "."
    run_dir: str = "./run"
    profile: str = "software"
    goal: str | None = None
    acceptance_commands: tuple[str, ...] = ()
    max_steps: int = 30
    task_revision: str | None = None
    model_revision: str | None = None
    execution_backend: str = "local"
    strict_layout: bool = False
    strict_tool_isolation: bool = False
    network_policy: str = "allow"
    require_sealed_oracle: bool = False
    sealed_oracle_root: str | None = None
    require_oracle_isolation: bool = False
    require_complete_provenance: bool = False
    resume: bool = False

    def command(self, *, python_executable: str | None = None) -> list[str]:
        python = python_executable or sys.executable
        argv = [python, "-m", "harness.cli"]
        if self.config:
            argv += ["--config", self.config]
        argv += [
            "--profile", self.profile,
            "--workspace", self.workspace,
            "--run-dir", self.run_dir,
            "--max-steps", str(self.max_steps),
            "--execution-backend", self.execution_backend,
            "--network-policy", self.network_policy,
        ]
        if self.goal:
            argv += ["--goal", self.goal]
        for command in self.acceptance_commands:
            if command:
                argv += ["--accept-command", command]
        if self.task_revision:
            argv += ["--task-revision", self.task_revision]
        if self.model_revision:
            argv += ["--model-revision", self.model_revision]
        if self.sealed_oracle_root:
            argv += ["--sealed-oracle-root", self.sealed_oracle_root]
        argv.append("--strict-layout" if self.strict_layout else "--no-strict-layout")
        argv.append("--strict-tool-isolation" if self.strict_tool_isolation else "--no-strict-tool-isolation")
        argv.append("--require-sealed-oracle" if self.require_sealed_oracle else "--no-require-sealed-oracle")
        if self.require_oracle_isolation:
            argv.append("--require-oracle-isolation")
        if self.require_complete_provenance:
            argv.append("--require-complete-provenance")
        if self.resume:
            argv.append("--resume")
        return argv


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_jsonl(path: Path, *, limit: int = 8) -> list[dict[str, Any]]:
    rows: deque[dict[str, Any]] = deque(maxlen=max(1, limit))
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except (OSError, UnicodeError):
        return []
    return list(rows)


@dataclass
class RunView:
    run_dir: Path | str
    metrics: dict[str, Any] = field(default_factory=dict)
    last_events: list[dict[str, Any]] = field(default_factory=list)
    last_tool_calls: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.run_dir = Path(self.run_dir)

    def refresh(self) -> "RunView":
        self.metrics = _read_json_object(self.run_dir / "metrics.json")
        self.last_events = _read_jsonl(self.run_dir / "events.jsonl")
        self.last_tool_calls = _read_jsonl(self.run_dir / "tool_calls.jsonl")
        return self

    @staticmethod
    def _compact(row: dict[str, Any], keys: Iterable[str]) -> str:
        parts = [f"{key}={row[key]}" for key in keys if key in row]
        return " ".join(parts) if parts else json.dumps(row, ensure_ascii=False, sort_keys=True)

    def summary_lines(self) -> list[str]:
        lines = [f"run_dir={self.run_dir.resolve()}"]
        if self.metrics:
            metric_keys = (
                "completed", "steps", "tool_calls", "failures",
                "progress_events", "recovery_transitions",
            )
            lines.append("metrics: " + self._compact(self.metrics, metric_keys))
        else:
            lines.append("metrics: unavailable")

        lines.append("events:")
        if self.last_events:
            lines.extend(
                "  " + self._compact(row, ("step", "kind", "reason"))
                for row in self.last_events
            )
        else:
            lines.append("  (none)")

        lines.append("tool_calls:")
        if self.last_tool_calls:
            lines.extend(
                "  " + self._compact(row, ("step", "tool", "ok", "permission"))
                for row in self.last_tool_calls
            )
        else:
            lines.append("  (none)")
        return lines


def _prompt(label: str, default: str | None = None, *, required: bool = False) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print("A value is required.")


def _prompt_bool(label: str, default: bool = False) -> bool:
    marker = "Y/n" if default else "y/N"
    while True:
        value = input(f"{label} [{marker}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes", "1", "true"}:
            return True
        if value in {"n", "no", "0", "false"}:
            return False
        print("Enter y or n.")


def _prompt_choice(label: str, choices: tuple[str, ...], default: str) -> str:
    while True:
        value = _prompt(f"{label} ({'/'.join(choices)})", default)
        if value in choices:
            return value
        print("Choose one of: " + ", ".join(choices))


def _prompt_acceptance_commands() -> tuple[str, ...]:
    print("Acceptance commands: enter one per line; blank line finishes.")
    values: list[str] = []
    while True:
        value = input("accept> ").strip()
        if not value:
            return tuple(values)
        values.append(value)


def _positive_int(label: str, default: str) -> int:
    raw = _prompt(label, default)
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError
        return value
    except ValueError as exc:
        raise SystemExit(f"{label} must be a positive integer.") from exc


def _default_run_root() -> Path:
    """Return the user-local Harness state root used by TUI-created runs."""
    explicit = os.environ.get("HARNESS_RUN_ROOT")
    if explicit:
        return Path(explicit).expanduser()
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "base_harness" / "runs"
        return Path.home() / "AppData" / "Local" / "base_harness" / "runs"
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home).expanduser() / "base_harness" / "runs"
    return Path.home() / ".local" / "state" / "base_harness" / "runs"


def _default_new_run_dir(root: str | Path | None = None) -> str:
    """Return a fresh run directory outside the project by default."""
    base = Path(root).expanduser() if root is not None else _default_run_root()
    stem = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = base / stem
    suffix = 2
    while candidate.exists():
        candidate = base / f"{stem}-{suffix}"
        suffix += 1
    return str(candidate)


def _run_dir_is_nonempty(path: str | Path) -> bool:
    candidate = Path(path).expanduser()
    if not candidate.exists():
        return False
    if not candidate.is_dir():
        return True
    try:
        return next(candidate.iterdir(), None) is not None
    except OSError:
        return True


def _prompt_fresh_run_dir() -> str:
    default = _default_new_run_dir()
    while True:
        value = _prompt("Run directory", default, required=True)
        if not _run_dir_is_nonempty(value):
            return value
        print("Run directory is not empty. Choose a fresh directory, or use Resume for an existing run.")
        default = _default_new_run_dir()


def _run_connect_provider(config_path: str) -> int:
    print("\nSkill: connect-provider")
    choices = tuple(PROVIDER_PRESETS)
    preset_name = _prompt_choice("Provider", choices, "gemini")
    preset = PROVIDER_PRESETS[preset_name]
    alias = _prompt("Model alias", preset_name, required=True)
    model_default = {
        "gemini": "gemini-3.5-flash",
        "openai": "gpt-5-mini",
        "ollama": "qwen2.5-coder:3b",
    }.get(preset_name)
    model = _prompt("Model", model_default, required=True)
    endpoint = _prompt("Endpoint", preset.endpoint) if preset.endpoint else _prompt("Endpoint", required=True)
    secret_env: str | None = None
    if preset.default_secret_env:
        secret_env = _prompt("API-key environment variable", preset.default_secret_env, required=True)
    make_default = _prompt_bool("Use this as default model", True)
    try:
        path = configure_provider(
            config_path,
            alias=alias,
            preset=preset_name,
            model=model,
            endpoint=endpoint,
            secret_env=secret_env,
            make_default=make_default,
        )
    except SkillActionError as exc:
        print(f"Connection configuration failed: {exc}")
        return 2
    print(f"Updated: {path.resolve()}")
    if secret_env:
        status = "available" if os.environ.get(secret_env) else "not present in this process"
        print(f"Secret reference: env:{secret_env} ({status})")
        print("The raw API key was not written to the TOML file.")
    return 0


def _prompt_env_refs() -> dict[str, str]:
    print("MCP environment mappings: TARGET_ENV=SOURCE_ENV; blank line finishes.")
    refs: dict[str, str] = {}
    while True:
        raw = input("env> ").strip()
        if not raw:
            return refs
        if "=" not in raw:
            print("Use TARGET_ENV=SOURCE_ENV")
            continue
        target, source = (item.strip() for item in raw.split("=", 1))
        if not target or not source:
            print("Both names are required.")
            continue
        refs[target] = source


def _run_configure_mcp(config_path: str) -> int:
    print("\nSkill: configure-mcp")
    print("Transport: stdio (current mcp-gateway-v1 runtime)")
    name = _prompt("MCP name", required=True)
    command_line = _prompt("Command argv", required=True)
    try:
        argv = tuple(shlex.split(command_line, posix=os.name != "nt"))
    except ValueError as exc:
        print(f"Invalid command argv: {exc}")
        return 2
    env_refs = _prompt_env_refs()
    try:
        path = configure_mcp(
            config_path,
            name=name,
            transport="stdio",
            command=argv,
            env_refs=env_refs,
        )
    except SkillActionError as exc:
        print(f"MCP configuration failed: {exc}")
        return 2
    print(f"Updated: {path.resolve()}")
    print("Configuration does not install or trust the MCP server; runtime permission policy still applies.")
    return 0


def _run_mcp_search() -> int:
    print("\nSkill: mcp-search")
    query = _prompt("Search MCP Registry", required=True)
    try:
        items = search_mcp_registry(query)
    except SkillActionError as exc:
        print(str(exc))
        return 2
    if not items:
        print("No matching MCP servers found.")
        return 0
    for index, item in enumerate(items, 1):
        version = f" {item.version}" if item.version else ""
        print(f"\n{index}. {item.name}{version}")
        if item.description:
            print("   " + item.description)
        if item.repository_url:
            print("   repository: " + item.repository_url)
        for hint in item.package_hints:
            print("   " + hint)
    print("\nSearch is discovery-only. Review a server before configuring it.")
    return 0


def _skill_catalog(workspace: str | Path | None = None) -> SkillCatalog:
    return SkillCatalog.default(workspace="." if workspace is None else workspace)


def _render_skill_list(query: str = "", *, workspace: str | Path | None = None) -> int:
    try:
        skills = _skill_catalog(workspace).search(query)
    except (OSError, UnicodeError, SkillError) as exc:
        print(f"Skill discovery failed: {exc}")
        return 2
    if not skills:
        print("No matching skills.")
        return 0
    for skill in skills:
        action = f" action={skill.action}" if skill.action else ""
        print(f"{skill.name:20} [{skill.category}]{action}")
        print("  " + skill.description)
    return 0


def _run_skill(name: str, *, config_path: str) -> int:
    try:
        skill = _skill_catalog().get(name)
    except SkillError as exc:
        print(str(exc))
        return 2
    action = skill.action
    if action == "connect-provider":
        return _run_connect_provider(config_path)
    if action == "mcp-search":
        return _run_mcp_search()
    if action == "configure-mcp":
        return _run_configure_mcp(config_path)

    print(f"# {skill.name}\n\n{skill.body}")
    print("\nThis skill has no built-in executable action; it was displayed only.")
    return 0


def _maybe_bootstrap_config(config: str) -> None:
    if Path(config).expanduser().exists():
        return
    print(f"Config does not exist: {config}")
    if _prompt_bool("Run the connect-provider skill now", True):
        rc = _run_connect_provider(config)
        if rc != 0:
            raise SystemExit(rc)


def interactive_spec(*, resume: bool) -> RunLaunchSpec:
    if resume:
        print("Verified-State Harness — Resume")
        config = _prompt("Config TOML", "harness.toml")
        workspace = _prompt("Workspace", ".", required=True)
        run_dir = _prompt("Run directory", "./run", required=True)
        profile = _prompt_choice("Mode", ("software", "hackathon", "ctf", "demo"), "software")
        goal = ""
    else:
        print("Verified-State Harness — New Task")
        workspace = _prompt("Workspace", ".", required=True)
        goal = _prompt("Task / problem", required=True)
        profile = _prompt_choice("Mode", ("software", "hackathon", "ctf", "demo"), "software")
        config = _prompt("Config TOML", "harness.toml")
        _maybe_bootstrap_config(config)
        run_dir = _prompt_fresh_run_dir()

    acceptance = () if profile in {"ctf", "demo"} else _prompt_acceptance_commands()
    advanced = _prompt_bool("Advanced execution settings", False)
    max_steps = 30
    execution_backend = "local"
    network_policy = "allow"
    strict_layout = False
    strict_tool_isolation = False
    require_sealed_oracle = False
    sealed_oracle_root = ""
    require_oracle_isolation = False

    if advanced:
        max_steps = _positive_int("Max steps", "30")
        execution_backend = _prompt_choice("Execution backend", ("local", "linux-namespace"), "local")
        network_policy = _prompt_choice("Network policy", ("allow", "deny"), "allow")
        strict_layout = _prompt_bool("Strict workspace/run layout", False)
        strict_tool_isolation = _prompt_bool("Strict tool isolation", False)
        require_sealed_oracle = _prompt_bool("Require sealed completion oracle", False)
        if require_sealed_oracle:
            sealed_oracle_root = _prompt("Sealed oracle root", required=True)
            require_oracle_isolation = _prompt_bool("Require oracle isolation", False)

    return RunLaunchSpec(
        config=config or None,
        workspace=workspace,
        run_dir=run_dir,
        profile=profile,
        goal=goal or None,
        acceptance_commands=acceptance,
        max_steps=max_steps,
        execution_backend=execution_backend,
        strict_layout=strict_layout,
        strict_tool_isolation=strict_tool_isolation,
        network_policy=network_policy,
        require_sealed_oracle=require_sealed_oracle,
        sealed_oracle_root=sealed_oracle_root or None,
        require_oracle_isolation=require_oracle_isolation,
        resume=resume,
    )


def _drain_stream(stream: TextIO | None, sink: deque[str]) -> None:
    if stream is None:
        return
    try:
        for line in stream:
            sink.append(line.rstrip())
    finally:
        stream.close()


def _render_live(view: RunView, stdout_lines: deque[str], stderr_lines: deque[str]) -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="")
    print("\n".join(view.refresh().summary_lines()))
    if stdout_lines:
        print("stdout:")
        for line in stdout_lines:
            print("  " + line)
    if stderr_lines:
        print("stderr:")
        for line in stderr_lines:
            print("  " + line)


def launch_and_monitor(spec: RunLaunchSpec) -> int:
    command = spec.command()
    stdout_lines: deque[str] = deque(maxlen=8)
    stderr_lines: deque[str] = deque(maxlen=8)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        shell=False,
    )
    threads = [
        Thread(target=_drain_stream, args=(process.stdout, stdout_lines), daemon=True),
        Thread(target=_drain_stream, args=(process.stderr, stderr_lines), daemon=True),
    ]
    for thread in threads:
        thread.start()

    view = RunView(spec.run_dir)
    try:
        while process.poll() is None:
            _render_live(view, stdout_lines, stderr_lines)
            sleep(0.75)
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    finally:
        for thread in threads:
            thread.join(timeout=1)
        _render_live(view, stdout_lines, stderr_lines)
    return int(process.returncode or 0)


def _home() -> int:
    while True:
        print("\nVerified-State Harness")
        print("  1. New task")
        print("  2. Skills / connections")
        print("  3. Resume run")
        print("  4. Inspect run")
        print("  q. Quit")
        choice = input("> ").strip().lower()
        if choice in {"q", "quit", "exit"}:
            return 0
        if choice == "1":
            return launch_and_monitor(interactive_spec(resume=False))
        if choice == "2":
            _render_skill_list()
            name = _prompt("Skill name (blank to return)")
            if name:
                config = _prompt("Config TOML", "harness.toml")
                _run_skill(name, config_path=config)
            continue
        if choice == "3":
            return launch_and_monitor(interactive_spec(resume=True))
        if choice == "4":
            run_dir = _prompt("Run directory", required=True)
            print("\n".join(RunView(run_dir).refresh().summary_lines()))
            continue
        print("Choose 1, 2, 3, 4 or q.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verified-State Harness task-oriented terminal UI")
    sub = parser.add_subparsers(dest="command", required=False)
    sub.add_parser("new", help="Launch a task-first interactive run")
    sub.add_parser("resume", help="Interactively resume an existing run")
    inspect = sub.add_parser("inspect", help="Inspect persisted run state without executing it")
    inspect.add_argument("run_dir")
    skills = sub.add_parser("skills", help="List/search available SKILL.md capabilities")
    skills.add_argument("query", nargs="?", default="")
    skill = sub.add_parser("skill", help="Run a built-in skill action or display a custom skill")
    skill.add_argument("name")
    skill.add_argument("--config", default="harness.toml")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command is None:
        return _home()
    if args.command == "inspect":
        print("\n".join(RunView(args.run_dir).refresh().summary_lines()))
        return 0
    if args.command == "skills":
        return _render_skill_list(args.query)
    if args.command == "skill":
        return _run_skill(args.name, config_path=args.config)
    spec = interactive_spec(resume=args.command == "resume")
    return launch_and_monitor(spec)


if __name__ == "__main__":
    raise SystemExit(main())
