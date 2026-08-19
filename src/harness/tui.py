from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
from time import sleep
from typing import Any, Iterable, TextIO


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


def interactive_spec(*, resume: bool) -> RunLaunchSpec:
    print("Verified-State Harness — " + ("resume run" if resume else "new run"))
    config = _prompt("Config TOML", "harness.toml")
    workspace = _prompt("Workspace", ".", required=True)
    run_dir = _prompt("Run directory", "./run", required=True)
    profile = _prompt_choice("Profile", ("software", "hackathon", "ctf", "demo"), "software")
    goal = "" if resume else _prompt("Goal", required=True)
    acceptance = () if profile in {"ctf", "demo"} else _prompt_acceptance_commands()
    max_steps_raw = _prompt("Max steps", "30")
    try:
        max_steps = int(max_steps_raw)
        if max_steps <= 0:
            raise ValueError
    except ValueError as exc:
        raise SystemExit("Max steps must be a positive integer.") from exc

    execution_backend = _prompt_choice("Execution backend", ("local", "linux-namespace"), "local")
    network_policy = _prompt_choice("Network policy", ("allow", "deny"), "allow")
    strict_layout = _prompt_bool("Strict workspace/run layout", False)
    strict_tool_isolation = _prompt_bool("Strict tool isolation", False)
    require_sealed_oracle = _prompt_bool("Require sealed completion oracle", False)
    sealed_oracle_root = ""
    require_oracle_isolation = False
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verified-State Harness thin terminal UI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("new", help="Interactively launch a new run")
    sub.add_parser("resume", help="Interactively resume an existing run")
    inspect = sub.add_parser("inspect", help="Inspect persisted run state without executing it")
    inspect.add_argument("run_dir")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "inspect":
        print("\n".join(RunView(args.run_dir).refresh().summary_lines()))
        return 0
    spec = interactive_spec(resume=args.command == "resume")
    return launch_and_monitor(spec)


if __name__ == "__main__":
    raise SystemExit(main())
