from __future__ import annotations

from pathlib import Path

from .linux_namespace_config import LinuxNamespaceConfigMixin
from .linux_namespace_exec import LinuxNamespaceExecutionMixin
from .linux_namespace_setup import SETUP_SCRIPT
from .sandbox_primitives import IsolationAttestation


class LinuxNamespaceSandboxBackend(LinuxNamespaceConfigMixin, LinuxNamespaceExecutionMixin):
    """Production Linux sandbox using user/mount/PID/network namespaces + chroot.

    Actor workspaces are the only writable host-backed path. Runtime/oracle
    mounts are read-only, unrelated host paths are absent, capabilities are
    dropped, and DENY mode uses a fresh network namespace. Strong isolation is
    accepted only after a live runtime probe succeeds.
    """

    name = "linux_namespace"
    _REQUIRED_COMMANDS = ("unshare", "mount", "chroot", "setpriv", "sh")
    _ETC_FILES = (
        "/etc/ld.so.cache", "/etc/ld.so.conf", "/etc/passwd", "/etc/group",
        "/etc/nsswitch.conf", "/etc/hosts", "/etc/resolv.conf",
    )
    _DEVICE_FILES = ("/dev/null", "/dev/urandom", "/dev/random")
    _FULL_WORKSPACE_RIGHTS_NOTE = (
        "workspace bind mount is writable; sandbox root/runtime mounts are read-only/immutable"
    )
    _SETUP_SCRIPT = SETUP_SCRIPT

    def _live_probe(self) -> IsolationAttestation:
        from .linux_namespace_probe import probe_linux_namespace_backend
        return probe_linux_namespace_backend(self)

    def isolation_attestation(self, *, workspace):
        if self._attestation_cache is None:
            self._attestation_cache = self._live_probe()
        return self._attestation_cache
