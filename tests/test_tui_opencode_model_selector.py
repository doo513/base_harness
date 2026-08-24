from types import SimpleNamespace
import tomllib

from harness.opencode_selection import OpenCodeModelInfo
from harness import tui_entry


class FakeSession:
    def __init__(self, answers):
        self.answers = iter(answers)

    def prompt(self, *args, **kwargs):
        return next(self.answers)


def _item(ref, *, free, context=65536):
    provider, model_id = ref.split("/", 1)
    return OpenCodeModelInfo(
        ref=ref,
        provider=provider,
        model_id=model_id,
        name=model_id,
        context_window=context,
        input_limit=None,
        output_limit=8192,
        cost_input=0.0 if free else 1.0,
        cost_output=0.0 if free else 2.0,
        explicitly_free=free,
        metadata={},
    )


def test_model_opencode_browses_catalog_and_persists_selected_route(tmp_path, monkeypatch):
    config = tmp_path / "harness.toml"
    state = SimpleNamespace(config=str(config))
    free = _item("opencode/free-model", free=True, context=131072)
    paid = _item("opencode/paid-model", free=False)
    monkeypatch.setattr(
        tui_entry,
        "list_opencode_models",
        lambda **kwargs: (paid, free),
    )
    monkeypatch.setattr(tui_entry.legacy, "_prompt_text", lambda session, label, default="": "1")
    notes = []
    monkeypatch.setattr(tui_entry.legacy, "_emit", lambda *parts, **kwargs: None)
    monkeypatch.setattr(tui_entry.legacy, "_print_note", lambda text: notes.append(text))
    monkeypatch.setattr(tui_entry.legacy, "_print_error", lambda text: notes.append("ERROR:" + text))
    monkeypatch.setattr(tui_entry.legacy, "_print_good", lambda text: notes.append(text))

    tui_entry._models_with_opencode(state, FakeSession([]), "opencode")

    data = tomllib.loads(config.read_text(encoding="utf-8"))
    assert data["default_model"] == "opencode"
    route = data["models"]["opencode"]
    assert route["model"] == "opencode/free-model"
    assert route["options"]["catalog_explicitly_free"] is True
    assert route["options"]["context_window"] == 131072
    assert route["options"]["opencode_agent"] == "harness-model"
    assert route["options"]["context_safety_margin_source"] == "opencode_adapter_overhead_guard"
    assert any("opencode/free-model" in note for note in notes)


def test_model_opencode_exact_ref_skips_numeric_choice(tmp_path, monkeypatch):
    config = tmp_path / "harness.toml"
    state = SimpleNamespace(config=str(config))
    first = _item("opencode/first", free=True)
    second = _item("opencode/second", free=True)
    monkeypatch.setattr(tui_entry, "list_opencode_models", lambda **kwargs: (first, second))
    monkeypatch.setattr(
        tui_entry.legacy,
        "_prompt_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("prompt should not run")),
    )
    monkeypatch.setattr(tui_entry.legacy, "_emit", lambda *parts, **kwargs: None)
    monkeypatch.setattr(tui_entry.legacy, "_print_note", lambda text: None)
    monkeypatch.setattr(tui_entry.legacy, "_print_error", lambda text: None)
    monkeypatch.setattr(tui_entry.legacy, "_print_good", lambda text: None)

    tui_entry._models_with_opencode(state, FakeSession([]), "opencode/second")

    data = tomllib.loads(config.read_text(encoding="utf-8"))
    assert data["models"]["opencode"]["model"] == "opencode/second"


def test_non_opencode_model_argument_uses_existing_model_handler(monkeypatch):
    called = []
    monkeypatch.setattr(tui_entry, "_ORIGINAL_MODELS", lambda state, session, argument="": called.append(argument))
    tui_entry._models_with_opencode(SimpleNamespace(config="x"), FakeSession([]), "ollama")
    assert called == ["ollama"]


def test_install_selector_composes_existing_tui_without_replacing_runtime(monkeypatch):
    monkeypatch.setattr(tui_entry, "_INSTALLED", False)
    monkeypatch.setattr(tui_entry.legacy, "_models", tui_entry._ORIGINAL_MODELS)
    monkeypatch.setattr(tui_entry.legacy, "_connect", tui_entry._ORIGINAL_CONNECT)
    monkeypatch.setattr(tui_entry.legacy, "_help", tui_entry._ORIGINAL_HELP)
    monkeypatch.setattr(
        tui_entry.conversation,
        "_ensure_model_ready",
        tui_entry._ORIGINAL_ENSURE_MODEL_READY,
    )
    monkeypatch.setattr(
        tui_entry.conversation,
        "_ConversationCompleter",
        tui_entry._ORIGINAL_COMPLETER,
    )
    original_model_description = tui_entry.conversation._COMMAND_DESCRIPTIONS["/model"]
    original_connect_description = tui_entry.conversation._COMMAND_DESCRIPTIONS["/connect"]
    monkeypatch.setitem(
        tui_entry.conversation._COMMAND_DESCRIPTIONS,
        "/model",
        original_model_description,
    )
    monkeypatch.setitem(
        tui_entry.conversation._COMMAND_DESCRIPTIONS,
        "/connect",
        original_connect_description,
    )

    tui_entry.install_opencode_model_selector()

    assert tui_entry.legacy._models is tui_entry._models_with_opencode
    assert tui_entry.legacy._connect is tui_entry._connect_with_opencode
    assert tui_entry.legacy._help is tui_entry._help_with_opencode
    assert tui_entry.conversation._ensure_model_ready is tui_entry._ensure_model_ready_with_opencode
    assert tui_entry.conversation._ConversationCompleter is tui_entry._OpenCodeCompleter
    assert "OpenCode" in tui_entry.conversation._COMMAND_DESCRIPTIONS["/model"]
    assert "OpenCode" in tui_entry.conversation._COMMAND_DESCRIPTIONS["/connect"]
