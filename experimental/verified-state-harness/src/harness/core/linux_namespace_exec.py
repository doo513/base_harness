from __future__ import annotations

from pathlib import Path
import platform
import subprocess
import tempfile

from .sandbox_primitives import ExecutionResult, NetworkPolicy


class LinuxNamespaceExecutionMixin:
    def _prepare_root(self, root: Path, *, workspace: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)

        # /usr is the primary immutable runtime tree. Preserve the common
        # merged-/usr symlinks inside the chroot instead of bind-mounting the
        # host root filesystem.
        (root / "usr").mkdir(parents=True, exist_ok=True)
        for link, target in (
            ("bin", "usr/bin"),
            ("sbin", "usr/sbin"),
            ("lib", "usr/lib"),
            ("lib64", "usr/lib64"),
        ):
            p = root / link
            if not p.exists() and not p.is_symlink():
                p.symlink_to(target)

        # Workspace and explicit read-only mounts keep the same absolute path
        # inside the chroot. This preserves existing command templates such as
        # {workspace} and {sealed_root} without exposing unrelated host paths.
        for source in (workspace, *self.runtime_read_only_paths, *self.read_only_paths):
            target = self._path_target(root, source)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.touch(exist_ok=True)

        for source in self._ETC_FILES:
            src = Path(source)
            if not src.exists():
                continue
            target = self._path_target(root, src)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(exist_ok=True)

        for source in self._DEVICE_FILES:
            src = Path(source)
            if not src.exists():
                continue
            target = self._path_target(root, src)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(exist_ok=True)

        # /vsh-tmp becomes a namespace-local tmpfs during setup. A dedicated
        # path avoids masking workspaces that legitimately live below /tmp.
        (root / "tmp").mkdir(parents=True, exist_ok=True)
        (root / "vsh-tmp").mkdir(parents=True, exist_ok=True)

        # The chroot skeleton itself must not become a second writable area.
        # Mounts are installed afterwards by the namespace setup process.
        directories = [p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()]
        for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
            directory.chmod(0o555)
        root.chmod(0o555)

    def _mount_specs(self) -> list[str]:
        specs: list[str] = []
        seen: set[Path] = set()
        for source in (*self.runtime_read_only_paths, *self.read_only_paths):
            if source in seen:
                continue
            seen.add(source)
            specs.append(f"{source}::{source}")
        return specs

    def _unshare_command(self, *, root: Path, workspace: Path, command: str) -> list[str]:
        available, found = self.required_commands_available()
        if not available:
            missing = [name for name, path in found.items() if not path]
            raise RuntimeError(f"missing Linux sandbox commands: {', '.join(missing)}")

        cmd = [
            found["unshare"] or "unshare",
            "--user",
            "--map-root-user",
            "--mount",
            "--pid",
            "--fork",
            "--kill-child=SIGKILL",
        ]
        if self.network_policy == NetworkPolicy.DENY:
            cmd.append("--net")
        cmd.extend([
            found["sh"] or "/bin/sh",
            "-c",
            self._SETUP_SCRIPT,
            "vsh-setup",
            str(root),
            str(workspace),
            "rw" if self.workspace_writable else "ro",
            command,
            *self._mount_specs(),
        ])
        return cmd

    def _run_shell_unchecked(
        self,
        *,
        workspace: Path,
        command: str,
        timeout_seconds: float,
        env: dict[str, str] | None,
    ) -> ExecutionResult:
        if platform.system() != "Linux":
            return ExecutionResult(
                returncode=126,
                stdout="",
                stderr="Linux namespace sandbox is only available on Linux",
            )

        workspace = Path(workspace).expanduser().resolve()
        if not workspace.exists() or not workspace.is_dir():
            return ExecutionResult(
                returncode=126,
                stdout="",
                stderr=f"workspace must be an existing directory: {workspace}",
            )

        try:
            self._validate_ro_paths(workspace)
            self._validate_workspace_tree(workspace)
            with tempfile.TemporaryDirectory(prefix="vsh-linuxns-root-") as td:
                root = Path(td).resolve()
                self._prepare_root(root, workspace=workspace)
                proc = subprocess.run(
                    self._unshare_command(root=root, workspace=workspace, command=command),
                    text=True,
                    capture_output=True,
                    timeout=timeout_seconds,
                    env=self._env(env, workspace=workspace),
                )
                return ExecutionResult(
                    returncode=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                )
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(
                returncode=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                timed_out=True,
            )
        except Exception as exc:
            return ExecutionResult(
                returncode=126,
                stdout="",
                stderr=f"sandbox setup failed: {type(exc).__name__}: {exc}",
            )

    def run_shell(self, *, workspace, command, timeout_seconds, env=None):
        if not isinstance(command, str) or not command.strip():
            return ExecutionResult(2, "", "command must be a non-empty string")
        return self._run_shell_unchecked(
            workspace=Path(workspace),
            command=command,
            timeout_seconds=timeout_seconds,
            env=env,
        )

