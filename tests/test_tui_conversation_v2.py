import json
import os
from pathlib import Path
import signal

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from harness import __version__
from harness.tui_conversation import (
    _COMMAND_DESCRIPTIONS,
    _ConversationCompleter,
    _banner,
    _interrupt_process,
    _recent_sessions,
    _resolve_session,
    _session_status,
)
from harness.tui_visual import AppState


def test_tui_v2_palette_exposes_described_primary_commands(tmp_path):
    state = AppState(workspace=str(tmp_path), config=str(tmp_path / "missing.toml"))
    completer = _ConversationCompleter(state)
    completions = list(
        completer.get_completions(
            Document(text="/"),
            CompleteEvent(completion_requested=True),
        )
    )
    names = {item.text for item in completions}

    assert {"/connect", "/model", "/sessions", "/status", "/permissions", "/help"} <= names
    assert all(_COMMAND_DESCRIPTIONS[name] for name in _COMMAND_DESCRIPTIONS)


def test_tui_v2_recent_sessions_use_user_run_root_and_newest_first(tmp_path, monkeypatch):
    root = tmp_path / "runs"
    older = root / "20260821-090000"
    newer = root / "20260821-100000"
    older.mkdir(parents=True)
    newer.mkdir()
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))
    monkeypatch.setenv("HARNESS_RUN_ROOT", str(root))

    sessions = _recent_sessions(limit=10)

    assert sessions == [newer, older]
    assert _resolve_session(newer.name) == newer.resolve()


def test_tui_v2_session_status_prefers_cli_owned_final_result(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "final_result.json").write_text(
        json.dumps({"completed": True}),
        encoding="utf-8",
    )

    assert _session_status(run_dir) == "completed"


def test_tui_v2_banner_omits_package_version(tmp_path, capsys):
    state = AppState(workspace=str(tmp_path), config=str(tmp_path / "missing.toml"))

    _banner(state)

    rendered = capsys.readouterr().out
    assert "base_harness" in rendered
    assert __version__ not in rendered


def test_tui_v2_posix_interrupt_targets_child_process_group(monkeypatch):
    seen = []

    class Process:
        pid = 4242

        def poll(self):
            return None

        def terminate(self):
            raise AssertionError("terminate fallback should not be used")

    monkeypatch.setattr(os, "killpg", lambda pid, sig: seen.append((pid, sig)))

    _interrupt_process(Process(), platform_name="posix")

    assert seen == [(4242, signal.SIGINT)]
