from __future__ import annotations

from pathlib import Path

import pytest

from harness.core.linux_namespace_backend import LinuxNamespaceSandboxBackend


def test_nested_read_only_source_mount_fails_closed(tmp_path, monkeypatch):
    source = (tmp_path / "source").resolve()
    nested = source / "nested"
    workspace = (tmp_path / "workspace").resolve()
    nested.mkdir(parents=True)
    workspace.mkdir()

    backend = LinuxNamespaceSandboxBackend(
        read_only_paths=[source],
        runtime_read_only_paths=(),
    )
    monkeypatch.setattr(backend, "_current_mount_points", lambda: (Path("/"), nested))

    with pytest.raises(ValueError, match="contains nested mount"):
        backend._validate_ro_paths(workspace)


def test_source_itself_may_be_mount_point_without_false_positive(tmp_path, monkeypatch):
    source = (tmp_path / "source").resolve()
    workspace = (tmp_path / "workspace").resolve()
    source.mkdir()
    workspace.mkdir()

    backend = LinuxNamespaceSandboxBackend(
        read_only_paths=[source],
        runtime_read_only_paths=(),
    )
    monkeypatch.setattr(backend, "_current_mount_points", lambda: (Path("/"), source))
    backend._validate_ro_paths(workspace)


def test_mountinfo_octal_path_decode():
    decoded = LinuxNamespaceSandboxBackend._decode_mountinfo_path(r"/tmp/a\040b\134c")
    assert decoded == "/tmp/a b\\c"
