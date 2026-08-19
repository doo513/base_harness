#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from harness.evaluation import MatchedAblationReport, load_evaluation_records


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate matched controls and summarize harness ablation records.")
    parser.add_argument("records", help="JSONL file containing evaluation-record-v1 objects")
    args = parser.parse_args()
    report = MatchedAblationReport(load_evaluation_records(args.records)).summarize()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
