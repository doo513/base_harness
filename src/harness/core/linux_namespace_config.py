from __future__ import annotations

from pathlib import Path
from typing import Iterable
import os
import re
import shutil
import stat
import sys

from .sandbox_primitives import IsolationAttestation, NetworkPolicy


class LinuxNamespaceConfigMixin:
    def __init__(
        self,
        *,
        network_policy: NetworkPolicy = NetworkPolicy.DENY,
        inherit_env: bool = False,
        workspace_writable: bool = True,
        read_only_paths: Iterable[str | Path] = (),
        runtime_read_only_paths: Iterable[str | Path] | None = None,
    ):
        self.network_policy = NetworkPolicy(network_policy)
        self.inherit_env = inherit_env
        self.workspace_writable = bool(workspace_writable)
        self.read_only_paths = tuple(
            Path(p).expanduser().resolve() for p in read_only_paths
        )
        if runtime_read_only_paths is None:
            runtime: list[Path] = []
            prefix = Path(sys.prefix).resolve()
            # /usr is always mounted separately. A virtual environment outside
            # /usr must be made visible read-only so python/pytest entry points
            # continue to work inside the sandbox.
            if prefix != Path("/usr") and not self._is_within(prefix, Path("/usr")):
                runtime.append(prefix)
            self.runtime_read_only_paths = tuple(runtime)
        else:
            self.runtime_read_only_paths = tuple(
                Path(p).expanduser().resolve() for p in runtime_read_only_paths
            )
        self._attestation_cache: IsolationAttestation | None = None

    @staticmethod
    def _is_within(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    @staticmethod
    def _path_target(root: Path, absolute: Path) -> Path:
        if not absolute.is_absolute():
            raise ValueError(f"sandbox path must be absolute: {absolute}")
        return root / absolute.relative_to("/")

    @classmethod
    def required_commands_available(cls) -> tuple[bool, dict[str, str | None]]:
        found = {name: shutil.which(name) for name in cls._REQUIRED_COMMANDS}
        return all(found.values()), found

    @staticmethod
    def _decode_mountinfo_path(raw: str) -> str:
        # proc(5) mountinfo escapes whitespace/backslash as octal sequences.
        return re.sub(
            r"\\([0-7]{3})",
            lambda match: chr(int(match.group(1), 8)),
            raw,
        )

    @classmethod
    def _current_mount_points(cls) -> tuple[Path, ...]:
        """Return current mount points from one /proc/self/mountinfo snapshot."""
        try:
            lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RuntimeError(f"cannot inspect mount topology: {exc}") from exc

        mount_points: list[Path] = []
        for line in lines:
            fields = line.split()
            if len(fields) < 6:
                raise RuntimeError("malformed /proc/self/mountinfo entry")
            decoded = cls._decode_mountinfo_path(fields[4])
            mount_points.append(Path(decoded).resolve())
        return tuple(mount_points)

    @classmethod
    def _nested_mounts(cls, source: Path, mount_points: Iterable[Path]) -> list[Path]:
        if not source.is_dir():
            return []
        return sorted(
            {
                mount_point
                for mount_point in mount_points
                if mount_point != source and cls._is_within(mount_point, source)
            },
            key=str,
        )

    def _sandbox_path(self) -> str:
        candidates = []
        prefix_bin = Path(sys.prefix).resolve() / "bin"
        if prefix_bin.exists() and not self._is_within(prefix_bin, Path("/usr")):
            candidates.append(str(prefix_bin))
        candidates.extend(["/usr/local/bin", "/usr/local/sbin", "/usr/bin", "/usr/sbin", "/bin", "/sbin"])
        return ":".join(dict.fromkeys(candidates))

    def _env(self, supplied: dict[str, str] | None, *, workspace: Path) -> dict[str, str]:
        if self.inherit_env:
            base = dict(os.environ)
        else:
            base = {
                "PATH": self._sandbox_path(),
                "HOME": str(workspace),
                "TMPDIR": "/vsh-tmp",
                "LANG": os.environ.get("LANG", "C.UTF-8"),
            }
            term = os.environ.get("TERM")
            if term:
                base["TERM"] = term
        if supplied:
            base.update({str(k): str(v) for k, v in supplied.items()})
        return base

    def _validate_ro_paths(self, workspace: Path) -> None:
        # Top-level `remount,bind,ro` does not make descendant mounts read-only.
        # Snapshot mount topology once per sandbox creation and fail closed if a
        # read-only source contains any nested mount. This binds the declared RO
        # policy to the actual mount topology instead of assuming recursion.
        mount_points = self._current_mount_points()
        for source in (*self.runtime_read_only_paths, *self.read_only_paths):
            if not source.exists():
                raise FileNotFoundError(f"sandbox read-only path does not exist: {source}")
            if source == workspace or self._is_within(workspace, source) or self._is_within(source, workspace):
                raise ValueError(
                    f"workspace must not overlap sandbox read-only mount: {source}"
                )
            nested = self._nested_mounts(source, mount_points)
            if nested:
                preview = ", ".join(str(path) for path in nested[:4])
                more = "" if len(nested) <= 4 else f" (+{len(nested) - 4} more)"
                raise ValueError(
                    "sandbox read-only source contains nested mount(s) whose recursive "
                    f"read-only state is not guaranteed: {source}: {preview}{more}"
                )

    def _validate_workspace_tree(self, workspace: Path) -> None:
        """Reject host-backed channels that a plain bind mount would preserve.

        A network namespace does not isolate AF_UNIX sockets that are already
        reachable through the filesystem. Likewise, a hard link in the
        workspace can refer to the same inode as a file outside the workspace.
        Fail closed for special files, nested mounts, and regular-file inodes
        whose complete link set is not contained in the workspace.
        """
        inode_counts: dict[tuple[int, int], int] = {}
        inode_nlinks: dict[tuple[int, int], int] = {}
        inode_examples: dict[tuple[int, int], Path] = {}

        for current, dirs, files in os.walk(workspace, followlinks=False):
            current_path = Path(current)
            for name in [*dirs, *files]:
                path = current_path / name
                info = path.lstat()
                mode = info.st_mode

                if stat.S_ISLNK(mode):
                    # Symlink escape is contained by chroot path resolution; it
                    # is separately covered by the Stage-02 attack probe.
                    continue
                if stat.S_ISDIR(mode):
                    if path.is_mount():
                        raise ValueError(f"nested mount is not allowed in sandbox workspace: {path}")
                    continue
                if stat.S_ISREG(mode):
                    key = (info.st_dev, info.st_ino)
                    inode_counts[key] = inode_counts.get(key, 0) + 1
                    inode_nlinks[key] = info.st_nlink
                    inode_examples.setdefault(key, path)
                    continue
                raise ValueError(
                    f"unsafe workspace special file is not allowed: {path}"
                )

        for key, count in inode_counts.items():
            nlink = inode_nlinks[key]
            if nlink > count:
                raise ValueError(
                    "workspace file has hard links outside the workspace: "
                    f"{inode_examples[key]} (visible_links={count}, st_nlink={nlink})"
                )
