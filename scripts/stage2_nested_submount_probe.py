from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from harness.core.linux_namespace_backend import LinuxNamespaceSandboxBackend


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def inside_probe() -> dict:
    if os.geteuid() != 0:
        raise RuntimeError("inside probe requires root")

    with tempfile.TemporaryDirectory(prefix="vsh-nested-submount-") as td:
        base = Path(td)
        source = base / "source"
        nested = source / "nested-mount"
        target = base / "target"
        workspace = base / "workspace"
        source.mkdir()
        nested.mkdir()
        target.mkdir()
        workspace.mkdir()

        run(["mount", "--make-rprivate", "/"])
        run(["mount", "-t", "tmpfs", "tmpfs", str(nested)])
        (nested / "canary").write_text("ORIGINAL", encoding="utf-8")

        raw_descendant_writable = False
        raw_host_canary_changed = False
        raw_error = ""
        try:
            run(["mount", "--rbind", str(source), str(target)])
            run(["mount", "--make-rslave", str(target)])
            run(["mount", "-o", "remount,bind,ro", str(target)])
            try:
                (target / "nested-mount" / "canary").write_text("RAW_MUTATED", encoding="utf-8")
                raw_descendant_writable = True
            except OSError as exc:
                raw_error = f"{type(exc).__name__}: {exc}"
            raw_host_canary_changed = (nested / "canary").read_text(encoding="utf-8") == "RAW_MUTATED"
        finally:
            subprocess.run(["umount", "-R", str(target)], text=True, capture_output=True)

        # Restore the nested source canary before testing the Harness defense.
        (nested / "canary").write_text("ORIGINAL", encoding="utf-8")

        backend = LinuxNamespaceSandboxBackend(
            read_only_paths=[source],
            runtime_read_only_paths=(),
        )
        preflight_blocked = False
        preflight_error = ""
        try:
            backend._validate_ro_paths(workspace)
        except Exception as exc:
            preflight_blocked = True
            preflight_error = f"{type(exc).__name__}: {exc}"

        actual_result = None
        actual_escape = False
        if not preflight_blocked:
            command = f"printf SANDBOX_MUTATED > '{source}/nested-mount/canary'"
            result = backend.run_shell(
                workspace=workspace,
                command=command,
                timeout_seconds=20,
                env=None,
            )
            actual_result = {
                "returncode": result.returncode,
                "stderr": result.stderr,
                "stdout": result.stdout,
            }
            actual_escape = (nested / "canary").read_text(encoding="utf-8") == "SANDBOX_MUTATED"

        subprocess.run(["umount", str(nested)], text=True, capture_output=True)

        raw_semantics_confirmed = raw_descendant_writable and raw_host_canary_changed
        defense_ok = preflight_blocked and not actual_escape
        result = {
            "stage": "02-remediation",
            "probe": "nested-read-only-submount",
            "environment": {
                "uid": os.geteuid(),
                "mount": shutil.which("mount"),
                "unshare": shutil.which("unshare"),
            },
            "raw_mount_semantics": {
                "top_level_rbind_remount_ro_descendant_writable": raw_descendant_writable,
                "source_canary_changed_through_descendant": raw_host_canary_changed,
                "error": raw_error,
            },
            "harness_defense": {
                "preflight_blocked_nested_read_only_source": preflight_blocked,
                "preflight_error": preflight_error,
                "actual_backend_attempt": actual_result,
                "actual_escape_observed": actual_escape,
            },
            "summary": {
                "raw_semantics_confirmed": raw_semantics_confirmed,
                "defense_ok": defense_ok,
                "all_passed": raw_semantics_confirmed and defense_ok,
            },
        }
        return result


def outer() -> int:
    if sys.platform != "linux":
        print(json.dumps({"supported": False, "reason": "linux required"}, indent=2))
        return 2
    if not shutil.which("sudo") or not shutil.which("unshare"):
        print(json.dumps({"supported": False, "reason": "sudo/unshare required"}, indent=2))
        return 2

    cmd = [
        "sudo", "-n", "-E",
        "unshare", "--mount", "--fork",
        sys.executable, str(Path(__file__).resolve()), "--inside",
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    return proc.returncode


def main() -> int:
    if "--inside" in sys.argv:
        try:
            result = inside_probe()
        except Exception as exc:
            print(json.dumps({
                "stage": "02-remediation",
                "probe": "nested-read-only-submount",
                "supported": False,
                "error": f"{type(exc).__name__}: {exc}",
            }, indent=2, sort_keys=True))
            return 2
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["summary"]["all_passed"] else 1
    return outer()


if __name__ == "__main__":
    raise SystemExit(main())
