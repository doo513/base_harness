#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# ///
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import (
    HarnessHookError,
    JsonValue,
    print_block,
    read_json_file,
    require_list,
    require_mapping,
    text_field,
)

DONE_STATUSES = {"done", "complete", "completed", "cancelled", "canceled", "skipped"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path("state/task-state.json"))
    return parser.parse_args()


def evidence_present(value: JsonValue) -> bool:
    return isinstance(value, list) and len(value) > 0


def missing_evidence_goal_ids(state_path: Path) -> list[str]:
    if not state_path.exists():
        return []
    try:
        state_data = read_json_file(state_path)
        if not isinstance(state_data, dict):
            return []
        goals = state_data.get("goals")
        if not isinstance(goals, list):
            return []
    except Exception:
        return []

    missing: list[str] = []
    for index, goal_value in enumerate(goals):
        if not isinstance(goal_value, dict):
            continue
        goal_id = goal_value.get("id")
        status = goal_value.get("status")
        if not isinstance(goal_id, str) or not isinstance(status, str):
            continue
        if status not in DONE_STATUSES and not evidence_present(goal_value.get("evidence")):
            missing.append(goal_id)
    return missing


def main() -> int:
    args = parse_args()
    try:
        missing = missing_evidence_goal_ids(args.state)
    except HarnessHookError as exc:
        print_block("BLOCK_STOP", str(exc))
        return 2

    if missing:
        print_block("BLOCK_STOP", f"unfinished goals missing evidence: {', '.join(missing)}")
        return 2

    print(json.dumps({"continue": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
