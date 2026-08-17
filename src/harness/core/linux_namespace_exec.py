from __future__ import annotations

from pathlib import Path
import platform
import subprocess
import tempfile

from .sandbox_primitives import ExecutionResult, NetworkPolicy, PopenExecutionSession


class LinuxNamespaceExecutionMixin:
    def _prepare_root(self, root: Path, *, workspace: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / "usr").mkdir(parents=True, exist_ok=True)
        for link, target in (("bin", "usr/bin"), ("sbin", "usr/sbin"), ("lib", "usr/lib"), ("lib64", "usr/lib64")):
            p = root / link
            if not p.exists() and not p.is_symlink():
                p.symlink_to(target)

        for source in (workspace, *self.runtime_read_only_paths, *self.read_only_paths):
            target = self._path_target(root, source)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir(): target.mkdir(parents=True, exist_ok=True)
            else: target.touch(exist_ok=True)

        for source in self._ETC_FILES:
            src = Path(source)
            if not src.exists(): continue
            target = self._path_target(root, src); target.parent.mkdir(parents=True, exist_ok=True); target.touch(exist_ok=True)

        for source in self._DEVICE_FILES:
            src = Path(source)
            if not src.exists(): continue
            target = self._path_target(root, src); target.parent.mkdir(parents=True, exist_ok=True); target.touch(exist_ok=True)

        (root / "tmp").mkdir(parents=True, exist_ok=True)
        (root / "vsh-tmp").mkdir(parents=True, exist_ok=True)
        directories = [p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()]
        for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True): directory.chmod(0o555)
        root.chmod(0o555)

    def _mount_specs(self) -> list[str]:
        specs: list[str] = []; seen: set[Path] = set()
        for source in (*self.runtime_read_only_paths, *self.read_only_paths):
            if source in seen: continue
            seen.add(source); specs.append(f"{source}::{source}")
        return specs

    def _unshare_argv_command(self, *, root: Path, workspace: Path, argv: list[str]) -> list[str]:
        available, found = self.required_commands_available()
        if not available:
            missing = [name for name, path in found.items() if not path]
            raise RuntimeError(f"missing Linux sandbox commands: {', '.join(missing)}")
        mount_specs = self._mount_specs()
        cmd = [found["unshare"] or "unshare", "--user", "--map-root-user", "--mount", "--pid", "--fork", "--kill-child=SIGKILL"]
        if self.network_policy == NetworkPolicy.DENY: cmd.append("--net")
        cmd.extend([
            found["sh"] or "/bin/sh", "-c", self._SETUP_SCRIPT, "vsh-setup",
            str(root), str(workspace), "rw" if self.workspace_writable else "ro",
            str(len(mount_specs)), *mount_specs, *argv,
        ])
        return cmd

    @staticmethod
    def _validate_argv(argv) -> list[str]:
        argv = list(argv)
        if not argv or any(not isinstance(item, str) or not item or "\x00" in item for item in argv):
            raise ValueError("argv must contain non-empty NUL-free strings")
        return argv

    def _validated_workspace(self, workspace: Path) -> Path:
        if platform.system() != "Linux": raise RuntimeError("Linux namespace sandbox is only available on Linux")
        workspace = Path(workspace).expanduser().resolve()
        if not workspace.exists() or not workspace.is_dir(): raise RuntimeError(f"workspace must be an existing directory: {workspace}")
        self._validate_ro_paths(workspace)
        self._validate_workspace_tree(workspace)
        return workspace

    def _run_argv_unchecked(self, *, workspace: Path, argv: list[str], timeout_seconds: float, env: dict[str, str] | None) -> ExecutionResult:
        try:
            workspace = self._validated_workspace(workspace)
            with tempfile.TemporaryDirectory(prefix="vsh-linuxns-root-") as td:
                root = Path(td).resolve(); self._prepare_root(root, workspace=workspace)
                proc = subprocess.run(
                    self._unshare_argv_command(root=root, workspace=workspace, argv=argv),
                    text=True, capture_output=True, timeout=timeout_seconds,
                    env=self._env(env, workspace=workspace),
                )
                return ExecutionResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired as exc:
            return ExecutionResult(124, exc.stdout or "", exc.stderr or "", timed_out=True)
        except Exception as exc:
            return ExecutionResult(126, "", f"sandbox setup failed: {type(exc).__name__}: {exc}")

    def _run_shell_unchecked(self, *, workspace: Path, command: str, timeout_seconds: float, env: dict[str, str] | None) -> ExecutionResult:
        if not isinstance(command, str) or not command.strip(): return ExecutionResult(2, "", "command must be a non-empty string")
        return self._run_argv_unchecked(
            workspace=Path(workspace), argv=["/bin/sh", "-c", command],
            timeout_seconds=timeout_seconds, env=env,
        )

    def run_argv(self, *, workspace, argv, timeout_seconds, env=None):
        try: argv = self._validate_argv(argv)
        except ValueError as exc: return ExecutionResult(2, "", str(exc))
        return self._run_argv_unchecked(workspace=Path(workspace), argv=argv, timeout_seconds=timeout_seconds, env=env)

    def run_shell(self, *, workspace, command, timeout_seconds, env=None):
        if not isinstance(command, str) or not command.strip(): return ExecutionResult(2, "", "command must be a non-empty string")
        return self._run_shell_unchecked(workspace=Path(workspace), command=command, timeout_seconds=timeout_seconds, env=env)

    def open_argv_session(self, *, workspace, argv, env=None):
        """Open a long-lived process inside the same namespace/chroot boundary.

        The TemporaryDirectory backing the chroot remains alive until session
        close; the returned PopenExecutionSession owns that cleanup lifecycle.
        """
        argv = self._validate_argv(argv)
        workspace = self._validated_workspace(Path(workspace))
        temp = tempfile.TemporaryDirectory(prefix="vsh-linuxns-session-root-")
        try:
            root = Path(temp.name).resolve(); self._prepare_root(root, workspace=workspace)
            proc = subprocess.Popen(
                self._unshare_argv_command(root=root, workspace=workspace, argv=argv),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=self._env(env, workspace=workspace), start_new_session=True,
            )
            return PopenExecutionSession(proc, cleanup=temp.cleanup)
        except Exception:
            temp.cleanup()
            raise
