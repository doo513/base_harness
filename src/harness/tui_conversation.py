from __future__ import annotations

import argparse
from collections import deque
import json
import os
from pathlib import Path
import subprocess
from threading import Thread
from time import sleep
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import InMemoryHistory

from harness.task_intake import analyze_task_input
from harness.tui import RunLaunchSpec, RunView, _default_new_run_dir
from harness import tui_visual as legacy


_HIDDEN_EVENTS = {
    "state.snapshot",
    "run.start",
    "run.end",
    "step.transition",
}


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("payload")
    return value if isinstance(value, dict) else {}


def _friendly_event(row: dict[str, Any]) -> None:
    kind = str(row.get("kind") or "event")
    if kind in _HIDDEN_EVENTS:
        return
    payload = _payload(row)

    if kind == "agent.plan.replaced":
        objective = str(payload.get("objective") or "work plan updated")
        legacy._emit(("class:accent", "  ◇ Plan  "), ("class:assistant", objective))
        return
    if kind == "agent.task.updated":
        task_id = str(payload.get("task_id") or "task")
        legacy._emit(("class:muted", "  · Check "), ("class:assistant", task_id))
        return
    if kind == "tool.result":
        return  # tool_calls.jsonl is rendered separately with clearer labels.
    if kind == "verification":
        claim = str(payload.get("claim") or "claim")
        assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
        accepted = bool(assessment.get("accepted"))
        cls = "class:good" if accepted else "class:warn"
        icon = "✓" if accepted else "!"
        legacy._emit((cls, f"  {icon} Verify "), ("class:assistant", claim))
        return
    if kind == "completion.oracle":
        accepted = bool(payload.get("accepted"))
        reason = str(payload.get("reason") or "completion check")
        cls = "class:good" if accepted else "class:warn"
        icon = "✓" if accepted else "!"
        legacy._emit((cls, f"  {icon} Final  "), ("class:assistant", reason))
        return
    if kind == "completion.accepted":
        legacy._emit(("class:good", "  ✓ Done   "), ("class:assistant", str(payload.get("reason") or "accepted")))
        return
    if kind == "failure":
        message = str(payload.get("message") or payload.get("reason") or "runtime failure")
        legacy._emit(("class:bad", "  ✕ Issue  "), ("class:assistant", message))
        return
    if kind.startswith("recovery"):
        transition = payload.get("transition") if isinstance(payload.get("transition"), dict) else {}
        action = str(transition.get("action") or payload.get("recommended_recovery") or "retrying safely")
        legacy._emit(("class:warn", "  ↻ Retry  "), ("class:assistant", action))
        return
    if kind.startswith("strategy"):
        legacy._emit(("class:warn", "  ↻ Adjust "), ("class:assistant", kind))
        return


def _friendly_tool(row: dict[str, Any]) -> None:
    tool = str(row.get("tool") or "tool")
    ok = row.get("ok")
    if ok is False:
        legacy._emit(("class:bad", "  ✕ Tool   "), ("class:assistant", tool), ("class:muted", " · failed"))
    else:
        legacy._emit(("class:tool", "  ● Tool   "), ("class:assistant", tool))


def _drain(stream, sink: deque[str]) -> None:
    if stream is None:
        return
    try:
        for line in stream:
            sink.append(line.rstrip())
    finally:
        stream.close()


def _read_final_result(run_dir: str | Path) -> dict[str, Any]:
    path = Path(run_dir) / "final_result.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _report_preview(artifact: dict[str, Any]) -> list[str]:
    absolute = artifact.get("absolute_path")
    if not isinstance(absolute, str) or not artifact.get("readable"):
        return []
    try:
        text = Path(absolute).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[:4]


def _render_final_result(run_dir: str | Path) -> None:
    result = _read_final_result(run_dir)
    if not result:
        return
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    facts = result.get("verified_facts") if isinstance(result.get("verified_facts"), dict) else {}
    artifact = result.get("artifact") if isinstance(result.get("artifact"), dict) else None

    if result.get("completed"):
        legacy._emit(("class:good", "\n  ✓ Finished"))
    else:
        legacy._emit(("class:warn", "\n  ◇ Stopped before verified completion"))

    legacy._emit(
        ("class:muted", "  Evidence  "),
        ("class:assistant", f"{evidence.get('workspace_observations', 0)} workspace observations · {facts.get('count', 0)} verified facts"),
    )
    if artifact and artifact.get("exists"):
        path = str(artifact.get("absolute_path") or artifact.get("path") or "")
        legacy._emit(("class:muted", "  Output    "), ("class:good", path))
        preview = _report_preview(artifact)
        if preview:
            legacy._emit(("class:muted", "  Preview"))
            for line in preview:
                legacy._emit(("class:muted", "    │ "), ("class:assistant", line[:140]))

    failures = result.get("last_failures") if isinstance(result.get("last_failures"), list) else []
    if not result.get("completed") and failures:
        last = failures[-1] if isinstance(failures[-1], dict) else {}
        message = str(last.get("message") or last.get("kind") or "run did not complete")
        legacy._emit(("class:muted", "  Last issue "), ("class:warn", message))
    legacy._emit(("class:muted", "  Run files  "), ("class:assistant", str(Path(run_dir).resolve())))
    print()


def _run_spec(state: legacy.AppState, spec: RunLaunchSpec) -> int:
    run_dir = Path(spec.run_dir)
    event_tail = legacy.JsonlTail(run_dir / "events.jsonl")
    tool_tail = legacy.JsonlTail(run_dir / "tool_calls.jsonl")
    stdout: deque[str] = deque(maxlen=8)
    stderr: deque[str] = deque(maxlen=8)
    process = subprocess.Popen(
        spec.command(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        shell=False,
        env=legacy._process_env(state),
    )
    threads = [
        Thread(target=_drain, args=(process.stdout, stdout), daemon=True),
        Thread(target=_drain, args=(process.stderr, stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()

    legacy._emit(("class:accent", "  ✻ Working "), ("class:muted", f"· {Path(state.workspace).name or state.workspace}"))
    try:
        while process.poll() is None:
            for row in event_tail.read():
                _friendly_event(row)
            for row in tool_tail.read():
                _friendly_tool(row)
            sleep(0.15)
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        legacy._print_note("Stopped by user. The run state is still saved for inspection/resume.")
    finally:
        for thread in threads:
            thread.join(timeout=1)
        for row in event_tail.read():
            _friendly_event(row)
        for row in tool_tail.read():
            _friendly_tool(row)

    state.last_run = spec.run_dir
    if process.returncode not in {0, None}:
        message = next((line for line in reversed(stderr) if line.strip()), "runtime failed")
        legacy._print_error(message)
    _render_final_result(spec.run_dir)
    return int(process.returncode or 0)


def _task_spec(state: legacy.AppState, task: str, *, artifact_target: str | None) -> RunLaunchSpec:
    acceptance = () if artifact_target else (state.acceptance or legacy._detect_acceptance(state.workspace))
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


def _banner(state: legacy.AppState) -> None:
    legacy._banner(state)
    legacy._emit(("class:muted", "  Tell me what you want done. I’ll plan the work, use the available tools, and verify the result."))
    legacy._emit(("class:muted", "  You normally do not need to choose a skill or task mode manually."))
    print()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verified-State Harness friendly conversational terminal UI")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--config", default="harness.toml")
    parser.add_argument("--mode", choices=["software", "hackathon", "ctf", "demo"], default="software")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    state = legacy.AppState(workspace=args.workspace, config=args.config, mode=args.mode)
    session: PromptSession = PromptSession(
        history=InMemoryHistory(),
        auto_suggest=AutoSuggestFromHistory(),
        completer=legacy.SlashCompleter(state),
        complete_while_typing=True,
        style=legacy.STYLE,
        bottom_toolbar=lambda: legacy._bottom_toolbar(state),
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
            if not legacy._handle_command(state, session, text):
                return 0
            continue

        legacy._print_user(text)
        intake = analyze_task_input(text)
        if intake.requested_workspace:
            requested = Path(intake.requested_workspace).resolve()
            current = Path(state.workspace).expanduser().resolve()
            if requested != current:
                state.workspace = str(requested)
                legacy._print_good(f"Using the project you requested · {requested}")
        elif intake.workspace_ambiguous:
            legacy._print_note("I found more than one project path in the request, so I kept the current workspace. Use /workspace <path> if one should be the write target.")

        if intake.artifact_target:
            legacy._print_note(
                f"Deliverable detected · {intake.artifact_target}. I’ll inspect project evidence first, then write and recheck the artifact."
            )

        if not legacy._ensure_model_ready(state, session):
            print()
            continue

        previous_artifact = state.session_env.get("HARNESS_TASK_ARTIFACT_TARGET")
        if intake.artifact_target:
            state.session_env["HARNESS_TASK_ARTIFACT_TARGET"] = intake.artifact_target
        else:
            state.session_env.pop("HARNESS_TASK_ARTIFACT_TARGET", None)
        try:
            spec = _task_spec(state, text, artifact_target=intake.artifact_target)
            if state.mode in {"software", "hackathon"} and not intake.artifact_target and not spec.acceptance_commands:
                legacy._emit(("class:warn", "  ! "), ("class:muted", "No deterministic completion check was detected. Use /accept <command> if this task has one."))
            _run_spec(state, spec)
        finally:
            if previous_artifact is None:
                state.session_env.pop("HARNESS_TASK_ARTIFACT_TARGET", None)
            else:
                state.session_env["HARNESS_TASK_ARTIFACT_TARGET"] = previous_artifact


if __name__ == "__main__":
    raise SystemExit(main())
