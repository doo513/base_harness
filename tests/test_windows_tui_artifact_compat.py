import os
from pathlib import Path

import pytest

from harness.core.storage import ArtifactStore, IntegrityError
from harness.tui import _default_new_run_dir


def test_artifact_store_portable_verified_read_accepts_valid_bytes(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_text("sample.txt", "hello")

    monkeypatch.setattr(os, "name", "nt", raising=False)
    assert store.verified_read_bytes(ref) == b"hello"


def test_artifact_store_portable_verified_read_rejects_tampering(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_text("sample.txt", "hello")
    path = store.resolve(ref)
    path.write_text("tampered", encoding="utf-8")

    monkeypatch.setattr(os, "name", "nt", raising=False)
    with pytest.raises(IntegrityError, match="hash mismatch"):
        store.verified_read_bytes(ref)


def test_default_tui_run_dir_uses_external_state_root(tmp_path, monkeypatch):
    workspace = tmp_path / "project"
    workspace.mkdir()
    state_root = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_root))

    run_dir = Path(_default_new_run_dir())
    assert state_root / "base_harness" / "runs" in run_dir.parents
    assert workspace not in run_dir.parents
