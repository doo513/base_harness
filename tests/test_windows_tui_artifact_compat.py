from pathlib import Path

import pytest

from harness.core.storage import ArtifactStore, IntegrityError
from harness.tui import _default_new_run_dir
from harness import tui_visual


def test_artifact_store_portable_verified_read_accepts_valid_bytes(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_text("sample.txt", "hello")

    assert ArtifactStore._portable_verified_read_bytes_from_root(store.root, ref) == b"hello"


def test_artifact_store_portable_verified_read_rejects_tampering(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_text("sample.txt", "hello")
    path = store.resolve(ref)
    path.write_text("tampered", encoding="utf-8")

    with pytest.raises(IntegrityError, match="hash mismatch"):
        ArtifactStore._portable_verified_read_bytes_from_root(store.root, ref)


def test_default_tui_run_dir_uses_external_state_root(tmp_path, monkeypatch):
    workspace = tmp_path / "project"
    workspace.mkdir()
    state_root = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))
    monkeypatch.delenv("HARNESS_RUN_ROOT", raising=False)

    run_dir = Path(_default_new_run_dir())
    assert state_root / "base_harness" / "runs" in run_dir.parents
    assert workspace not in run_dir.parents


def test_secret_prompt_uses_dedicated_session(monkeypatch):
    calls = []

    class ConversationSession:
        def prompt(self, *args, **kwargs):
            raise AssertionError("conversation session must not enter password mode")

    class SecretSession:
        def prompt(self, *args, **kwargs):
            calls.append(kwargs)
            return "top-secret"

    monkeypatch.setattr(tui_visual, "PromptSession", SecretSession)
    value = tui_visual._prompt_secret(ConversationSession())

    assert value == "top-secret"
    assert calls and calls[0]["is_password"] is True
