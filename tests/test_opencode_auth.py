from types import SimpleNamespace

import pytest

from harness.opencode_auth import (
    OpenCodeAuthError,
    login_opencode_provider,
    opencode_auth_status,
    parse_auth_list,
)


def test_parse_auth_list_detects_opencode_without_exposing_credentials():
    status = parse_auth_list("Credentials\n  OpenCode Zen - active\n  Anthropic - active\n")
    assert status.provider == "opencode"
    assert status.authenticated is True
    assert "OpenCode Zen" in status.raw_output


def test_auth_status_uses_read_only_auth_list(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="opencode - active\n", stderr="")

    monkeypatch.setattr("harness.opencode_auth.subprocess.run", fake_run)
    status = opencode_auth_status(binary="opencode", provider="opencode", timeout_seconds=5)

    assert status.authenticated is True
    assert captured["argv"] == ["opencode", "auth", "list"]
    assert captured["capture_output"] is True
    assert captured["shell"] is False


def test_login_delegates_secret_entry_to_official_opencode_prompt(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        if argv[1:3] == ["auth", "login"]:
            assert "input" not in kwargs
            assert "capture_output" not in kwargs
            assert kwargs["shell"] is False
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=0, stdout="OpenCode Zen - active\n", stderr="")

    monkeypatch.setattr("harness.opencode_auth.subprocess.run", fake_run)
    result = login_opencode_provider(binary="opencode", provider="opencode", timeout_seconds=30)

    assert result.success is True
    assert result.verified is True
    assert calls[0][0] == ["opencode", "auth", "login", "--provider", "opencode"]
    assert calls[1][0] == ["opencode", "auth", "list"]
    assert all("api" not in " ".join(argv).lower() or "provider" in " ".join(argv).lower() for argv, _ in calls)


def test_login_nonzero_is_not_reported_as_authenticated(monkeypatch):
    monkeypatch.setattr(
        "harness.opencode_auth.subprocess.run",
        lambda argv, **kwargs: SimpleNamespace(returncode=2),
    )
    result = login_opencode_provider(timeout_seconds=30)
    assert result.success is False
    assert result.verified is False
    assert result.returncode == 2


def test_invalid_auth_arguments_fail_closed():
    with pytest.raises(OpenCodeAuthError):
        opencode_auth_status(binary="")
    with pytest.raises(OpenCodeAuthError):
        login_opencode_provider(provider="")
