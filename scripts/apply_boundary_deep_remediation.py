from __future__ import annotations

from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    applicator = ROOT / "scripts" / "apply_p2_memory.py"
    if not applicator.is_file():
        raise RuntimeError("P2 memory applicator is missing")
    runpy.run_path(str(applicator), run_name="__main__")


if __name__ == "__main__":
    main()
