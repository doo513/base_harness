#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one opt-in live harness evaluation case and print metrics.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--profile", choices=["software", "hackathon", "ctf", "demo"], required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--accept-command", action="append", default=[])
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--task-revision", required=True)
    parser.add_argument("--require-complete-provenance", action="store_true")
    args = parser.parse_args()

    command = [
        sys.executable,
        "-m",
        "harness.cli",
        "--config", args.config,
        "--workspace", args.workspace,
        "--run-dir", args.run_dir,
        "--profile", args.profile,
        "--goal", args.goal,
        "--max-steps", str(args.max_steps),
        "--task-revision", args.task_revision,
    ]
    for acceptance in args.accept_command:
        command.extend(["--accept-command", acceptance])
    if args.require_complete_provenance:
        command.append("--require-complete-provenance")

    completed = subprocess.run(command, text=True)
    run_dir = Path(args.run_dir).resolve()
    metrics_path = run_dir / "metrics.json"
    if metrics_path.exists():
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            metrics = {"error": "metrics.json is not valid JSON"}
        print(json.dumps({"run_dir": str(run_dir), "metrics": metrics}, ensure_ascii=False, sort_keys=True))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
