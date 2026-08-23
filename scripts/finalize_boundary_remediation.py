from __future__ import annotations

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    required = (
        ROOT / "src" / "harness" / "project_memory_v2.py",
        ROOT / "src" / "harness" / "core" / "runtime_memory.py",
        ROOT / "tests" / "test_p2_memory_v2.py",
        ROOT / "docs" / "tracks" / "integration-runtime" / "P2_MEMORY_A_D_IMPLEMENTATION_REPORT.md",
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("P2 memory output is incomplete: " + ", ".join(missing))

    for relative in (
        "scripts/apply_p2_memory.py",
        "scripts/apply_p2_meta_review.py",
        ".github/workflows/p2-memory-a-d.yml",
        ".github/workflows/p2-memory-meta-review.yml",
    ):
        path = ROOT / relative
        path.unlink(missing_ok=True)

    payload = ROOT / "scripts" / "p2_memory_payload"
    if payload.exists():
        shutil.rmtree(payload)


if __name__ == "__main__":
    main()
