from __future__ import annotations

import os
import platform
import socket
import tempfile
import threading
from pathlib import Path

from .sandbox_primitives import ExecutionResult, IsolationAttestation, NetworkPolicy


def probe_linux_namespace_backend(self) -> IsolationAttestation:
    available, commands = self.required_commands_available()
    if platform.system() != "Linux" or not available:
        return IsolationAttestation(
            filesystem_isolated=False,
            network_isolated=False,
            environment_sanitized=not self.inherit_env,
            source="runtime_probe_failed",
            evidence={
                "platform": platform.system(),
                "commands": commands,
                "reason": "required Linux sandbox primitives unavailable",
            },
        )

    with tempfile.TemporaryDirectory(prefix="vsh-linuxns-probe-") as td:
        root = Path(td)
        workspace = root / "workspace"
        private = root / "private"
        workspace.mkdir()
        private.mkdir()
        secret = private / "secret.txt"
        secret.write_text("VSH_NAMESPACE_PRIVATE_CANARY", encoding="utf-8")
        outside_write = private / "escape-write.txt"

        workspace_probe = self._run_shell_unchecked(
            workspace=workspace,
            command="printf VSH_WORKSPACE_OK > probe.txt && cat probe.txt",
            timeout_seconds=10,
            env=None,
        )
        fs_read = self._run_shell_unchecked(
            workspace=workspace,
            command=f"cat {secret}",
            timeout_seconds=10,
            env=None,
        )
        fs_write = self._run_shell_unchecked(
            workspace=workspace,
            command=f"printf escaped > {outside_write}",
            timeout_seconds=10,
            env=None,
        )
        rootfs_write = self._run_shell_unchecked(
            workspace=workspace,
            command="chmod u+w / 2>/dev/null; printf escaped > /vsh-rootfs-escape",
            timeout_seconds=10,
            env=None,
        )

        env_name = "VSH_NAMESPACE_PARENT_SECRET"
        old_env = os.environ.get(env_name)
        os.environ[env_name] = "VSH_NAMESPACE_ENV_CANARY"
        try:
            env_probe = self._run_shell_unchecked(
                workspace=workspace,
                command=(
                    "/usr/bin/python3 -c \"import os;"
                    f"print(os.getenv('{env_name}','MISSING'))\""
                ),
                timeout_seconds=10,
                env=None,
            )
        finally:
            if old_env is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = old_env

        network_result: ExecutionResult | None = None
        accepted = {"value": False}
        listener_error: str | None = None
        if self.network_policy == NetworkPolicy.DENY:
            listener = socket.socket()
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(3)
            port = listener.getsockname()[1]

            def serve() -> None:
                nonlocal listener_error
                try:
                    conn, _ = listener.accept()
                    accepted["value"] = True
                    conn.close()
                except TimeoutError:
                    pass
                except OSError as exc:
                    listener_error = f"{type(exc).__name__}: {exc}"
                finally:
                    listener.close()

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            network_result = self._run_shell_unchecked(
                workspace=workspace,
                command=(
                    "/usr/bin/python3 -c \"import socket;"
                    f"socket.create_connection(('127.0.0.1',{port}),1)\""
                ),
                timeout_seconds=5,
                env=None,
            )
            thread.join(timeout=4)

        workspace_behavior_ok = (
            (workspace_probe.returncode == 0 and "VSH_WORKSPACE_OK" in workspace_probe.stdout)
            if self.workspace_writable
            else workspace_probe.returncode != 0
        )
        filesystem_isolated = (
            workspace_behavior_ok
            and "VSH_NAMESPACE_PRIVATE_CANARY" not in fs_read.stdout
            and not outside_write.exists()
            and fs_write.returncode != 0
            and rootfs_write.returncode != 0
        )
        environment_sanitized = (
            not self.inherit_env
            and "VSH_NAMESPACE_ENV_CANARY" not in env_probe.stdout
            and env_probe.stdout.strip() == "MISSING"
        )
        network_isolated = False
        if self.network_policy == NetworkPolicy.DENY and network_result is not None:
            network_isolated = network_result.returncode != 0 and not accepted["value"]

        source = (
            "runtime_probe"
            if filesystem_isolated
            and environment_sanitized
            and (self.network_policy != NetworkPolicy.DENY or network_isolated)
            else "runtime_probe_failed"
        )
        return IsolationAttestation(
            filesystem_isolated=filesystem_isolated,
            network_isolated=network_isolated,
            environment_sanitized=environment_sanitized,
            source=source,
            evidence={
                "platform": platform.system(),
                "commands": commands,
                "network_policy": self.network_policy.value,
                "workspace_writable": self.workspace_writable,
                "workspace_probe_returncode": workspace_probe.returncode,
                "filesystem_read_escape_returncode": fs_read.returncode,
                "filesystem_canary_leaked": "VSH_NAMESPACE_PRIVATE_CANARY" in fs_read.stdout,
                "filesystem_write_escape_returncode": fs_write.returncode,
                "filesystem_write_escape_created": outside_write.exists(),
                "rootfs_chmod_write_escape_returncode": rootfs_write.returncode,
                "environment_probe_returncode": env_probe.returncode,
                "environment_secret_leaked": "VSH_NAMESPACE_ENV_CANARY" in env_probe.stdout,
                "loopback_returncode": (
                    network_result.returncode if network_result is not None else None
                ),
                "loopback_connection_accepted": accepted["value"],
                "loopback_listener_error": listener_error,
                "runtime_read_only_paths": [str(p) for p in self.runtime_read_only_paths],
                "extra_read_only_paths": [str(p) for p in self.read_only_paths],
                "filesystem_model": (
                    self._FULL_WORKSPACE_RIGHTS_NOTE
                    if self.workspace_writable
                    else "candidate workspace and runtime mounts are read-only; unrelated host paths are absent"
                ),
            },
        )

