import tomllib

from harness.skill_actions import configure_provider
from harness.tui_visual import (
    AppState,
    COMMANDS,
    _detect_acceptance,
    _model_status,
    _set_default_model,
    _task_spec,
)


def test_visual_tui_detects_python_acceptance_with_python3_on_posix(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    commands = _detect_acceptance(tmp_path)
    assert len(commands) == 1
    assert commands[0].endswith("-m pytest -q")


def test_visual_tui_model_picker_switches_default_without_touching_secret(tmp_path):
    path = tmp_path / "harness.toml"
    configure_provider(path, alias="one", preset="ollama", model="qwen-one")
    configure_provider(path, alias="two", preset="gemini", model="gemini-two", secret_env="MY_KEY", make_default=False)

    _set_default_model(path, "two")
    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    assert parsed["default_model"] == "two"
    assert parsed["models"]["two"]["api_key"] == "env:MY_KEY"


def test_visual_tui_model_status_reports_missing_environment_credential(tmp_path, monkeypatch):
    path = tmp_path / "harness.toml"
    configure_provider(path, alias="gemini", preset="gemini", model="gemini-test", secret_env="VISUAL_TEST_KEY")
    monkeypatch.delenv("VISUAL_TEST_KEY", raising=False)
    alias, model, ready = _model_status(path)
    assert alias == "gemini"
    assert model == "gemini-test"
    assert ready is False


def test_visual_tui_session_credential_makes_configured_model_ready(tmp_path, monkeypatch):
    path = tmp_path / "harness.toml"
    configure_provider(path, alias="gemini", preset="gemini", model="gemini-test", secret_env="SESSION_ONLY_KEY")
    monkeypatch.delenv("SESSION_ONLY_KEY", raising=False)
    state = AppState(workspace=str(tmp_path), config=str(path))
    assert state.model_status()[2] is False
    state.session_env["SESSION_ONLY_KEY"] = "not-persisted"
    assert state.model_status()[2] is True
    assert "not-persisted" not in path.read_text(encoding="utf-8")


def test_visual_tui_exposes_expected_agent_cli_commands():
    assert {"/connect", "/model", "/mcp", "/skills", "/permissions", "/resume", "/status"} <= set(COMMANDS)


def test_visual_tui_task_spec_auto_detects_acceptance_and_fresh_run(tmp_path):
    (tmp_path / "tests").mkdir()
    state = AppState(workspace=str(tmp_path), mode="software")
    spec = _task_spec(state, "fix the project")
    assert spec.goal == "fix the project"
    assert spec.acceptance_commands
    assert spec.acceptance_commands[0].endswith("-m pytest -q")
    assert spec.run_dir.startswith("runs") or spec.run_dir.startswith("./runs")


def test_visual_tui_extracts_target_workspace_from_prompt(tmp_path):
    sub_dir = tmp_path / "target_project"
    sub_dir.mkdir()
    state = AppState(workspace=str(tmp_path), mode="software")
    
    # Prompt containing directory path
    prompt = f'analyze "{sub_dir}" and write report'
    spec = _task_spec(state, prompt)
    assert str(sub_dir.resolve()) in spec.workspace


def test_visual_tui_synthesizes_acceptance_for_report_request(tmp_path):
    state = AppState(workspace=str(tmp_path), mode="software")
    spec = _task_spec(state, "이 프로젝트를 분석해서 보고서를 작성해줘")
    assert spec.acceptance_commands
    assert "Analysis goal completed" in spec.acceptance_commands[0]


def test_visual_tui_local_endpoint_ready_without_secret(tmp_path):
    path = tmp_path / "harness.toml"
    configure_provider(path, alias="ollama_local", preset="ollama", model="gemma-4")
    alias, model, ready = _model_status(path)
    assert alias == "ollama_local"
    assert model == "gemma-4"
    assert ready is True

