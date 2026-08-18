from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class WorkspaceContractError(ValueError):
    pass


@dataclass(frozen=True)
class WorkspaceContract:
    """Actor workspace boundary and optional managed subdirectories.

    The workspace root is the only path that tools may treat as the actor's
    project root. Managed paths are optional convenience locations and must stay
    inside that root. This contract does not replace OS sandboxing.
    """

    root: Path
    temp_dir: Path | None = None
    build_dir: Path | None = None
    cache_dir: Path | None = None

    @staticmethod
    def _resolve(path: str | Path) -> Path:
        return Path(path).expanduser().resolve()

    @staticmethod
    def _contains(root: Path, candidate: Path) -> bool:
        try:
            candidate.relative_to(root)
            return True
        except ValueError:
            return False

    @classmethod
    def build(
        cls,
        root: str | Path,
        *,
        temp_dir: str | Path | None = None,
        build_dir: str | Path | None = None,
        cache_dir: str | Path | None = None,
    ) -> "WorkspaceContract":
        resolved_root = cls._resolve(root)

        def resolve_managed(value: str | Path | None) -> Path | None:
            if value is None:
                return None
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                candidate = resolved_root / candidate
            return candidate.resolve()

        contract = cls(
            root=resolved_root,
            temp_dir=resolve_managed(temp_dir),
            build_dir=resolve_managed(build_dir),
            cache_dir=resolve_managed(cache_dir),
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        if not self.root.exists():
            raise WorkspaceContractError(f"workspace root does not exist: {self.root}")
        if not self.root.is_dir():
            raise WorkspaceContractError(f"workspace root is not a directory: {self.root}")
        for name, value in (
            ("temp_dir", self.temp_dir),
            ("build_dir", self.build_dir),
            ("cache_dir", self.cache_dir),
        ):
            if value is not None and not self._contains(self.root, value):
                raise WorkspaceContractError(
                    f"{name} must stay inside workspace root: {value}"
                )

    def resolve_actor_path(self, relative_path: str | Path) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            raise WorkspaceContractError("actor path must be relative to workspace root")
        resolved = (self.root / path).resolve()
        if not self._contains(self.root, resolved):
            raise WorkspaceContractError("actor path escapes workspace root")
        return resolved

    def ensure_managed_dirs(self) -> None:
        for value in (self.temp_dir, self.build_dir, self.cache_dir):
            if value is not None:
                value.mkdir(parents=True, exist_ok=True)

    def descriptor(self) -> dict[str, Any]:
        return {
            "schema_version": "workspace-contract-v1",
            "root": str(self.root),
            "temp_dir": str(self.temp_dir) if self.temp_dir is not None else None,
            "build_dir": str(self.build_dir) if self.build_dir is not None else None,
            "cache_dir": str(self.cache_dir) if self.cache_dir is not None else None,
            "managed_paths_inside_root": True,
            "os_isolation_authority": False,
        }
