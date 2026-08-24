from __future__ import annotations

from dataclasses import dataclass
import re
import subprocess
from typing import Any


class OpenCodeAuthError(RuntimeError):
    pass


_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class OpenCodeAuthStatus:
    provider: str
    authenticated: bool
    raw_output: str


@dataclass(frozen=True)
class OpenCodeLoginResult:
    provider: str
    success: bool
    verified: bool
    returncode: int


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _ANSI_RE.sub("", value).lower())


def parse_auth_list(stdout: str, *, provider: str = "opencode") -> OpenCodeAuthStatus:
    """Conservatively detect a provider in `opencode auth list` output.

    OpenCode owns the credential file and its exact presentation is not part of
    the Harness contract. The parser therefore only answers whether the requested
    provider name appears in normalized output; it never reads or copies secrets.
    """
    provider_key = _normalize(provider)
    if not provider_key:
        raise OpenCodeAuthError("OpenCode provider must not be empty")
    normalized = _normalize(stdout)
    return OpenCodeAuthStatus(
        provider=provider,
        authenticated=provider_key in normalized,
        raw_output=stdout,
    )


def opencode_auth_status(
    *,
    binary: str = "opencode",
    provider: str = "opencode",
    timeout_seconds: float = 15.0,
) -> OpenCodeAuthStatus:
    if not binary.strip():
        raise OpenCodeAuthError("OpenCode binary must not be empty")
    if not provider.strip():
        raise OpenCodeAuthError("OpenCode provider must not be empty")
    if timeout_seconds <= 0:
        raise OpenCodeAuthError("OpenCode auth status timeout must be positive")
    try:
        proc = subprocess.run(
            [binary, "auth", "list"],
            text=True,
            capture_output=True,
            timeout=float(timeout_seconds),
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OpenCodeAuthError("OpenCode auth status timed out") from exc
    except OSError as exc:
        raise OpenCodeAuthError(f"OpenCode auth command failed to start: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        raise OpenCodeAuthError(f"OpenCode auth list failed ({proc.returncode}): {detail}")
    return parse_auth_list(proc.stdout, provider=provider)


def login_opencode_provider(
    *,
    binary: str = "opencode",
    provider: str = "opencode",
    timeout_seconds: float = 600.0,
) -> OpenCodeLoginResult:
    """Delegate credential entry/storage to OpenCode's official auth command.

    stdin/stdout/stderr are deliberately inherited. The API key is entered into
    OpenCode's own secure prompt and is never passed through Harness argv, config,
    subprocess input, captured output, or environment mutation.
    """
    if not binary.strip():
        raise OpenCodeAuthError("OpenCode binary must not be empty")
    if not provider.strip():
        raise OpenCodeAuthError("OpenCode provider must not be empty")
    if timeout_seconds <= 0:
        raise OpenCodeAuthError("OpenCode auth login timeout must be positive")
    try:
        proc = subprocess.run(
            [binary, "auth", "login", "--provider", provider],
            timeout=float(timeout_seconds),
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OpenCodeAuthError("OpenCode auth login timed out") from exc
    except OSError as exc:
        raise OpenCodeAuthError(f"OpenCode auth login failed to start: {exc}") from exc

    if proc.returncode != 0:
        return OpenCodeLoginResult(
            provider=provider,
            success=False,
            verified=False,
            returncode=int(proc.returncode),
        )

    verified = False
    try:
        verified = opencode_auth_status(
            binary=binary,
            provider=provider,
            timeout_seconds=min(15.0, timeout_seconds),
        ).authenticated
    except OpenCodeAuthError:
        # A successful official login command is sufficient to continue this TUI
        # session even if a later display/status command is unavailable. The next
        # real model call remains the operational verification boundary.
        verified = False

    return OpenCodeLoginResult(
        provider=provider,
        success=True,
        verified=verified,
        returncode=0,
    )


def is_opencode_authenticated(
    *,
    binary: str = "opencode",
    provider: str = "opencode",
) -> bool:
    try:
        return opencode_auth_status(binary=binary, provider=provider).authenticated
    except OpenCodeAuthError:
        return False
