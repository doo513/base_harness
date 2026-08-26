from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, choices=("windows-x64", "linux-x64"))
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    runtime = repo / "runtime"
    output = runtime / "dist" / args.target
    name = "base-harness-verifier.exe" if args.target == "windows-x64" else "base-harness-verifier"
    work = runtime / ".verifier-build" / args.target
    dist = work / "dist"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "base-harness-verifier",
        "--paths",
        str(repo / "src"),
        "--distpath",
        str(dist),
        "--workpath",
        str(work / "work"),
        "--specpath",
        str(work),
        str(repo / "src" / "harness" / "verified_sidecar.py"),
    ]
    subprocess.run(command, cwd=repo, check=True)
    built = dist / name
    if not built.is_file():
        raise FileNotFoundError(built)
    shutil.copy2(built, output / name)

    archive = runtime / "dist" / ("base-harness-" + args.target)
    shutil.make_archive(str(archive), "zip", output)
    print(str(archive) + ".zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
