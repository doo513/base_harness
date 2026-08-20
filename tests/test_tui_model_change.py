import tomllib

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from harness.skill_actions import configure_provider
from harness import tui_visual as legacy
from harness.tui_conversation import _ConversationCompleter, _handle_command


class _NoPromptSession:
    def prompt(self, *args, **kwargs):
        raise AssertionError("prompt should not be needed when /change receives an alias")


def test_change_alias_switches_configured_default_model(tmp_path, monkeypatch):
    config = tmp_path / "harness.toml"
    configure_provider(config, alias="one", preset="ollama", model="model-one")
    configure_provider(config, alias="two", preset="ollama", model="model-two", make_default=False)
    monkeypatch.setattr(legacy, "_discover_local_ollama_models", lambda endpoint="http://127.0.0.1:11434": [])

    state = legacy.AppState(workspace=str(tmp_path), config=str(config))
    assert _handle_command(state, _NoPromptSession(), "/change two") is True

    parsed = tomllib.loads(config.read_text(encoding="utf-8"))
    assert parsed["default_model"] == "two"
    assert state.model_status()[:2] == ("two", "model-two")


def test_change_command_autocomplete_exposes_aliases(tmp_path, monkeypatch):
    config = tmp_path / "harness.toml"
    configure_provider(config, alias="alpha", preset="ollama", model="model-a")
    configure_provider(config, alias="beta", preset="ollama", model="model-b", make_default=False)
    monkeypatch.setattr(legacy, "_discover_local_ollama_models", lambda endpoint="http://127.0.0.1:11434": [])

    state = legacy.AppState(workspace=str(tmp_path), config=str(config))
    completer = _ConversationCompleter(state)

    command_items = list(completer.get_completions(
        Document(text="/cha", cursor_position=4),
        CompleteEvent(completion_requested=True),
    ))
    assert any(item.text == "/change" for item in command_items)

    alias_items = list(completer.get_completions(
        Document(text="/change b", cursor_position=9),
        CompleteEvent(completion_requested=True),
    ))
    assert [item.text for item in alias_items] == ["beta"]
