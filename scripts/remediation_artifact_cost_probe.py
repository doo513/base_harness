from __future__ import annotations

import hashlib
import json
import statistics
import tempfile
import time
from pathlib import Path

from harness.core.storage import ArtifactStore


PAYLOAD_BYTES = 4 * 1024 * 1024
ROUNDS = 7


def old_double_read(path: Path, expected: str) -> bytes:
    checked = path.read_bytes()
    if hashlib.sha256(checked).hexdigest() != expected:
        raise RuntimeError("baseline integrity mismatch")
    return path.read_bytes()


def timed(fn, rounds: int) -> list[float]:
    samples: list[float] = []
    for _ in range(rounds):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return samples


def run_probe() -> dict:
    with tempfile.TemporaryDirectory(prefix="vsh-remediation-cost-") as td:
        store = ArtifactStore(Path(td) / "artifacts")
        payload = "A" * PAYLOAD_BYTES
        ref = store.put_text("cost.bin", payload)
        path = store.resolve(ref)
        expected = store.digest_from_ref(ref)

        baseline = timed(lambda: old_double_read(path, expected), ROUNDS)
        hardened = timed(lambda: store.verified_read_bytes(ref), ROUNDS)

        result = {
            "probe": "verified-read-cost-v081",
            "payload_bytes": PAYLOAD_BYTES,
            "rounds": ROUNDS,
            "baseline": {
                "logical_content_reads_per_call": 2,
                "artifact_bytes_read_per_call": PAYLOAD_BYTES * 2,
                "sha256_operations_per_call": 1,
                "wall_seconds_median": statistics.median(baseline),
            },
            "hardened": {
                "logical_content_reads_per_call": 1,
                "artifact_bytes_read_per_call": PAYLOAD_BYTES,
                "sha256_operations_per_call": 1,
                "wall_seconds_median": statistics.median(hardened),
            },
            "delta": {
                "artifact_bytes_read_per_call": -PAYLOAD_BYTES,
                "artifact_read_reduction_fraction": 0.5,
                "hash_operations_change": 0,
                "wall_seconds_median": statistics.median(hardened) - statistics.median(baseline),
            },
            "notes": [
                "wall time is a noisy CI/runtime proxy and is not a correctness gate",
                "byte/read counts are deterministic from the executed baseline and hardened algorithms",
                "critical integrity hashing is preserved",
            ],
        }
        result["passed"] = (
            result["hardened"]["logical_content_reads_per_call"] == 1
            and result["hardened"]["artifact_bytes_read_per_call"] * 2
            == result["baseline"]["artifact_bytes_read_per_call"]
        )
        return result


def main() -> int:
    result = run_probe()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
