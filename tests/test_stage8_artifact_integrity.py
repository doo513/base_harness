from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from harness.core.storage import ArtifactStore, IntegrityError
from harness.core.verification import _verified_artifact_bytes, _verified_artifact_json


def test_verified_read_returns_exact_hashed_buffer(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_text("message.txt", "hello")
    assert store.verified_read_bytes(ref) == b"hello"
    assert store.verified_read_text(ref) == "hello"


def test_tampered_bytes_fail_closed(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_json("payload.json", {"ok": True, "value": "ORIGINAL"})
    path = store.resolve(ref)
    path.write_text(json.dumps({"ok": True, "value": "TAMPERED"}), encoding="utf-8")
    with pytest.raises(IntegrityError, match="content hash mismatch"):
        store.verified_read_bytes(ref)


def test_missing_malformed_and_path_escape_refs_fail_closed(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    missing = "artifact://" + ("a" * 64) + "_missing.json"
    with pytest.raises(IntegrityError, match="missing"):
        store.verified_read_bytes(missing)
    with pytest.raises((ValueError, IntegrityError)):
        store.verified_read_bytes("artifact://not-addressed")
    with pytest.raises(ValueError):
        store.verified_read_bytes("artifact://" + ("b" * 64) + "_../escape")


def test_symlink_substitution_is_rejected(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_text("message.txt", "original")
    token = ref[len("artifact://"):]
    path = store.resolve(ref)
    target = tmp_path / "outside.txt"
    target.write_text("original", encoding="utf-8")
    path.unlink()
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(IntegrityError):
        store.verified_read_bytes(ref)


def test_swap_after_first_read_cannot_substitute_returned_bytes(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("POSIX directory-fd atomic swap test")
    store = ArtifactStore(tmp_path / "artifacts")

    original = (b"A" * (1024 * 1024)) + (b"B" * 64)
    # put_text uses UTF-8 and this payload is ASCII, so encoded bytes are exact.
    ref = store.put_text("large.txt", original.decode("ascii"))
    path = store.resolve(ref)

    replacement = path.with_name("replacement.tmp")
    replacement.write_bytes(b"TAMPERED")

    real_read = os.read
    swapped = {"done": False}

    def racing_read(fd: int, size: int) -> bytes:
        chunk = real_read(fd, size)
        if chunk and not swapped["done"]:
            swapped["done"] = True
            os.replace(replacement, path)
        return chunk

    monkeypatch.setattr(os, "read", racing_read)
    returned = store.verified_read_bytes(ref)

    # The caller receives the exact bytes read from the already-open original
    # inode. A pathname replacement cannot replace the verified return buffer.
    assert swapped["done"] is True
    assert returned == original

    # A later logical read opens the new pathname and therefore rejects it.
    with pytest.raises(IntegrityError, match="content hash mismatch"):
        store.verified_read_bytes(ref)


def test_stage4_helpers_consume_verified_buffer_not_reopened_path(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    ref = store.put_json("payload.json", {"bound_claim": "x", "value": 7})
    assert json.loads(_verified_artifact_bytes(store.root, ref).decode("utf-8"))["value"] == 7
    assert _verified_artifact_json(store.root, ref)["bound_claim"] == "x"

    path = store.resolve(ref)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(IntegrityError):
        _verified_artifact_bytes(store.root, ref)
