from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib
from typing import Any, Mapping, Sequence


DOMAINS = ("software", "hackathon", "ctf", "demo")


class TUIConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TUISettings:
    profile: str = "software"
    acceptance_commands: tuple[str, ...] = ()
    execution_backend: str | None = None
    strict_layout: bool | None = None
    strict_tool_isolation: bool | None = None
    network_policy: str | None = None
    require_sealed_oracle: bool | None = None
    require_oracle_isolation: bool | None = None

    def security_mapping(self) -> dict[str, Any]:
        values = {
            "execution_backend": self.execution_backend,
            "strict_layout": self.strict_layout,
            "strict_tool_isolation": self.strict_tool_isolation,
            "network_policy": self.network_policy,
            "require_sealed_oracle": self.require_sealed_oracle,
            "require_oracle_isolation": self.require_oracle_isolation,
        }
        return {key: value for key, value in values.items() if value is not None}


def initial_workspace(
    explicit: str | Path | None = None,
    *,
    invocation_dir: str | Path | None = None,
    home_dir: str | Path | None = None,
) -> Path:
    """Use an explicit directory, otherwise invocation cwd, then the user home."""
    if explicit is not None:
        candidates = [Path(explicit).expanduser()]
    else:
        candidates = [
            Path(invocation_dir) if invocation_dir is not None else Path.cwd(),
            Path(home_dir).expanduser() if home_dir is not None else Path.home(),
        ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_dir():
            return resolved
    if explicit is not None:
        raise TUIConfigError(f"workspace must be an existing directory: {explicit}")
    raise TUIConfigError("neither the invocation directory nor the user home is available")


def default_config_path(
    explicit: str | Path | None = None,
    *,
    invocation_dir: str | Path | None = None,
    home_dir: str | Path | None = None,
) -> Path:
    """Prefer explicit/local TOML; otherwise store shared settings under user home."""
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env_path = os.environ.get("HARNESS_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()

    invocation = Path(invocation_dir) if invocation_dir is not None else Path.cwd()
    local = invocation / "harness.toml"
    if local.exists() and local.is_file():
        return local.resolve()

    if home_dir is not None:
        home = Path(home_dir).expanduser()
        if os.name == "nt":
            return (home / "AppData" / "Roaming" / "base_harness" / "harness.toml").resolve()
        return (home / ".config" / "base_harness" / "harness.toml").resolve()

    home = Path.home()
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA") or (home / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config")).expanduser()
    return (root / "base_harness" / "harness.toml").resolve()


def load_tui_settings(path: str | Path) -> TUISettings:
    candidate = Path(path).expanduser()
    if not candidate.exists():
        return TUISettings()
    if not candidate.is_file():
        raise TUIConfigError(f"config path is not a file: {candidate}")
    try:
        with candidate.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise TUIConfigError(f"config cannot be loaded: {exc}") from exc

    profile = raw.get("profile", "software")
    if profile not in DOMAINS:
        raise TUIConfigError(f"unsupported profile/domain in config: {profile!r}")
    acceptance = raw.get("acceptance_commands", [])
    if not isinstance(acceptance, list) or any(not isinstance(item, str) or not item for item in acceptance):
        raise TUIConfigError("acceptance_commands must be an array of non-empty strings")
    security = raw.get("security", {})
    if not isinstance(security, dict):
        raise TUIConfigError("security must be a TOML table")

    def optional_bool(key: str) -> bool | None:
        value = security.get(key)
        if value is not None and not isinstance(value, bool):
            raise TUIConfigError(f"security.{key} must be boolean")
        return value

    execution_backend = security.get("execution_backend")
    if execution_backend is not None and execution_backend not in {"local", "linux-namespace"}:
        raise TUIConfigError("security.execution_backend must be local or linux-namespace")
    network_policy = security.get("network_policy")
    if network_policy is not None and network_policy not in {"allow", "deny"}:
        raise TUIConfigError("security.network_policy must be allow or deny")

    return TUISettings(
        profile=profile,
        acceptance_commands=tuple(acceptance),
        execution_backend=execution_backend,
        strict_layout=optional_bool("strict_layout"),
        strict_tool_isolation=optional_bool("strict_tool_isolation"),
        network_policy=network_policy,
        require_sealed_oracle=optional_bool("require_sealed_oracle"),
        require_oracle_isolation=optional_bool("require_oracle_isolation"),
    )


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in value) + "]"
    raise TUIConfigError(f"unsupported TOML value: {value!r}")


def _section_bounds(lines: list[str], section: str | None) -> tuple[int, int] | None:
    headers: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$", line)
        if match:
            headers.append((index, match.group(1).strip()))
    if section is None:
        return 0, headers[0][0] if headers else len(lines)
    for position, (index, name) in enumerate(headers):
        if name == section:
            end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
            return index + 1, end
    return None


def _set_value(text: str, *, section: str | None, key: str, value: Any) -> str:
    lines = text.splitlines()
    rendered = f"{key} = {_literal(value)}"
    bounds = _section_bounds(lines, section)
    if bounds is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([f"[{section}]", rendered])
        return "\n".join(lines).rstrip() + "\n"

    start, end = bounds
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for index in range(start, end):
        if pattern.match(lines[index]):
            lines[index] = rendered
            return "\n".join(lines).rstrip() + "\n"

    insert_at = end
    while insert_at > start and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, rendered)
    return "\n".join(lines).rstrip() + "\n"


def _base_text() -> str:
    return (
        'profile = "software"\n'
        'run_dir = "./run"\n'
        'acceptance_commands = []\n\n'
        '[workspace]\n'
        f'root = {json.dumps(str(Path.home()), ensure_ascii=False)}\n\n'
        '[security]\n'
        'execution_backend = "local"\n'
        'strict_layout = false\n'
        'strict_tool_isolation = false\n'
        'network_policy = "allow"\n'
        'require_sealed_oracle = false\n'
        'require_oracle_isolation = false\n'
    )


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def persist_tui_settings(
    path: str | Path,
    *,
    workspace: str | Path | None = None,
    profile: str | None = None,
    acceptance_commands: Sequence[str] | None = None,
    security: Mapping[str, Any] | None = None,
) -> Path:
    target = Path(path).expanduser().resolve()
    text = target.read_text(encoding="utf-8") if target.exists() else _base_text()
    if profile is not None:
        if profile not in DOMAINS:
            raise TUIConfigError(f"unsupported profile/domain: {profile}")
        text = _set_value(text, section=None, key="profile", value=profile)
    if acceptance_commands is not None:
        commands = tuple(acceptance_commands)
        if any(not isinstance(item, str) or not item for item in commands):
            raise TUIConfigError("acceptance commands must be non-empty strings")
        text = _set_value(text, section=None, key="acceptance_commands", value=commands)
    if workspace is not None:
        root = initial_workspace(workspace)
        text = _set_value(text, section="workspace", key="root", value=str(root))
    for key, value in dict(security or {}).items():
        if key not in {
            "execution_backend", "strict_layout", "strict_tool_isolation",
            "network_policy", "require_sealed_oracle", "require_oracle_isolation",
        }:
            raise TUIConfigError(f"unsupported TUI security key: {key}")
        text = _set_value(text, section="security", key=key, value=value)

    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise TUIConfigError(f"generated config is invalid TOML: {exc}") from exc
    _atomic_write(target, text)
    return target
