from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
from pathlib import Path

from harness.core.sandbox import LocalProcessBackend


def main():
    with tempfile.TemporaryDirectory(prefix="vsh-stage2-probe-") as td:
        root = Path(td); workspace = root / "workspace"; private = root / "private"
        workspace.mkdir(); private.mkdir()
        secret = private / "secret.txt"; secret.write_text("VSH_PRIVATE_CANARY", encoding="utf-8")
        backend = LocalProcessBackend(inherit_env=False); att = backend.isolation_attestation(workspace=workspace)
        fs = backend.run_shell(workspace=workspace, command=f"cat {secret}", timeout_seconds=5)
        os.environ["VSH_PARENT_SECRET"] = "PARENT_SECRET_CANARY"
        env = backend.run_shell(workspace=workspace, command="python -c \"import os;print(os.getenv('VSH_PARENT_SECRET','MISSING'))\"", timeout_seconds=5)
        listener = socket.socket(); listener.bind(("127.0.0.1", 0)); listener.listen(1); port = listener.getsockname()[1]; accepted = {"value": False}
        def serve():
            try:
                conn, _ = listener.accept(); accepted["value"] = True; conn.sendall(b"ok"); conn.close()
            finally: listener.close()
        t = threading.Thread(target=serve, daemon=True); t.start()
        net = backend.run_shell(workspace=workspace, command=("python -c \"import socket;" f"s=socket.create_connection(('127.0.0.1',{port}),2);print(s.recv(2).decode());s.close()\""), timeout_seconds=5)
        t.join(timeout=3)
        available = {name: shutil.which(name) for name in ("bwrap", "bubblewrap", "firejail", "docker", "podman", "nsjail", "unshare")}
        if available.get("unshare"):
            unshare = subprocess.run([available["unshare"], "--user", "--map-root-user", "--mount", "--pid", "--fork", "sh", "-c", "true"], text=True, capture_output=True)
            unshare_probe = {"returncode": unshare.returncode, "stderr": unshare.stderr.strip()}
        else: unshare_probe = {"returncode": None, "stderr": "not installed"}
        result = {
            "backend": backend.name,
            "declared_attestation": {"filesystem_isolated": att.filesystem_isolated, "network_isolated": att.network_isolated, "environment_sanitized": att.environment_sanitized, "source": att.source, "evidence": att.evidence},
            "filesystem_escape_probe": {"returncode": fs.returncode, "canary_leaked": "VSH_PRIVATE_CANARY" in fs.stdout},
            "environment_secret_probe": {"returncode": env.returncode, "stdout": env.stdout.strip(), "parent_secret_leaked": "PARENT_SECRET_CANARY" in env.stdout},
            "loopback_network_probe": {"returncode": net.returncode, "connection_accepted": accepted["value"], "stdout": net.stdout.strip()},
            "sandbox_tools_available": available,
            "unshare_user_mount_probe": unshare_probe,
        }
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__": main()
