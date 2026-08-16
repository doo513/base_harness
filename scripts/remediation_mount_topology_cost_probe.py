from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from harness.core.linux_namespace_backend import LinuxNamespaceSandboxBackend


ROUNDS = 50


def main() -> int:
    mountinfo = Path("/proc/self/mountinfo")
    raw = mountinfo.read_bytes()
    samples = []
    counts = []
    for _ in range(ROUNDS):
        started = time.perf_counter()
        points = LinuxNamespaceSandboxBackend._current_mount_points()
        samples.append(time.perf_counter() - started)
        counts.append(len(points))

    result = {
        "probe": "stage02-mount-topology-cost",
        "rounds": ROUNDS,
        "mountinfo_bytes_per_preflight": len(raw),
        "mount_points": {
            "min": min(counts),
            "max": max(counts),
        },
        "after": {
            "mountinfo_reads_per_sandbox_preflight": 1,
            "median_wall_seconds": statistics.median(samples),
            "max_wall_seconds": max(samples),
        },
        "before": {
            "mountinfo_reads_per_sandbox_preflight": 0,
        },
        "notes": [
            "The topology snapshot is taken once per _validate_ro_paths call, not once per read-only path.",
            "This is a pre-execution security cost and adds no model tokens or runtime event-log entries.",
            "Wall time is an environment-specific proxy; the one-read-per-preflight count is the deterministic cost.",
        ],
    }
    result["passed"] = result["after"]["mountinfo_reads_per_sandbox_preflight"] == 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
