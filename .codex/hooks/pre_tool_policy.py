#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# ///
from __future__ import annotations

import argparse
import re
import shlex
from pathlib import Path

from common import HarnessHookError, JsonValue, print_block, print_result, read_payload, require_mapping, text_field

PIPE_SHELL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:[\w./-]+/)?(?:sh|bash|dash|zsh|ksh)\b"), "download pipe shell"),
    (re.compile(r"\b(?:[\w./-]+/)?(?:sh|bash|dash|zsh|ksh)\s+-\w*c\w*\s+[\"']?\$?\(?\s*(?:curl|wget)\b"), "shell executes downloader"),
)
CONTROL_TOKENS = {"&&", "||", ";", "|"}
SHELL_COMMANDS = {"sh", "bash", "dash", "zsh", "ksh"}
GIT_OPTION_ARG_NAMES = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path)
    return parser.parse_args()

def shell_tokens(command: str) -> list[str]:
    normalized = re.sub(r"(&&|\|\||[;|])", r" \1 ", command)
    try:
        return shlex.split(normalized)
    except ValueError:
        return normalized.split()

def command_segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in CONTROL_TOKENS:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments

def option_letters(token: str) -> set[str]:
    if not token.startswith("-") or token.startswith("--"):
        return set()
    return set(token[1:])

def command_name(token: str) -> str:
    return token.rsplit("/", 1)[-1]

def has_option(tokens: list[str], short: str, long_name: str) -> bool:
    return long_name in tokens or any(short in option_letters(token) for token in tokens)

def drop_sudo(tokens: list[str]) -> list[str]:
    index = 1
    options_with_args = {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "--close-from"}
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return tokens[index + 1 :]
        if not token.startswith("-"):
            return tokens[index:]
        index += 2 if token in options_with_args and index + 1 < len(tokens) else 1
    return []

def drop_env(tokens: list[str]) -> list[str]:
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            return tokens[index + 1 :]
        if token.startswith("-") or ("=" in token and not token.startswith("=")):
            index += 1
            continue
        return tokens[index:]
    return []

def strip_wrappers(tokens: list[str]) -> list[str]:
    current = tokens
    while current:
        name = command_name(current[0])
        if name == "sudo":
            current = drop_sudo(current)
        elif name == "env":
            current = drop_env(current)
        elif name == "command":
            current = current[1:]
        else:
            return current
    return current

def nested_shell_script(tokens: list[str]) -> str | None:
    if not tokens or command_name(tokens[0]) not in SHELL_COMMANDS:
        return None
    for index, token in enumerate(tokens[1:], start=1):
        if token == "-c" or (token.startswith("-") and not token.startswith("--") and "c" in token[1:]):
            return tokens[index + 1] if index + 1 < len(tokens) else ""
    return None

def git_parts(tokens: list[str]) -> tuple[str, list[str]]:
    if not tokens or command_name(tokens[0]) != "git":
        return "", []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--":
            index += 1
            break
        if token in GIT_OPTION_ARG_NAMES:
            index += 2
        elif any(token.startswith(name + "=") for name in GIT_OPTION_ARG_NAMES):
            index += 1
        elif token.startswith("-"):
            index += 1
        else:
            break
    if index >= len(tokens):
        return "", []
    return tokens[index], tokens[index + 1 :]

def has_rm_force_recursive(tokens: list[str]) -> bool:
    if not tokens or command_name(tokens[0]) != "rm":
        return False
    args = tokens[1:]
    return has_option(args, "f", "--force") and (has_option(args, "r", "--recursive") or has_option(args, "R", "--recursive"))

def has_git_reset_hard(tokens: list[str]) -> bool:
    subcommand, args = git_parts(tokens)
    return subcommand == "reset" and "--hard" in args

def has_git_clean_force_dir(tokens: list[str]) -> bool:
    subcommand, args = git_parts(tokens)
    if subcommand != "clean":
        return False
    letters: set[str] = set()
    for token in args:
        letters |= option_letters(token)
    return ("f" in letters or "--force" in args) and ("d" in letters or "--directories" in args)

def has_git_push_force(tokens: list[str]) -> bool:
    subcommand, args = git_parts(tokens)
    if subcommand != "push":
        return False
    return any(token in {"-f", "--mirror"} or token.startswith("--force") or token.startswith("+") for token in args)

def has_chmod_recursive_777(tokens: list[str]) -> bool:
    if len(tokens) < 4 or command_name(tokens[0]) != "chmod":
        return False
    return "777" in tokens and has_option(tokens[1:], "R", "--recursive")

def segment_block_reason(tokens: list[str], depth: int) -> str | None:
    core = strip_wrappers(tokens)
    nested = nested_shell_script(core)
    if nested is not None:
        if depth >= 4:
            return "nested shell command"
        return command_block_reason(nested, depth + 1)
    checks = (
        (has_rm_force_recursive(core), "recursive forced removal"),
        (has_git_reset_hard(core), "hard reset"),
        (has_git_clean_force_dir(core), "force clean directories"),
        (has_git_push_force(core), "force or mirror push"),
        (has_chmod_recursive_777(core), "recursive chmod 777"),
    )
    for blocked, label in checks:
        if blocked:
            return label
    return None

def command_block_reason(command: str, depth: int = 0) -> str | None:
    for pattern, label in PIPE_SHELL_PATTERNS:
        if pattern.search(command):
            return label
    for segment in command_segments(shell_tokens(command)):
        reason = segment_block_reason(segment, depth)
        if reason:
            return reason
    return None

def payload_tool_command(payload: dict[str, JsonValue]) -> tuple[str, str | None]:
    tool = payload.get("tool_name", payload.get("tool"))
    if not isinstance(tool, str):
        raise HarnessHookError("missing text field: tool_name")
    if tool != "Bash":
        return tool, None
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        command = text_field(tool_input, "command")
    else:
        command = text_field(payload, "command")
    return tool, command

def main() -> int:
    args = parse_args()
    try:
        payload = require_mapping(read_payload(args.payload), "tool payload")
        tool, command = payload_tool_command(payload)
    except HarnessHookError as exc:
        print_block("BLOCK_TOOL", str(exc))
        return 2

    if tool != "Bash":
        print_result("OK_TOOL", f"tool accepted: {tool}")
        return 0

    if command is None:
        print_block("BLOCK_TOOL", "missing Bash command")
        return 2

    reason = command_block_reason(command)
    if reason:
        print_block("BLOCK_TOOL", f"destructive command detected: {reason}")
        return 2

    print_result("OK_TOOL", "command accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
