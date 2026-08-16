from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import os
import platform
import shutil
import subprocess
import sys

from .storage import canonical_hash


PROVENANCE_SCHEMA_VERSION = 1
SEMANTIC_SOURCE_PATHS = ("src/harness", "pyproject.toml", "requirements-ci.lock")
TOOLCHAIN_COMMANDS = {
    "git": ("git", "--version"),
    "mount": ("mount", "--version"),
    "unshare": ("unshare", "--version"),
    "setpriv": ("setpriv", "--version"),
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _run_text(command: list[str], *, cwd: Path | None = None, timeout: float = 2.0) -> str | None:
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _project_root() -> Path | None:
    override = os.environ.get("VSH_PROJECT_ROOT")
    if override:
        root = Path(override).expanduser().resolve()
        return root if (root / "pyproject.toml").is_file() else None

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "harness").is_dir():
            return parent
    return None


def _semantic_source_hashes(root: Path | None) -> tuple[dict[str, str], list[str]]:
    warnings: list[str] = []
    hashes: dict[str, str] = {}

    if root is not None:
        harness_root = root / "src" / "harness"
        for path in sorted(harness_root.rglob("*.py")):
            if path.is_file():
                hashes[path.relative_to(root).as_posix()] = _sha256_file(path)
        for relative in ("pyproject.toml", "requirements-ci.lock"):
            path = root / relative
            if path.is_file():
                hashes[relative] = _sha256_file(path)
            else:
                warnings.append(f"build provenance input missing: {relative}")
        return hashes, warnings

    # Installed-wheel/source-tree fallback. This preserves code-content identity
    # even when Git/project metadata is unavailable, but lock/release metadata is
    # necessarily incomplete and therefore reported as a warning.
    package_root = Path(__file__).resolve().parents[1]
    for path in sorted(package_root.rglob("*.py")):
        if path.is_file():
            hashes[f"installed:harness/{path.relative_to(package_root).as_posix()}"] = _sha256_file(path)
    warnings.append("project root unavailable; git/config/lock build provenance is incomplete")
    return hashes, warnings


def _git_audit(root: Path | None) -> dict[str, Any]:
    if root is None or shutil.which("git") is None:
        return {
            "available": False,
            "commit": None,
            "tree": None,
            "tracked_dirty": None,
            "status_entries": None,
        }

    commit = _run_text(["git", "rev-parse", "HEAD"], cwd=root)
    tree = _run_text(["git", "rev-parse", "HEAD^{tree}"], cwd=root)
    tracked_status = _run_text(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root)
    all_status = _run_text(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root)
    available = commit is not None and tree is not None
    return {
        "available": available,
        "commit": commit,
        "tree": tree,
        "tracked_dirty": None if tracked_status is None else bool(tracked_status),
        "status_entries": None if all_status is None else len([line for line in all_status.splitlines() if line.strip()]),
    }


def _toolchain_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name, command in TOOLCHAIN_COMMANDS.items():
        if shutil.which(command[0]) is None:
            versions[name] = "UNAVAILABLE"
            continue
        output = _run_text(list(command))
        versions[name] = output.splitlines()[0] if output else "UNAVAILABLE"
    return versions


def _ci_environment() -> dict[str, str | None]:
    return {
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "runner_image_os": os.environ.get("ImageOS"),
        "runner_image_version": os.environ.get("ImageVersion"),
        "container_image_digest": os.environ.get("VSH_CONTAINER_IMAGE_DIGEST"),
    }


@dataclass(frozen=True)
class BuildProvenance:
    schema_version: int
    source_hashes: dict[str, str]
    source_semantic_hash: str
    dependency_lock_path: str | None
    dependency_lock_sha256: str | None
    git: dict[str, Any]
    python: dict[str, str]
    platform: dict[str, str]
    toolchain: dict[str, str]
    environment: dict[str, str | None]
    warnings: tuple[str, ...] = ()

    def semantic_descriptor(self) -> dict[str, Any]:
        # Git commit/full tree are audit identifiers. They are intentionally not
        # semantic resume keys because docs/evidence-only commits must not alter
        # runtime meaning. Actual code/config/lock bytes are independently hashed.
        return {
            "schema_version": self.schema_version,
            "source_semantic_hash": self.source_semantic_hash,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "python": dict(self.python),
            "platform": dict(self.platform),
            "toolchain": dict(self.toolchain),
            "environment": {
                "runner_os": self.environment.get("runner_os"),
                "runner_arch": self.environment.get("runner_arch"),
                "container_image_digest": self.environment.get("container_image_digest"),
            },
        }

    @property
    def semantic_hash(self) -> str:
        return canonical_hash(self.semantic_descriptor())

    def dump(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_hashes": dict(self.source_hashes),
            "source_semantic_hash": self.source_semantic_hash,
            "dependency_lock_path": self.dependency_lock_path,
            "dependency_lock_sha256": self.dependency_lock_sha256,
            "git": dict(self.git),
            "python": dict(self.python),
            "platform": dict(self.platform),
            "toolchain": dict(self.toolchain),
            "environment": dict(self.environment),
            "semantic_hash": self.semantic_hash,
            "warnings": list(self.warnings),
        }


def capture_build_provenance() -> BuildProvenance:
    """Capture release/runtime provenance once when a HarnessRuntime is created."""
    root = _project_root()
    source_hashes, warnings = _semantic_source_hashes(root)
    source_semantic_hash = canonical_hash(source_hashes)

    lock_path: str | None = None
    lock_hash: str | None = None
    if root is not None:
        candidate = root / "requirements-ci.lock"
        if candidate.is_file():
            lock_path = candidate.relative_to(root).as_posix()
            lock_hash = _sha256_file(candidate)
        else:
            warnings.append("requirements-ci.lock is unavailable")

    git = _git_audit(root)
    if not git.get("available"):
        warnings.append("git commit/tree provenance is unavailable")
    elif git.get("tracked_dirty"):
        warnings.append("git tracked worktree is dirty")

    environment = _ci_environment()
    if Path("/.dockerenv").exists() and not environment.get("container_image_digest"):
        warnings.append("container environment detected without VSH_CONTAINER_IMAGE_DIGEST")

    return BuildProvenance(
        schema_version=PROVENANCE_SCHEMA_VERSION,
        source_hashes=source_hashes,
        source_semantic_hash=source_semantic_hash,
        dependency_lock_path=lock_path,
        dependency_lock_sha256=lock_hash,
        git=git,
        python={
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable": str(Path(sys.executable).resolve()),
        },
        platform={
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        toolchain=_toolchain_versions(),
        environment=environment,
        warnings=tuple(dict.fromkeys(warnings)),
    )
