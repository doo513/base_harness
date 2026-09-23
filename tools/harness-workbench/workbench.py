"""Base Harness Workbench: CLI, environment diagnostics, and safe execution runner.

Harness Workbench is an operator aid for Base Harness development on Windows/WSL.
It is NOT a replacement for the Host/Kernel and NOT an authority over Evidence/Ready.
It is safe by default: no automatic retry loops, no process termination (no kill).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse
from typing import Any, Mapping

from data import (
    ACTOR_LABELS,
    BOUNDARY_MODES,
    DEFAULT_BACKEND,
    DEFAULT_DOMAIN,
    DEFAULT_MODEL,
    DEFAULT_STALE_AFTER,
    DOMAIN_LABELS,
    DOMAINS,
    EVENT_TYPES,
    KNOWN_BACKENDS,
    KNOWN_MODELS,
    PHASE_TO_STAGE,
    PROXY_ENV_KEYS,
    ROLE_RULES,
    SAFETY_PRINCIPLES,
    SENSITIVE_KEYS,
    STAGE_BY_ID,
    STAGES,
    TERMINAL_PHASES,
    WORKBENCH_SCHEMA,
)


def _safe_text(val: Any) -> str:
    return "" if val is None else str(val)


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def configure_output_encoding() -> None:
    """Keep JSON/text output usable in CP949 Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


# ---------------------------------------------------------------------------
# Data Redaction & Proxy Sanitization
# ---------------------------------------------------------------------------
class DataRedactor:
    """Redacts credentials, tokens, keys, and passwords from logs and previews."""

    _REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1***REDACTED***"),
        (re.compile(r"(?i)(sk-[A-Za-z0-9_-]{8,})"), "***REDACTED_KEY***"),
        (re.compile(r"(?i)(AIza[0-9A-Za-z_-]{20,})"), "***REDACTED_KEY***"),
        (
            re.compile(r"(?i)(--?(?:password|passwd|pwd|token|api[-_]?key|secret|cookie)(?:=|\s+))[^\s,;]+"),
            r"\1***REDACTED***",
        ),
        # Keep the authentication scheme visible while masking the bearer
        # credential. The bearer rule above runs first.
        (
            re.compile(r"(?i)(\bauthorization\s*[:=]\s*)(?!Bearer\b)[^\s,;]+"),
            r"\1***REDACTED***",
        ),
        (
            re.compile(r"(?i)(\b(?:password|passwd|pwd|token|api[-_]?key|secret|cookie|access[-_]?key|private[-_]?key)\s*[:=]\s*)[^\s,;]+"),
            r"\1***REDACTED***",
        ),
        # URL with embedded password: http://user:pass@host -> http://user:***REDACTED***@host
        (re.compile(r"(https?://[^:\s/@]+:)([^@\s/]+)(@)"), r"\1***REDACTED***\3"),
    )

    @classmethod
    def redact(cls, text: Any) -> str:
        s = _safe_text(text)
        for pattern, replacement in cls._REDACT_PATTERNS:
            s = pattern.sub(replacement, s)
        return s

    @classmethod
    def redact_object(cls, obj: Any) -> Any:
        if isinstance(obj, str):
            return cls.redact(obj)
        if isinstance(obj, list):
            return [cls.redact_object(item) for item in obj]
        if isinstance(obj, tuple):
            return tuple(cls.redact_object(item) for item in obj)
        if isinstance(obj, dict):
            res = {}
            for k, v in obj.items():
                normalized = _safe_text(k).lower().replace("-", "_")
                if any(sk in normalized for sk in SENSITIVE_KEYS):
                    res[k] = "***REDACTED***"
                else:
                    res[k] = cls.redact_object(v)
            return res
        return obj


def sanitize_proxy_url(proxy_url: str) -> str:
    """Masks embedded password in proxy URLs while preserving scheme, host, and port."""
    if not proxy_url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(proxy_url)
        if parsed.password:
            # Reconstruct netloc with redacted password
            user = parsed.username or ""
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            redacted_netloc = f"{user}:***REDACTED***@{host}{port}"
            return urllib.parse.urlunsplit((parsed.scheme, redacted_netloc, parsed.path, parsed.query, parsed.fragment))
        return proxy_url
    except Exception:
        return DataRedactor.redact(proxy_url)


def get_sanitized_proxies() -> dict[str, str]:
    """Returns proxy environment variables with credentials safely redacted."""
    proxies: dict[str, str] = {}
    for key in PROXY_ENV_KEYS:
        val = os.environ.get(key)
        if val is not None:
            proxies[key] = sanitize_proxy_url(val)
    return proxies


# ---------------------------------------------------------------------------
# OS & Backend Boundary Classification
# ---------------------------------------------------------------------------
def detect_os_identity() -> dict[str, Any]:
    """Detects current OS, WSL environment, kernel version, and platform."""
    is_win = sys.platform == "win32"
    is_wsl = False
    wsl_distro = os.environ.get("WSL_DISTRO_NAME")
    wsl_interop = os.environ.get("WSL_INTEROP")

    if not is_win:
        # Check WSL markers
        if wsl_distro or wsl_interop:
            is_wsl = True
        else:
            proc_version = pathlib.Path("/proc/version")
            if proc_version.exists():
                try:
                    content = proc_version.read_text(encoding="utf-8", errors="ignore").lower()
                    if "microsoft" in content or "wsl" in content:
                        is_wsl = True
                except OSError:
                    pass

    if is_wsl:
        os_type = "wsl"
        os_name = f"Linux (WSL: {wsl_distro or 'generic'})"
    elif is_win:
        os_type = "windows"
        os_name = f"Windows ({platform.release()})"
    elif sys.platform.startswith("linux"):
        os_type = "linux"
        os_name = f"Linux ({platform.release()})"
    elif sys.platform == "darwin":
        os_type = "darwin"
        os_name = f"macOS ({platform.mac_ver()[0] or platform.release()})"
    else:
        os_type = "unknown"
        os_name = platform.system() or "Unknown OS"

    return {
        "os_type": os_type,
        "os_name": os_name,
        "is_windows": is_win,
        "is_wsl": is_wsl,
        "wsl_distro": wsl_distro,
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
    }


def classify_binary_path(binary_path: str | pathlib.Path | None) -> str:
    """Classifies a binary path as 'windows', 'wsl', or 'unknown'."""
    if not binary_path:
        return "unknown"
    p_str = str(binary_path).strip()
    p_lower = p_str.lower()

    # Windows indicators
    if (
        p_lower.endswith(".exe")
        or p_lower.endswith(".cmd")
        or p_lower.endswith(".bat")
        or (len(p_str) > 2 and p_str[1] == ":" and p_str[2] in ("\\", "/"))
        or p_lower.startswith("/mnt/c/")
        or p_lower.startswith("/mnt/d/")
        or "\\users\\" in p_lower
    ):
        return "windows"

    # WSL/Linux indicators
    if (
        p_str.startswith("/usr/")
        or p_str.startswith("/home/")
        or p_str.startswith("/bin/")
        or p_str.startswith("/opt/")
        or p_str.startswith("/var/")
        or p_str.startswith("/etc/")
    ):
        return "wsl"

    return "unknown"


def evaluate_backend_boundary(os_type: str, agy_binary: str | pathlib.Path | None) -> dict[str, Any]:
    """Evaluates whether the selected AGY binary and host OS form a clean boundary.

    WSL Harness + WSL AGY: OK
    Windows Harness + Windows AGY: OK
    Crossed combinations: Mismatch Warning
    """
    binary_type = classify_binary_path(agy_binary)

    if os_type == "wsl" and binary_type == "wsl":
        rule = BOUNDARY_MODES["wsl_native"]
    elif os_type == "windows" and binary_type == "windows":
        rule = BOUNDARY_MODES["windows_native"]
    elif os_type == "wsl" and binary_type == "windows":
        rule = BOUNDARY_MODES["mismatch_wsl_host_windows_agy"]
    elif os_type == "windows" and binary_type == "wsl":
        rule = BOUNDARY_MODES["mismatch_windows_host_wsl_agy"]
    else:
        # Fallback or general match
        if os_type in ("wsl", "linux") and binary_type not in ("windows",):
            rule = BOUNDARY_MODES["wsl_native"]
        elif os_type == "windows" and binary_type not in ("wsl",):
            rule = BOUNDARY_MODES["windows_native"]
        else:
            rule = BOUNDARY_MODES["unknown"]

    is_matched = rule["status"] == "matched"
    warning = None if is_matched else rule["description"]

    return {
        "rule_id": rule["id"],
        "label": rule["label"],
        "status": rule["status"],
        "is_matched": is_matched,
        "badge_color": rule["badge_color"],
        "description": rule["description"],
        "warning": warning,
        "current_os": os_type,
        "binary_type": binary_type,
        "binary_path": str(agy_binary) if agy_binary else "",
    }


# ---------------------------------------------------------------------------
# TLS Reachability Check (Credential-Free)
# ---------------------------------------------------------------------------
def check_tls_reachability(
    host: str = "oauth2.googleapis.com",
    port: int = 443,
    timeout_s: float = 2.5,
) -> dict[str, Any]:
    """Performs a credential-free TCP+TLS handshake check to verify network reachability.

    Zero tokens, headers, cookies, or auth file contents are transmitted.
    Tolerates sandbox isolation and offline environments gracefully.
    """
    t0 = time.perf_counter()
    sock: socket.socket | None = None
    ssock: ssl.SSLSocket | None = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout_s)
        ctx = ssl.create_default_context()
        ssock = ctx.wrap_socket(sock, server_hostname=host)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        cipher = ssock.cipher()
        cipher_desc = f"{cipher[0]} ({cipher[1]})" if cipher else "Unknown Cipher"
        return {
            "host": host,
            "port": port,
            "reachable": True,
            "status": "connected",
            "latency_ms": round(elapsed_ms, 1),
            "cipher": cipher_desc,
            "error": None,
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        err_msg = f"{type(exc).__name__}: {exc}"
        return {
            "host": host,
            "port": port,
            "reachable": False,
            "status": "unreachable",
            "latency_ms": round(elapsed_ms, 1),
            "cipher": None,
            "error": err_msg,
        }
    finally:
        if ssock:
            try:
                ssock.close()
            except Exception:
                pass
        elif sock:
            try:
                sock.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Full Environment Diagnostics
# ---------------------------------------------------------------------------
def diagnose_environment(
    harness_root: str | pathlib.Path | None = None,
    agy_binary: str | pathlib.Path | None = None,
    model: str = DEFAULT_MODEL,
    backend: str = DEFAULT_BACKEND,
    skip_tls: bool = False,
) -> dict[str, Any]:
    """Gathers comprehensive, credential-free environment diagnostics."""
    os_info = detect_os_identity()

    # Python availability
    py_exec = sys.executable
    py_ver = ".".join(map(str, sys.version_info[:3]))
    py_path = shutil.which("python3") or shutil.which("python")

    # Bun availability
    bun_path = shutil.which("bun")
    if not bun_path and os_info["is_wsl"]:
        candidate = pathlib.Path(os.path.expanduser("~/.bun/bin/bun"))
        if candidate.exists() and os.access(candidate, os.X_OK):
            bun_path = str(candidate)

    bun_version: str | None = None
    bun_available = bool(bun_path)
    if bun_path:
        try:
            res = subprocess.run(
                [bun_path, "--version"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if res.returncode == 0:
                bun_version = res.stdout.strip()
        except Exception:
            bun_version = None

    # AGY binary discovery
    if not agy_binary:
        agy_binary = os.environ.get("BASE_HARNESS_AGY_BINARY") or shutil.which("agy")
        if not agy_binary and os_info["is_wsl"]:
            candidate = pathlib.Path(os.path.expanduser("~/.local/bin/agy"))
            if candidate.exists() and os.access(candidate, os.X_OK):
                agy_binary = str(candidate)
        elif not agy_binary and os_info["is_windows"]:
            # Check standard Windows AppData program location
            candidate = pathlib.Path(
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity\Antigravity.exe")
            )
            if candidate.exists():
                agy_binary = str(candidate)

    agy_version: str | None = None
    agy_available = bool(agy_binary and pathlib.Path(agy_binary).exists())
    if agy_available and agy_binary:
        # Only query version if executable on current OS to avoid silent cross-launch
        bin_classification = classify_binary_path(agy_binary)
        if (os_info["is_windows"] and bin_classification == "windows") or (
            os_info["is_wsl"] and bin_classification == "wsl"
        ):
            try:
                res = subprocess.run(
                    [str(agy_binary), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                    check=False,
                )
                if res.returncode == 0:
                    agy_version = res.stdout.strip()
            except Exception:
                agy_version = None

    # Harness root inspection
    harness_root_path: pathlib.Path | None = None
    if harness_root:
        harness_root_path = pathlib.Path(harness_root).resolve()
    else:
        # Check standard defaults
        candidates: list[pathlib.Path] = []
        configured_root = os.environ.get("BASE_HARNESS_ROOT")
        if configured_root:
            candidates.append(pathlib.Path(configured_root).expanduser())
        # Find the checkout from the current directory or this script's
        # ancestors, then try the conventional per-user Downloads location.
        for start in (pathlib.Path.cwd(), pathlib.Path(__file__).resolve().parent):
            candidates.extend(start.parents)
            candidates.append(start)
        candidates.append(pathlib.Path.home() / "Downloads" / "base_harness")
        candidates = list(dict.fromkeys(candidates))
        for c in candidates:
            if c.exists() and (
                (c / "runtime" / "packages" / "base-harness").exists()
                or (c / "src" / "index.ts").exists()
                or (c / "pyproject.toml").exists()
            ):
                harness_root_path = c.resolve()
                break
        if not harness_root_path and candidates:
            harness_root_path = candidates[0]

    harness_exists = bool(harness_root_path and harness_root_path.exists())
    package_dir = (
        harness_root_path / "runtime" / "packages" / "base-harness"
        if harness_root_path
        else None
    )
    has_package = bool(package_dir and package_dir.exists())

    # Backend boundary analysis
    boundary = evaluate_backend_boundary(os_info["os_type"], agy_binary)

    # Sanitized proxy variables
    proxies = get_sanitized_proxies()

    # Clock
    now_local = datetime.datetime.now().astimezone()
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    clock = {
        "local_iso": now_local.isoformat(),
        "utc_iso": now_utc.isoformat(),
        "timezone": now_local.tzname() or "Local",
        "epoch_seconds": round(time.time(), 3),
    }

    # Credential-free TLS reachability
    tls_check = (
        {"status": "skipped", "reachable": False, "note": "TLS reachability check skipped"}
        if skip_tls
        else check_tls_reachability()
    )

    return {
        "schemaVersion": WORKBENCH_SCHEMA,
        "diagnosedAt": clock["utc_iso"],
        "os": os_info,
        "python": {
            "executable": py_exec,
            "version": py_ver,
            "path_binary": py_path,
        },
        "bun": {
            "available": bun_available,
            "binary": bun_path,
            "version": bun_version,
        },
        "agy": {
            "available": agy_available,
            "binary": str(agy_binary) if agy_binary else None,
            "version": agy_version,
            "model": model or DEFAULT_MODEL,
            "backend": backend or DEFAULT_BACKEND,
        },
        "harness": {
            "configured_root": str(harness_root_path) if harness_root_path else None,
            "exists": harness_exists,
            "has_base_harness_package": has_package,
            "package_path": str(package_dir) if package_dir else None,
        },
        "boundary": boundary,
        "proxies": proxies,
        "clock": clock,
        "tlsReachability": tls_check,
    }


# ---------------------------------------------------------------------------
# Run Configuration & Exact Redacted Command Preview
# ---------------------------------------------------------------------------
class RunConfig:
    """Holds configuration for a Base Harness execution run."""

    def __init__(
        self,
        workspace: str | pathlib.Path,
        harness_root: str | pathlib.Path,
        domain: str = DEFAULT_DOMAIN,
        backend: str = DEFAULT_BACKEND,
        model: str = DEFAULT_MODEL,
        goal_file: str | pathlib.Path | None = None,
        log_file: str | pathlib.Path | None = None,
        agy_binary: str | pathlib.Path | None = None,
        python_binary: str | pathlib.Path | None = None,
        bun_binary: str | pathlib.Path | None = None,
    ) -> None:
        self.workspace = pathlib.Path(workspace).resolve() if workspace else pathlib.Path.cwd()
        self.harness_root = pathlib.Path(harness_root).resolve() if harness_root else pathlib.Path.cwd()
        self.domain = domain if domain in DOMAINS else DEFAULT_DOMAIN
        self.backend = backend or DEFAULT_BACKEND
        self.model = model or DEFAULT_MODEL
        self.goal_file = pathlib.Path(goal_file).resolve() if goal_file else (self.harness_root / ".harness-goal.txt")
        self.log_file = pathlib.Path(log_file).resolve() if log_file else (self.harness_root / ".agy-run-workbench.log")
        default_agy = pathlib.Path.home() / ".local" / "bin" / "agy"
        self.agy_binary = str(agy_binary) if agy_binary else (
            os.environ.get("BASE_HARNESS_AGY_BINARY")
            or shutil.which("agy")
            or (str(default_agy) if default_agy.exists() else None)
        )
        self.python_binary = str(python_binary) if python_binary else (os.environ.get("BASE_HARNESS_PYTHON") or sys.executable)
        self.bun_binary = str(bun_binary) if bun_binary else shutil.which("bun")

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "harness_root": str(self.harness_root),
            "domain": self.domain,
            "backend": self.backend,
            "model": self.model,
            "goal_file": str(self.goal_file),
            "log_file": str(self.log_file),
            "agy_binary": self.agy_binary,
            "python_binary": self.python_binary,
            "bun_binary": self.bun_binary,
        }

    def get_base_harness_workdir(self) -> pathlib.Path:
        package_dir = self.harness_root / "runtime" / "packages" / "base-harness"
        if package_dir.exists() and (package_dir / "src" / "index.ts").exists():
            return package_dir
        if (self.harness_root / "src" / "index.ts").exists():
            return self.harness_root
        return self.harness_root

    def build_command_preview(self) -> str:
        """Returns the exact redacted command preview for Base Harness invocation."""
        workdir = self.get_base_harness_workdir()
        bun_cmd = self.bun_binary or "bun"
        agy_bin = self.agy_binary or "agy"
        py_bin = self.python_binary or sys.executable

        lines = [
            f"# Execution Directory: {workdir}",
            f"export BASE_HARNESS_AGY_BINARY={DataRedactor.redact(agy_bin)}",
            f"export BASE_HARNESS_PYTHON={DataRedactor.redact(py_bin)}",
            f"{bun_cmd} run --conditions=browser ./src/index.ts run \\",
            f'  --dir "{DataRedactor.redact(str(self.workspace))}" \\',
            f"  --domain {self.domain} \\",
            f"  --execution-backend {self.backend} \\",
            f"  --execution-model {self.model} \\",
            f"  --format json \\",
            f'  < "{DataRedactor.redact(str(self.goal_file))}" \\',
            f'  > "{DataRedactor.redact(str(self.log_file))}" 2>&1',
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Safe Process Execution (No Retry Loop, No Kill)
# ---------------------------------------------------------------------------
class ProcessRecord:
    """Holds metadata for an executed Base Harness run."""

    def __init__(
        self,
        pid: int,
        start_time: str,
        command_preview: str,
        log_path: str,
        workdir: str,
        process_handle: subprocess.Popen[Any] | None = None,
    ) -> None:
        self.pid = pid
        self.start_time = start_time
        self.command_preview = command_preview
        self.log_path = log_path
        self.workdir = workdir
        self.process_handle = process_handle
        self._exit_code: int | None = None

    @property
    def exit_code(self) -> int | None:
        if self._exit_code is not None:
            return self._exit_code
        if self.process_handle:
            code = self.process_handle.poll()
            if code is not None:
                self._exit_code = code
            return self._exit_code
        return None

    @property
    def is_running(self) -> bool:
        return self.exit_code is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "startTime": self.start_time,
            "command": self.command_preview,
            "logPath": self.log_path,
            "workdir": self.workdir,
            "isRunning": self.is_running,
            "exitCode": self.exit_code,
        }


def launch_base_harness(config: RunConfig) -> ProcessRecord:
    """Safely launches a Base Harness process.

    STRICT CONSTRAINTS:
    - NO automatic retry loop.
    - NO terminate/kill actions provided.
    - Records PID, start time, redacted command, log path, exit code.
    """
    workdir = config.get_base_harness_workdir()
    bun_cmd = config.bun_binary or shutil.which("bun") or "bun"

    # Ensure log parent directory exists
    config.log_file.parent.mkdir(parents=True, exist_ok=True)

    # Ensure goal file exists (create a template if missing)
    if not config.goal_file.exists():
        config.goal_file.parent.mkdir(parents=True, exist_ok=True)
        config.goal_file.write_text(
            f"# Base Harness Goal for {config.workspace.name}\n"
            f"Build and verify the requested target in {config.workspace}.\n",
            encoding="utf-8",
        )

    cmd_args = [
        bun_cmd,
        "run",
        "--conditions=browser",
        "./src/index.ts",
        "run",
        "--dir",
        str(config.workspace),
        "--domain",
        config.domain,
        "--execution-backend",
        config.backend,
        "--execution-model",
        config.model,
        "--format",
        "json",
    ]

    env = dict(os.environ)
    if config.agy_binary:
        env["BASE_HARNESS_AGY_BINARY"] = str(config.agy_binary)
    if config.python_binary:
        env["BASE_HARNESS_PYTHON"] = str(config.python_binary)

    # Open log file for output redirection
    log_fd = open(config.log_file, "a", encoding="utf-8", errors="replace")
    start_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        goal_in = open(config.goal_file, "r", encoding="utf-8", errors="replace")
    except OSError:
        goal_in = None

    # Spawn process safely detached
    kwargs: dict[str, Any] = {
        "cwd": str(workdir),
        "env": env,
        "stdin": goal_in or subprocess.DEVNULL,
        "stdout": log_fd,
        "stderr": subprocess.STDOUT,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd_args, **kwargs)

    # Note: log_fd and goal_in are owned by proc or can be closed in parent
    try:
        if goal_in:
            goal_in.close()
    except Exception:
        pass

    preview = config.build_command_preview()

    return ProcessRecord(
        pid=proc.pid,
        start_time=start_time_iso,
        command_preview=preview,
        log_path=str(config.log_file),
        workdir=str(workdir),
        process_handle=proc,
    )


# ---------------------------------------------------------------------------
# Live Status Section: Lifecycle Monitor Integration & Direct JSONL Fallback
# ---------------------------------------------------------------------------
def _find_lifecycle_monitor() -> pathlib.Path | None:
    """Finds the desktop lifecycle monitor main.py script if present."""
    env_path = os.environ.get("HARNESS_MONITOR_PATH")
    if env_path:
        p = pathlib.Path(env_path).resolve()
        if p.exists():
            return p

    candidates = [
        pathlib.Path(__file__).resolve().parent.parent / "harness_lifecycle_monitor" / "main.py",
        pathlib.Path.home() / "Downloads" / "base_harness" / "harness_lifecycle_monitor" / "main.py",
        pathlib.Path.home() / "OneDrive" / "Desktop" / "harness_lifecycle_monitor" / "main.py",
        pathlib.Path.home() / "OneDrive" / "바탕 화면" / "harness_lifecycle_monitor" / "main.py",
    ]
    for start in (pathlib.Path.cwd(), pathlib.Path(__file__).resolve().parent):
        candidates.extend(parent / "harness_lifecycle_monitor" / "main.py" for parent in (start, *start.parents))
    harness_root = os.environ.get("BASE_HARNESS_ROOT")
    if harness_root:
        candidates.append(pathlib.Path(harness_root).expanduser() / "harness_lifecycle_monitor" / "main.py")
    for c in candidates:
        if c.exists():
            return c.resolve()
    return None


def fetch_monitor_snapshot(
    monitor_main: pathlib.Path,
    workspace: str | pathlib.Path | None = None,
    harness_root: str | pathlib.Path | None = None,
    log_file: str | pathlib.Path | None = None,
    timeout_s: float = 6.0,
) -> dict[str, Any] | None:
    """Reuses the existing desktop lifecycle monitor via 'main.py --json'."""
    cmd = [sys.executable, str(monitor_main), "--json"]
    if workspace:
        cmd.extend(["--workspace", str(workspace)])
    if harness_root:
        cmd.extend(["--harness-root", str(harness_root)])
    if log_file:
        cmd.extend(["--log", str(log_file)])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            if isinstance(data, dict) and "harness" in data:
                return data
    except Exception:
        pass
    return None


def parse_harness_jsonl_records(
    log_paths: list[str | pathlib.Path],
    stale_after_s: float = DEFAULT_STALE_AFTER,
) -> dict[str, Any]:
    """Parses harness JSONL status records directly with evidence-only semantics."""
    records: list[dict[str, Any]] = []
    for lp in log_paths:
        p = pathlib.Path(lp)
        if not p.exists():
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for line_idx, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or not (line.startswith("{") and line.endswith("}")):
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            rec_type = obj.get("type") or "harness_status"
                            if rec_type in EVENT_TYPES or rec_type == "error" or "phase" in obj or "status" in obj:
                                obj["_source_file"] = str(p)
                                obj["_line"] = line_idx
                                records.append(obj)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            continue

    if not records:
        return {
            "source": "direct-jsonl",
            "available": False,
            "domain": "unknown",
            "domainLabel": "Unknown",
            "stage": "unknown",
            "stageLabel": "Unknown",
            "phase": "unknown",
            "actor": "unknown",
            "actorLabel": "Unknown",
            "model": "unknown",
            "backend": "unknown",
            "subagents": {"called": 0, "active": 0, "queued": 0, "failed": 0},
            "outcome": "—",
            "stale": False,
            "warnings": ["관측 가능한 하네스 JSONL 로그 파일이 없습니다."],
            "latestEvent": None,
            "events": [],
        }

    # Keep error records as evidence, but derive the lifecycle fields from the
    # latest status/result record rather than from the error envelope itself.
    status_records = [record for record in records if record.get("type") != "error"]
    latest = status_records[-1] if status_records else records[-1]
    error_records = [record for record in records if record.get("type") == "error"]
    # Check for embedded status
    status_obj = latest.get("status") if isinstance(latest.get("status"), dict) else latest

    phase = _safe_text(status_obj.get("phase") or "unknown").lower()
    domain = _safe_text(status_obj.get("domain") or "unknown").lower()
    stage = PHASE_TO_STAGE.get(phase, "unknown")
    if phase == "autonomous":
        planning_state = _safe_text(status_obj.get("planningState")).lower()
        autonomous = status_obj.get("autonomousResult") or status_obj.get("autonomous") or {}
        lifecycle = _safe_text(autonomous.get("lifecycle") if isinstance(autonomous, dict) else "").lower()
        stage = PHASE_TO_STAGE.get(planning_state, "prepare" if lifecycle == "preparing" else "execute" if lifecycle == "active" else "verify" if lifecycle == "closed" else "unknown")
    stage_info = STAGE_BY_ID.get(stage, {"label": "Unknown"})

    # Execution / Model
    exec_info = status_obj.get("execution") or {}
    model = _safe_text(exec_info.get("modelID") or exec_info.get("model") or "unknown")
    backend = _safe_text(exec_info.get("adapterID") or exec_info.get("backend") or "unknown")

    # Actor determination
    if error_records:
        actor = "idle"
    elif phase in TERMINAL_PHASES:
        actor = "idle"
    elif "worker" in phase or "repair" in phase:
        actor = "subagent_worker"
    elif "verif" in phase:
        actor = "verifier"
    elif "explor" in phase or "search" in phase:
        actor = "external_llm"
    elif "contract" in phase or "plan" in phase or "schedul" in phase:
        actor = "internal_orchestration"
    elif phase == "autonomous":
        actor = "external_llm" if model != "unknown" else "internal_orchestration"
    elif phase == "unknown":
        actor = "unknown"
    else:
        actor = "internal_orchestration"

    # Subagents count
    workers = status_obj.get("workers") or []
    called_cnt = len(workers) if isinstance(workers, list) else _safe_int(status_obj.get("workers"))
    active_cnt = _safe_int(status_obj.get("activeCount") or status_obj.get("activeWorkers"))
    queued_cnt = _safe_int(status_obj.get("queuedCount") or status_obj.get("queuedWorkers"))
    failed_cnt = sum(
        1 for w in workers if isinstance(w, dict) and w.get("state") in ("failed", "error", "cancelled")
    ) if isinstance(workers, list) else 0

    outcome = _safe_text(status_obj.get("outcome") or latest.get("outcome") or "—")
    if error_records:
        error_value = error_records[-1].get("error")
        if isinstance(error_value, dict):
            outcome = _safe_text(error_value.get("_tag") or error_value.get("message") or "runtime_error")
        else:
            outcome = _safe_text(error_value) or "runtime_error"
    if not outcome:
        outcome = "—"

    # Stale calculation
    ts_str = _safe_text(latest.get("timestamp") or status_obj.get("timestamp"))
    is_stale = False
    warnings: list[str] = []
    if ts_str:
        try:
            # Parse ISO timestamp
            if ts_str.isdigit():
                epoch = float(ts_str)
                if epoch > 100_000_000_000:
                    epoch /= 1000
                dt = datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
            else:
                clean_ts = ts_str.replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(clean_ts)
            age = (datetime.datetime.now(datetime.timezone.utc) - dt.astimezone(datetime.timezone.utc)).total_seconds()
            if age > stale_after_s:
                is_stale = True
                warnings.append(f"마지막 상태 이벤트 발생 후 {int(age)}초 경과하여 현재 실행으로 간주하지 않습니다.")
        except Exception:
            pass

    # Recent events list (up to 10)
    event_list = []
    for r in records[-10:]:
        s = r.get("status") if isinstance(r.get("status"), dict) else r
        event_list.append({
            "timestamp": _safe_text(r.get("timestamp") or s.get("timestamp")),
            "type": _safe_text(r.get("type") or "harness_status"),
            "phase": _safe_text(s.get("phase")),
            "outcome": _safe_text(s.get("outcome") or r.get("outcome")),
            "failureKind": _safe_text(s.get("failureKind") or r.get("failureKind") or (r.get("error") or {}).get("_tag") if isinstance(r.get("error"), dict) else s.get("failureKind") or r.get("failureKind")),
        })

    latest_event = event_list[-1] if event_list else None
    if error_records:
        error_value = error_records[-1].get("error")
        error_tag = _safe_text(error_value.get("_tag") if isinstance(error_value, dict) else error_value) or "runtime_error"
        warnings.append(f"Harness error observed: {error_tag}")
        if latest_event is not None:
            latest_event["failureKind"] = error_tag

    return {
        "source": "direct-jsonl",
        "available": True,
        "domain": domain,
        "domainLabel": DOMAIN_LABELS.get(domain, domain.title()),
        "stage": stage,
        "stageLabel": stage_info["label"],
        "phase": phase,
        "active": bool(not is_stale and not error_records and phase not in TERMINAL_PHASES),
        "actor": actor,
        "actorLabel": ACTOR_LABELS.get(actor, actor.title()),
        "model": model,
        "backend": backend,
        "subagents": {
            "called": called_cnt,
            "active": active_cnt,
            "queued": queued_cnt,
            "failed": failed_cnt,
        },
        "outcome": outcome,
        "stale": is_stale,
        "warnings": warnings,
        "latestEvent": latest_event,
        "events": event_list,
    }


def get_live_status(
    workspace: str | pathlib.Path | None = None,
    harness_root: str | pathlib.Path | None = None,
    log_file: str | pathlib.Path | None = None,
    monitor_path: str | pathlib.Path | None = None,
    stale_after_s: float = DEFAULT_STALE_AFTER,
) -> dict[str, Any]:
    """Retrieves live status by reusing monitor when present, or direct parsing."""
    monitor_bin = pathlib.Path(monitor_path).resolve() if monitor_path else _find_lifecycle_monitor()

    if monitor_bin and monitor_bin.exists():
        snapshot = fetch_monitor_snapshot(
            monitor_main=monitor_bin,
            workspace=workspace,
            harness_root=harness_root,
            log_file=log_file,
        )
        if snapshot:
            harness = snapshot.get("harness", {})
            execution = snapshot.get("execution", {})
            subagents = snapshot.get("subagents", {})
            events = snapshot.get("events", [])
            latest_ev = events[-1] if events else None

            # Models
            models_list = execution.get("models") or []
            active_model = execution.get("model") or (
                models_list[0].get("model") if models_list else DEFAULT_MODEL
            )
            active_backend = execution.get("adapter") or (
                models_list[0].get("backend") if models_list else DEFAULT_BACKEND
            )

            stage_id = harness.get("stage") or "prepare"
            stage_meta = STAGE_BY_ID.get(stage_id, {"label": stage_id.title()})

            return {
                "source": "lifecycle-monitor",
                "available": True,
                "domain": harness.get("domain", "develop"),
                "domainLabel": harness.get("domainLabel", "Develop"),
                "stage": stage_id,
                "stageLabel": stage_meta.get("label", stage_id.title()),
                "phase": harness.get("phase", "idle"),
                "actor": harness.get("actor", "idle"),
                "actorLabel": harness.get("actorLabel", "Idle"),
                "model": active_model,
                "backend": active_backend,
                "subagents": {
                    "called": subagents.get("called", 0),
                    # Explicit status.workers/metrics is authoritative for
                    # lifecycle counts. A stray process in the monitor's
                    # secondary sensor must not turn a stale/terminal Run
                    # into an active sub-agent count.
                    "active": subagents.get("active", 0)
                    if subagents.get("source") == "status.workers"
                    else subagents.get("activeEvidence", subagents.get("active", 0)),
                    "queued": subagents.get("queued", 0),
                    "failed": subagents.get("failed", 0),
                },
                "outcome": harness.get("outcome", "—") or "—",
                "stale": harness.get("stale", False),
                "warnings": snapshot.get("warnings", []),
                "latestEvent": latest_ev,
                "events": events[-10:],
            }

    # Fallback to direct JSONL parser
    candidates: list[pathlib.Path] = []
    if log_file:
        candidates.append(pathlib.Path(log_file))
    if harness_root:
        hr = pathlib.Path(harness_root)
        candidates.extend(hr.glob(".agy*.log"))
        candidates.extend([hr / ".harness.log", hr / "harness.jsonl"])
    if workspace:
        ws = pathlib.Path(workspace)
        candidates.extend(ws.glob(".agy*.log"))
        candidates.extend([ws / ".harness.log", ws / "harness.jsonl"])

    # Portable default; users can override this with --harness-root or
    # BASE_HARNESS_ROOT. Only existing logs are read by the parser.
    default_root = pathlib.Path(os.environ.get("BASE_HARNESS_ROOT", pathlib.Path.home() / "Downloads" / "base_harness")).expanduser()
    candidates.extend(default_root.glob(".agy*.log"))
    default_log = default_root / ".agy-run-harness-monitor.log"
    if default_log.exists() and default_log not in candidates:
        candidates.append(default_log)

    return parse_harness_jsonl_records(candidates, stale_after_s=stale_after_s)


# ---------------------------------------------------------------------------
# CLI Text Formatters
# ---------------------------------------------------------------------------
def format_diagnostics_text(diag: dict[str, Any]) -> str:
    """Formats diagnostic dictionary into human-readable text."""
    os_info = diag.get("os", {})
    py_info = diag.get("python", {})
    bun_info = diag.get("bun", {})
    agy_info = diag.get("agy", {})
    harness_info = diag.get("harness", {})
    boundary = diag.get("boundary", {})
    clock = diag.get("clock", {})
    tls = diag.get("tlsReachability", {})
    proxies = diag.get("proxies", {})

    status_tag = "✓ MATCHED" if boundary.get("is_matched") else "⚠ BOUNDARY MISMATCH"

    lines = [
        "╔══════════════════════════════════════════════════════════════════════╗",
        "║ Base Harness Workbench: Environment Diagnostics                     ║",
        "╠══════════════════════════════════════════════════════════════════════╣",
        f"║ OS Identity    : {os_info.get('os_name', 'Unknown'):<51} ║",
        f"║ Environment    : {os_info.get('os_type', 'unknown').upper():<10} (WSL: {str(os_info.get('is_wsl')):<5}) Architecture: {os_info.get('architecture', ''):<10} ║",
        f"║ Python Exec    : {py_info.get('executable', 'None')[:51]:<51} ║",
        f"║ Python Version : {py_info.get('version', 'None'):<15} Bun Available: {str(bun_info.get('available')):<5} ({bun_info.get('version') or 'N/A'}) ║",
        f"║ Harness Root   : {str(harness_info.get('configured_root') or 'Not Found')[:51]:<51} ║",
        f"║ AGY Binary     : {str(agy_info.get('binary') or 'Not Found')[:51]:<51} ║",
        f"║ AGY Version    : {str(agy_info.get('version') or 'N/A'):<15} Default Model: {str(agy_info.get('model')):<19} ║",
        "╠─ Backend Boundary Check ─────────────────────────────────────────────╣",
        f"║ Mode           : {boundary.get('label', 'Unknown'):<51} ║",
        f"║ Status         : [{status_tag:<18}] OS={boundary.get('current_os')} Binary={boundary.get('binary_type')} ║",
    ]
    if boundary.get("warning"):
        lines.append(f"║ WARNING        : {boundary.get('warning')[:51]:<51} ║")
    lines.extend([
        "╠─ Network & Security ─────────────────────────────────────────────────╣",
        f"║ TLS Check      : oauth2.googleapis.com:443 -> {tls.get('status', 'unknown').upper():<15} ({tls.get('latency_ms', '—')}ms) ║",
    ])
    if tls.get("cipher"):
        lines.append(f"║ TLS Cipher     : {tls.get('cipher')[:51]:<51} ║")
    if tls.get("error"):
        lines.append(f"║ TLS Error      : {tls.get('error')[:51]:<51} ║")
    if proxies:
        lines.append(f"║ Active Proxies : {', '.join(proxies.keys())[:51]:<51} ║")
    else:
        lines.append("║ Active Proxies : None configured (clean environment)                  ║")
    lines.extend([
        "╠─ Clock ──────────────────────────────────────────────────────────────╣",
        f"║ Local Time     : {clock.get('local_iso', '')[:51]:<51} ║",
        f"║ UTC Time       : {clock.get('utc_iso', '')[:51]:<51} ║",
        "╚══════════════════════════════════════════════════════════════════════╝",
    ])
    return "\n".join(lines)


def format_status_text(status: dict[str, Any]) -> str:
    """Formats live status dictionary into human-readable text."""
    stage_markers = []
    current_stage = status.get("stage", "prepare")
    for s in STAGES:
        mark = "●" if s["id"] == current_stage else "○"
        stage_markers.append(f"{mark} {s['label']}")

    sub = status.get("subagents", {})
    ev = status.get("latestEvent") or {}
    stale_text = " [STALE WARNING]" if status.get("stale") else " [ACTIVE]"

    lines = [
        "╔══════════════════════════════════════════════════════════════════════╗",
        "║ Base Harness Workbench: Live Status Snapshot                         ║",
        "╠══════════════════════════════════════════════════════════════════════╣",
        f"║ Domain  : {status.get('domainLabel', 'Unknown'):<18} Stage: {status.get('stageLabel', 'Unknown'):<12} {stale_text:<16} ║",
        f"║ Phase   : {status.get('phase', 'unknown'):<18} Actor: {status.get('actorLabel', 'Unknown'):<19} ║",
        f"║ Model   : {status.get('model', 'unknown'):<18} Backend: {status.get('backend', 'unknown'):<17} ║",
        f"║ Outcome : {status.get('outcome', '—'):<18} Source: {status.get('source', 'unknown'):<18} ║",
        "╠══════════════════════════════════════════════════════════════════════╣",
        "║ " + "   ".join(stage_markers),
        "╠══════════════════════════════════════════════════════════════════════╣",
        f"║ Subagents : Called={sub.get('called', 0)} Active={sub.get('active', 0)} Queued={sub.get('queued', 0)} Failed={sub.get('failed', 0)}",
    ]
    if ev:
        lines.extend([
            "╠─ Latest Event ───────────────────────────────────────────────────────╣",
            f"║ Time    : {ev.get('timestamp', '—')}",
            f"║ Type    : {ev.get('type', '—')} (Phase: {ev.get('phase', '—')})",
            f"║ Detail  : {ev.get('failureKind') or ev.get('outcome') or '—'}",
        ])
    for w in status.get("warnings", []):
        lines.append(f"║ ! Warning: {w}")
    lines.append("╚══════════════════════════════════════════════════════════════════════╝")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI Argument Parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Base Harness Workbench: Operator Aid, Environment Diagnostics & Safe Runner",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--diagnose", action="store_true", help="Run comprehensive environment diagnostics")
    mode.add_argument("--status", action="store_true", help="Inspect live Base Harness status")
    mode.add_argument("--preview", action="store_true", help="Show exact redacted run command preview")
    mode.add_argument("--start", action="store_true", help="Safely launch Base Harness once (no retry, no kill)")
    mode.add_argument("--gui", action="store_true", help="Launch Tkinter desktop GUI")

    parser.add_argument("--json", action="store_true", help="Output pure JSON to stdout")
    parser.add_argument("--workspace", help="Target workspace path")
    parser.add_argument("--harness-root", help="Base Harness repository root directory")
    parser.add_argument("--domain", choices=DOMAINS, default=DEFAULT_DOMAIN, help="Execution domain (develop/general)")
    parser.add_argument("--backend", default=DEFAULT_BACKEND, help="Execution backend (e.g. antigravity-cli)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Execution model (default: gemini-3.8-flash-high)")
    parser.add_argument("--goal-file", help="Path to goal input file")
    parser.add_argument("--log-file", help="Path to output log file")
    parser.add_argument("--agy-binary", help="Path to agy or Antigravity binary")
    parser.add_argument("--monitor-path", help="Explicit path to desktop lifecycle monitor main.py")
    parser.add_argument("--stale-after", type=float, default=DEFAULT_STALE_AFTER, help="Seconds before marking run stale")
    parser.add_argument("--skip-tls", action="store_true", help="Skip TLS reachability check")
    parser.add_argument("--watch", action="store_true", help="Keep refreshing Live Status until Ctrl+C")
    parser.add_argument("--interval", type=float, default=2.0, help="Watch refresh interval in seconds")
    parser.add_argument("--follow", action="store_true", help="Keep the launcher attached until an explicit Run exits")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = build_parser().parse_args(argv)

    # Initialize RunConfig
    config = RunConfig(
        workspace=args.workspace,
        harness_root=args.harness_root,
        domain=args.domain,
        backend=args.backend,
        model=args.model,
        goal_file=args.goal_file,
        log_file=args.log_file,
        agy_binary=args.agy_binary,
    )

    # --watch is a status mode even when no other mode flag is supplied.
    if args.watch and not (args.diagnose or args.status or args.preview or args.start or args.gui):
        args.status = True

    # If no mode flag specified, default to GUI if display available, otherwise diagnose
    if not (args.diagnose or args.status or args.preview or args.start or args.gui):
        has_display = bool(os.environ.get("DISPLAY") or sys.platform == "win32")
        if has_display and not args.json:
            args.gui = True
        else:
            args.diagnose = True

    # GUI Mode
    if args.gui:
        try:
            from gui import WorkbenchGUI
            app = WorkbenchGUI(config=config, monitor_path=args.monitor_path)
            app.mainloop()
            return 0
        except Exception as exc:
            print(f"GUI launch failed: {exc}. Falling back to continuous CLI status.", file=sys.stderr)
            args.gui = False
            args.status = True
            args.watch = True

    # Mode: Diagnose
    if args.diagnose:
        diag = diagnose_environment(
            harness_root=config.harness_root,
            agy_binary=config.agy_binary,
            model=config.model,
            backend=config.backend,
            skip_tls=args.skip_tls,
        )
        if args.json:
            print(json.dumps(diag, indent=2, ensure_ascii=False))
        else:
            print(format_diagnostics_text(diag))
        return 0

    # Mode: Status
    if args.status:
        try:
            while True:
                st = get_live_status(
                    workspace=config.workspace,
                    harness_root=config.harness_root,
                    log_file=config.log_file,
                    monitor_path=args.monitor_path,
                    stale_after_s=args.stale_after,
                )
                if args.json:
                    if args.watch:
                        # One compact JSON object per line is stream-friendly.
                        print(json.dumps(st, ensure_ascii=False, separators=(",", ":")), flush=True)
                    else:
                        print(json.dumps(st, indent=2, ensure_ascii=False))
                else:
                    if args.watch:
                        print("\x1b[2J\x1b[H", end="")
                    print(format_status_text(st), flush=True)
                if not args.watch:
                    return 0
                time.sleep(max(0.25, args.interval))
        except KeyboardInterrupt:
            return 130

    # Mode: Preview
    if args.preview:
        preview_text = config.build_command_preview()
        if args.json:
            out = {
                "config": config.to_dict(),
                "redactedPreview": preview_text,
            }
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            print(preview_text)
        return 0

    # Mode: Start
    if args.start:
        try:
            record = launch_base_harness(config)
        except Exception as exc:
            error = {"started": False, "errorType": type(exc).__name__, "error": DataRedactor.redact(str(exc))}
            if args.json:
                print(json.dumps(error, indent=2, ensure_ascii=False))
            else:
                print(f"Base Harness start failed: {error['error']}", file=sys.stderr)
            return 1
        if args.follow:
            try:
                while record.is_running:
                    time.sleep(max(0.25, args.interval))
            except KeyboardInterrupt:
                # Do not terminate the child implicitly. The caller can
                # inspect its PID and decide what to do outside this tool.
                pass
        if args.json:
            print(json.dumps(record.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(f"Base Harness started successfully!")
            print(f"  PID       : {record.pid}")
            print(f"  Start Time: {record.start_time}")
            print(f"  Log File  : {record.log_path}")
            print(f"  Workdir   : {record.workdir}")
            print(f"  Exit Code : {record.exit_code} (Running: {record.is_running})")
            print("Notice: No automatic retry loop. Safe by default.")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
