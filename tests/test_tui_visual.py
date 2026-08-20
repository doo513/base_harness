import tomllib

from harness.skill_actions import configure_provider
from harness.tui_visual import _detect_acceptance, _model_status, _set_default_model


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
