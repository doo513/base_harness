from types import SimpleNamespace

from harness import tui_entry


class FakeState:
    def __init__(self, config="harness.toml"):
        self.config = config
        self.session_env = {}

    def model_status(self):
        return "not connected", "-", False


class FakeSession:
    pass


def test_connect_opencode_skips_login_when_persistent_auth_exists(monkeypatch):
    state = FakeState()
    notes = []
    monkeypatch.setattr(tui_entry, "is_opencode_authenticated", lambda **kwargs: True)
    monkeypatch.setattr(
        tui_entry,
        "login_opencode_provider",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("login should not run")),
    )
    monkeypatch.setattr(tui_entry.legacy, "_print_good", lambda text: notes.append(text))
    monkeypatch.setattr(tui_entry.legacy, "_print_note", lambda text: notes.append(text))

    tui_entry._connect_with_opencode(state, FakeSession(), "opencode")

    assert state.session_env[tui_entry._AUTH_SENTINEL] == "1"
    assert any("already stored" in text for text in notes)


def test_connect_opencode_runs_official_login_and_keeps_only_nonsecret_session_sentinel(monkeypatch):
    state = FakeState()
    notes = []
    monkeypatch.setattr(tui_entry, "is_opencode_authenticated", lambda **kwargs: False)
    monkeypatch.setattr(
        tui_entry,
        "login_opencode_provider",
        lambda **kwargs: SimpleNamespace(success=True, verified=True, returncode=0),
    )
    monkeypatch.setattr(tui_entry.legacy, "_print_good", lambda text: notes.append(text))
    monkeypatch.setattr(tui_entry.legacy, "_print_note", lambda text: notes.append(text))
    monkeypatch.setattr(tui_entry.legacy, "_print_error", lambda text: notes.append("ERROR:" + text))

    tui_entry._connect_with_opencode(state, FakeSession(), "opencode")

    assert state.session_env == {tui_entry._AUTH_SENTINEL: "1"}
    assert not any("api_key" in key.lower() for key in state.session_env)
    assert any("persistent auth store" in text for text in notes)


def test_connect_without_argument_offers_opencode_as_provider(monkeypatch):
    state = FakeState()
    seen = []
    monkeypatch.setattr(tui_entry, "is_opencode_authenticated", lambda **kwargs: True)
    monkeypatch.setattr(
        tui_entry.legacy,
        "_prompt_text",
        lambda session, label, default="": seen.append((label, default)) or "opencode",
    )
    monkeypatch.setattr(tui_entry.legacy, "_print_good", lambda text: None)
    monkeypatch.setattr(tui_entry.legacy, "_print_note", lambda text: None)

    tui_entry._connect_with_opencode(state, FakeSession(), "")

    assert seen
    assert "opencode" in seen[0][0]
    assert seen[0][1] == "opencode"


def test_opencode_route_is_authenticated_before_run(monkeypatch):
    state = FakeState(config="config.toml")
    monkeypatch.setattr(
        tui_entry.legacy,
        "_config_data",
        lambda path: {
            "default_model": "opencode",
            "models": {
                "opencode": {
                    "model": "opencode/free-model",
                    "options": {"adapter": "opencode"},
                }
            },
        },
    )
    monkeypatch.setattr(tui_entry, "is_opencode_authenticated", lambda **kwargs: True)

    assert tui_entry._ensure_model_ready_with_opencode(state, FakeSession()) is True
    assert state.session_env[tui_entry._AUTH_SENTINEL] == "1"


def test_missing_opencode_auth_triggers_connect_before_run(monkeypatch):
    state = FakeState(config="config.toml")
    monkeypatch.setattr(
        tui_entry.legacy,
        "_config_data",
        lambda path: {
            "default_model": "opencode",
            "models": {
                "opencode": {
                    "model": "opencode/free-model",
                    "options": {"adapter": "opencode"},
                }
            },
        },
    )
    monkeypatch.setattr(tui_entry, "is_opencode_authenticated", lambda **kwargs: False)
    monkeypatch.setattr(tui_entry.legacy, "_print_note", lambda text: None)

    def fake_connect(current_state, session, argument=""):
        assert argument == "opencode"
        current_state.session_env[tui_entry._AUTH_SENTINEL] = "1"

    monkeypatch.setattr(tui_entry, "_connect_with_opencode", fake_connect)

    assert tui_entry._ensure_model_ready_with_opencode(state, FakeSession()) is True
