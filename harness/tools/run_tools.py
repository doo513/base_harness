from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from harness.core.context_budget import BudgetInput, resolve_budget, truncate_text
from harness.core.types import JsonObject

BLOCK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brm\s+-[^\s]*r[^\s]*f[^\s]*(\s+--)?\s+(/|\.)(\s|$)"),
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+clean\s+-[^\s]*f[^\s]*d[^\s]*x\b"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\b(curl|wget)\b.+\|\s*(sh|bash)\b"),
)


def _argv(command: str | Sequence[str]) -> list[str]:
    if isinstance(command, str):
        return shlex.split(command)
    return [str(part) for part in command]


def _command_text(command: str | Sequence[str]) -> str:
    if isinstance(command, str):
        return command
    return " ".join(shlex.quote(str(part)) for part in command)


def _blocked(command: str | Sequence[str]) -> bool:
    text = _command_text(command)
    return any(pattern.search(text) for pattern in BLOCK_PATTERNS)


def _timeout_output_text(value: str | bytes | None) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return ""


def run_command(command: str | Sequence[str], timeout: int = 30, budget: BudgetInput = None) -> JsonObject:
    resolved_budget = resolve_budget(budget)
    if _blocked(command):
        return {
            "command": _command_text(command),
            "executed": False,
            "status": "blocked",
            "returncode": None,
            "stdout": "",
            "stderr": "destructive command blocked",
            "truncated": False,
        }
    try:
        result = subprocess.run(
            _argv(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _timeout_output_text(exc.stdout)
        stderr = _timeout_output_text(exc.stderr)
        limited_stdout = truncate_text(stdout, resolved_budget.max_tool_result_chars)
        limited_stderr = truncate_text(stderr, resolved_budget.max_tool_result_chars)
        return {
            "command": _command_text(command),
            "executed": True,
            "status": "timeout",
            "returncode": None,
            "stdout": limited_stdout["value"],
            "stderr": limited_stderr["value"],
            "stdout_truncated": limited_stdout["truncated"],
            "stderr_truncated": limited_stderr["truncated"],
            "truncated": limited_stdout["truncated"] or limited_stderr["truncated"],
        }
    except FileNotFoundError as exc:
        return {
            "command": _command_text(command),
            "executed": False,
            "status": "not_found",
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "truncated": False,
        }

    limited_stdout = truncate_text(result.stdout, resolved_budget.max_tool_result_chars)
    limited_stderr = truncate_text(result.stderr, resolved_budget.max_tool_result_chars)
    return {
        "command": _command_text(command),
        "executed": True,
        "status": "completed",
        "returncode": result.returncode,
        "stdout": limited_stdout["value"],
        "stderr": limited_stderr["value"],
        "stdout_truncated": limited_stdout["truncated"],
        "stderr_truncated": limited_stderr["truncated"],
        "truncated": limited_stdout["truncated"] or limited_stderr["truncated"],
    }


def run_python(
    script_path: str | Path,
    args: Sequence[str] | None = None,
    timeout: int = 30,
    budget: BudgetInput = None,
) -> JsonObject:
    command = [sys.executable, str(script_path), *(args or ())]
    return run_command(command, timeout=timeout, budget=budget)
