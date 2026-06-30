#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# ///
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import HarnessHookError, print_block, print_result, read_payload, require_mapping, text_field

SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "OpenAI-style key"),
    (re.compile(r"ghp_[A-Za-z0-9_]{20,}"), "GitHub token"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (
        re.compile(r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----"),
        "private key block",
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = require_mapping(read_payload(args.payload), "prompt payload")
        prompt = text_field(payload, "prompt")
    except HarnessHookError as exc:
        print_block("BLOCK_PROMPT", str(exc))
        return 2

    for pattern, label in SECRET_PATTERNS:
        if pattern.search(prompt):
            print_block("BLOCK_PROMPT", f"secret-like content detected: {label}")
            return 2

    print_result("OK_PROMPT", "prompt accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
