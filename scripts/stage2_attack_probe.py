from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import tempfile
import threading
from pathlib import Path
from typing import Any

from harness.core.oracles import SealedAssetBundle
from harness.core.sandbox import LinuxNamespaceSandboxBackend, NetworkPolicy


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _record(result, **extra: Any) -> dict[str, Any]:
    data = {"returncode": result.returncode, "timed_out": result.timed_out, "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}
    data.update(extra)
    return data


def _run_probe() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="vsh-stage2-rc2-probe-") as td:
        root = Path(td).resolve()
        workspace = root / "workspace"; outside = root / "outside"; harness_private = root / "harness-private"; sealed_root = root / "sealed-oracle"
        for p in (workspace, outside, harness_private, sealed_root): p.mkdir()
        (workspace / "work.txt").write_text("WORKSPACE_BASELINE\n", encoding="utf-8")
        outside_secret = outside / "secret.txt"; outside_secret.write_text("VSH_OUTSIDE_CANARY\n", encoding="utf-8")
        harness_secret = harness_private / "run-secret.txt"; harness_secret.write_text("VSH_HARNESS_PRIVATE_CANARY\n", encoding="utf-8")
        sealed_asset = sealed_root / "acceptance.txt"; sealed_asset.write_text("VSH_SEALED_ORACLE_CANARY\n", encoding="utf-8")
        seal = SealedAssetBundle(sealed_root)
        symlink = workspace / "escape-link"; symlink.symlink_to(outside_secret)

        actor = LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY, workspace_writable=True)
        att = actor.isolation_attestation(workspace=workspace)
        probes: dict[str, dict[str, Any]] = {}

        r = actor.run_shell(workspace=workspace, command="printf ACTOR_WRITE_OK > actor-created.txt && cat actor-created.txt", timeout_seconds=10)
        probes["workspace_write_control"] = _record(r, passed=(r.returncode == 0 and (workspace / "actor-created.txt").read_text(encoding="utf-8") == "ACTOR_WRITE_OK"))

        r = actor.run_shell(workspace=workspace, command="cat ../outside/secret.txt", timeout_seconds=10)
        probes["01_path_traversal"] = _record(r, passed=r.returncode != 0 and "VSH_OUTSIDE_CANARY" not in r.stdout)
        r = actor.run_shell(workspace=workspace, command=f"cat {outside_secret}", timeout_seconds=10)
        probes["02_absolute_read_outside_workspace"] = _record(r, passed=r.returncode != 0 and "VSH_OUTSIDE_CANARY" not in r.stdout)
        outside_write = outside / "actor-write.txt"
        r = actor.run_shell(workspace=workspace, command=f"printf escaped > {outside_write}", timeout_seconds=10)
        probes["03_absolute_write_outside_workspace"] = _record(r, passed=r.returncode != 0 and not outside_write.exists(), host_file_created=outside_write.exists())
        r = actor.run_shell(workspace=workspace, command=f"cat {harness_secret}", timeout_seconds=10)
        probes["04_harness_private_read"] = _record(r, passed=r.returncode != 0 and "VSH_HARNESS_PRIVATE_CANARY" not in r.stdout)
        harness_write = harness_private / "actor-write.txt"
        r = actor.run_shell(workspace=workspace, command=f"printf escaped > {harness_write}", timeout_seconds=10)
        probes["05_harness_private_write"] = _record(r, passed=r.returncode != 0 and not harness_write.exists(), host_file_created=harness_write.exists())
        r = actor.run_shell(workspace=workspace, command=f"cat {sealed_asset}", timeout_seconds=10)
        probes["06_sealed_oracle_read"] = _record(r, passed=r.returncode != 0 and "VSH_SEALED_ORACLE_CANARY" not in r.stdout)
        r = actor.run_shell(workspace=workspace, command="cat escape-link", timeout_seconds=10)
        probes["07_symlink_escape"] = _record(r, passed=r.returncode != 0 and "VSH_OUTSIDE_CANARY" not in r.stdout)

        listener = socket.socket(); listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); listener.bind(("127.0.0.1", 0)); listener.listen(1); listener.settimeout(3)
        port = listener.getsockname()[1]; accepted = {"value": False}
        def serve() -> None:
            try:
                conn, _ = listener.accept(); accepted["value"] = True; conn.close()
            except (TimeoutError, OSError): pass
            finally: listener.close()
        thread = threading.Thread(target=serve, daemon=True); thread.start()
        r = actor.run_shell(workspace=workspace, command=("/usr/bin/python3 -c \"import socket;" f"socket.create_connection(('127.0.0.1',{port}),1)\""), timeout_seconds=5)
        thread.join(timeout=4)
        probes["08_loopback_connection"] = _record(r, passed=r.returncode != 0 and not accepted["value"], host_listener_accepted=accepted["value"])

        r = actor.run_shell(workspace=workspace, command="/usr/bin/python3 -c \"import socket;socket.create_connection(('1.1.1.1',53),1)\"", timeout_seconds=5)
        probes["09_external_network_connection"] = _record(r, passed=r.returncode != 0, target="1.1.1.1:53", note="fresh network namespace has no usable external interface; failure is local namespace enforcement")

        parent_secret_name = "VSH_STAGE2_PARENT_SECRET"; old = os.environ.get(parent_secret_name); os.environ[parent_secret_name] = "VSH_PARENT_ENV_CANARY"
        try:
            r = actor.run_shell(workspace=workspace, command=("/usr/bin/python3 -c \"import os;" f"print(os.getenv('{parent_secret_name}','MISSING'))\""), timeout_seconds=10)
        finally:
            if old is None: os.environ.pop(parent_secret_name, None)
            else: os.environ[parent_secret_name] = old
        probes["10_environment_secret_inheritance"] = _record(r, passed=r.returncode == 0 and r.stdout.strip() == "MISSING", parent_secret_leaked="VSH_PARENT_ENV_CANARY" in r.stdout)

        verifier = LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY, workspace_writable=False)
        verifier_target = workspace / "verifier-write.txt"
        r = verifier.run_shell(workspace=workspace, command=("printf VSH_VERIFIER_SCRATCH > $TMPDIR/verifier-scratch.txt && cat $TMPDIR/verifier-scratch.txt && " f"printf verifier > {verifier_target}"), timeout_seconds=10)
        probes["11_verifier_write_attempt"] = _record(r, passed=(r.returncode != 0 and not verifier_target.exists() and "VSH_VERIFIER_SCRATCH" in r.stdout), candidate_mutated=verifier_target.exists(), ephemeral_scratch_available="VSH_VERIFIER_SCRATCH" in r.stdout, boundary="subprocess verifier backend with read-only candidate workspace and namespace-local scratch")

        oracle = LinuxNamespaceSandboxBackend(network_policy=NetworkPolicy.DENY, workspace_writable=False, read_only_paths=[sealed_root])
        sealed_hash_before = _sha256(sealed_asset)
        oracle_read = oracle.run_shell(workspace=workspace, command=f"cat {sealed_asset}", timeout_seconds=10)
        r = oracle.run_shell(workspace=workspace, command=f"printf tamper >> {sealed_asset}", timeout_seconds=10)
        sealed_hash_after = _sha256(sealed_asset); seal_after = seal.verify_unchanged()
        probes["12_oracle_asset_mutation_attempt"] = _record(r, passed=(oracle_read.returncode == 0 and "VSH_SEALED_ORACLE_CANARY" in oracle_read.stdout and r.returncode != 0 and sealed_hash_before == sealed_hash_after and seal_after.ok), oracle_read_returncode=oracle_read.returncode, oracle_can_read_sealed_asset="VSH_SEALED_ORACLE_CANARY" in oracle_read.stdout, sealed_hash_before=sealed_hash_before, sealed_hash_after=sealed_hash_after, sealed_manifest_unchanged=seal_after.ok)

        rootfs_escape = actor.run_shell(workspace=workspace, command="chmod u+w /; printf escaped > /rootfs-escape", timeout_seconds=10)
        probes["13_rootfs_chmod_escape"] = _record(rootfs_escape, passed=rootfs_escape.returncode != 0, note="defense-in-depth probe for owner-chmod bypass of the chroot skeleton")
        nested_userns = actor.run_shell(workspace=workspace, command="unshare --user --map-root-user --mount /bin/sh -c 'mount -o remount,rw / && printf escaped > /tmp/nested-userns-escape'", timeout_seconds=10)
        probes["14_nested_userns_remount_escape"] = _record(nested_userns, passed=nested_userns.returncode != 0, note="defense-in-depth probe; child must not remount the parent-owned sandbox root writable")

        unix_socket_path = workspace / "host-channel.sock"; unix_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); unix_listener.bind(str(unix_socket_path)); unix_listener.listen(1); unix_listener.settimeout(2); unix_accepted = {"value": False}
        def serve_unix() -> None:
            try:
                conn, _ = unix_listener.accept(); unix_accepted["value"] = True; conn.close()
            except (TimeoutError, OSError): pass
            finally: unix_listener.close()
        unix_thread = threading.Thread(target=serve_unix, daemon=True); unix_thread.start()
        unix_result = actor.run_shell(workspace=workspace, command="/usr/bin/python3 -c \"import socket;s=socket.socket(socket.AF_UNIX);s.connect('host-channel.sock')\"", timeout_seconds=5)
        unix_thread.join(timeout=3)
        probes["15_workspace_unix_socket_channel"] = _record(unix_result, passed=(unix_result.returncode != 0 and "unsafe workspace special file" in unix_result.stderr and not unix_accepted["value"]), host_listener_accepted=unix_accepted["value"], note="preflight blocks AF_UNIX host channel preserved by a bind-mounted workspace")
        unix_socket_path.unlink(missing_ok=True)

        hardlink_escape = workspace / "hardlink-escape"; hardlink_escape.hardlink_to(outside_secret)
        hardlink_result = actor.run_shell(workspace=workspace, command="cat hardlink-escape", timeout_seconds=5)
        probes["16_external_hardlink_escape"] = _record(hardlink_result, passed=(hardlink_result.returncode != 0 and "hard links outside the workspace" in hardlink_result.stderr and "VSH_OUTSIDE_CANARY" not in hardlink_result.stdout), note="preflight rejects regular-file inodes whose full hard-link set is not contained in workspace")
        hardlink_escape.unlink(missing_ok=True)

        required = ["01_path_traversal", "02_absolute_read_outside_workspace", "03_absolute_write_outside_workspace", "04_harness_private_read", "05_harness_private_write", "06_sealed_oracle_read", "07_symlink_escape", "08_loopback_connection", "09_external_network_connection", "10_environment_secret_inheritance", "11_verifier_write_attempt", "12_oracle_asset_mutation_attempt"]
        required_pass = all(probes[name]["passed"] for name in required); positive_control_pass = probes["workspace_write_control"]["passed"]
        attestation_pass = (att.source == "runtime_probe" and att.filesystem_isolated and att.network_isolated and att.environment_sanitized)
        return {"probe_version": "stage2-rc2", "backend": actor.name, "attestation": {"filesystem_isolated": att.filesystem_isolated, "network_isolated": att.network_isolated, "environment_sanitized": att.environment_sanitized, "source": att.source, "evidence": att.evidence}, "probes": probes, "summary": {"required_probe_count": len(required), "required_pass_count": sum(1 for name in required if probes[name]["passed"]), "required_attacks_blocked": required_pass, "workspace_positive_control": positive_control_pass, "runtime_attestation_pass": attestation_pass, "defense_in_depth_pass": (probes["13_rootfs_chmod_escape"]["passed"] and probes["14_nested_userns_remount_escape"]["passed"] and probes["15_workspace_unix_socket_channel"]["passed"] and probes["16_external_hardlink_escape"]["passed"]), "stage2_runtime_boundary_pass": (required_pass and positive_control_pass and attestation_pass and probes["13_rootfs_chmod_escape"]["passed"] and probes["14_nested_userns_remount_escape"]["passed"] and probes["15_workspace_unix_socket_channel"]["passed"] and probes["16_external_hardlink_escape"]["passed"])}, "scope_note": "Verifier write probe covers verifier subprocesses launched through the read-only namespace backend. Built-in in-process verifier code remains part of the trusted harness computing base."}


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 02 rc2 real sandbox attack probe"); parser.add_argument("--output", help="Optional JSON evidence path"); args = parser.parse_args()
    result = _run_probe(); text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["summary"]["stage2_runtime_boundary_pass"] else 1


if __name__ == "__main__": raise SystemExit(main())
