import json

from harness.tui import RunLaunchSpec, RunView


def test_tui_launch_spec_builds_cli_command_without_shell_interpolation(tmp_path):
    spec = RunLaunchSpec(
        config="harness.toml",
        workspace=str(tmp_path / "workspace with space"),
        run_dir=str(tmp_path / "run"),
        profile="software",
        goal="fix auth flow",
        acceptance_commands=("python -m pytest tests/test_auth.py",),
        max_steps=20,
        task_revision="task-v1",
        execution_backend="linux-namespace",
        strict_layout=True,
        strict_tool_isolation=True,
        network_policy="deny",
    )
    command = spec.command(python_executable="python-test")
    assert command[:3] == ["python-test", "-m", "harness.cli"]
    assert "fix auth flow" in command
    assert str(tmp_path / "workspace with space") in command
    assert "--strict-layout" in command
    assert "--strict-tool-isolation" in command
    assert command[command.index("--network-policy") + 1] == "deny"
    assert command[command.index("--accept-command") + 1] == "python -m pytest tests/test_auth.py"


def test_tui_run_view_reads_persisted_runtime_artifacts(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "metrics.json").write_text(json.dumps({
        "completed": True,
        "steps": 4,
        "tool_calls": 2,
        "failures": 0,
        "progress_events": 1,
        "recovery_transitions": 0,
    }), encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        "\n".join([
            json.dumps({"step": 1, "kind": "agent.plan.replaced"}),
            json.dumps({"step": 4, "kind": "completion.accepted"}),
        ]) + "\n",
        encoding="utf-8",
    )
    (run_dir / "tool_calls.jsonl").write_text(
        json.dumps({"step": 3, "tool": "shell", "ok": True}) + "\n",
        encoding="utf-8",
    )

    view = RunView(run_dir).refresh()
    assert view.metrics["completed"] is True
    assert view.last_events[-1]["kind"] == "completion.accepted"
    assert view.last_tool_calls[-1]["tool"] == "shell"
    rendered = "\n".join(view.summary_lines())
    assert "completed=True" in rendered
    assert "completion.accepted" in rendered
    assert "shell" in rendered


def test_tui_run_view_tolerates_partial_or_malformed_live_files(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "metrics.json").write_text("{partial", encoding="utf-8")
    (run_dir / "events.jsonl").write_text(
        json.dumps({"step": 1, "kind": "run.start"}) + "\n{partial\n",
        encoding="utf-8",
    )
    view = RunView(run_dir).refresh()
    assert view.metrics == {}
    assert view.last_events == [{"step": 1, "kind": "run.start"}]
