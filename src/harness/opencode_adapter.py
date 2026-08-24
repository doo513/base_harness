from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import argparse
import json
import os
import subprocess
import sys
import tempfile

from harness.model_error_envelope import encode_model_error
from harness.model_protocol import DecisionProtocolError, decode_decision_text


class OpenCodeAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: str = "opencode_adapter_error",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = bool(retryable)


DEFAULT_OPENCODE_AGENT = "harness-model"
_INTERNAL_STRUCTURED_OUTPUT_TOOL = "StructuredOutput"


@dataclass(frozen=True)
class OpenCodeRunResult:
    decision_json: str
    session_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    event_count: int
    protocol_repaired: bool = False
    protocol_repair_kind: str | None = None
    structured_output_tool_uses: int = 0
    external_tool_uses: int = 0


def _decision_transport_prompt(system: str, user: str) -> str:
    return (
        "HARNESS DECISION TRANSPORT MODE\n"
        "You are being used only as a model/decision transport for another verified-state Harness.\n"
        "Do NOT use OpenCode shell, file, web, workspace, or subagent tools.\n"
        "A requested Harness tool action must be returned as JSON text; never execute it yourself.\n"
        "Return exactly one complete JSON object and no commentary.\n\n"
        "HARNESS SYSTEM CONTRACT:\n"
        f"{system}\n\n"
        "HARNESS MODEL INPUT:\n"
        f"{user}"
    )


def _deny_external_tools_inline_config() -> str:
    """Define a minimal primary agent with no host-action authority.

    OpenCode Structured Output is an internal schema-validation mechanism. It is
    explicitly allowed so a later structured-output transport can be A/B tested,
    while every external/action tool remains denied. This is still application-
    level permissioning, not an OS sandbox; the adapter also uses a temp cwd.
    """
    permission = {
        "*": "deny",
        _INTERNAL_STRUCTURED_OUTPUT_TOOL: "allow",
    }
    return json.dumps(
        {
            "permission": permission,
            "compaction": {"auto": True, "prune": True},
            "agent": {
                DEFAULT_OPENCODE_AGENT: {
                    "description": "Decision-only model transport for base_harness",
                    "mode": "primary",
                    "permission": permission,
                    "prompt": (
                        "Act only as a text model transport. Do not call external tools or subagents. "
                        "Follow the user-provided Harness contract and return only the requested text."
                    ),
                }
            },
        },
        separators=(",", ":"),
    )


def _parse_jsonl(stdout: str) -> OpenCodeRunResult:
    text_parts: list[str] = []
    session_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    event_count = 0
    structured_output_tool_uses = 0
    external_tool_uses = 0

    for line_no, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise OpenCodeAdapterError(
                f"OpenCode JSONL line {line_no} is invalid: {exc.msg}",
                kind="invalid_response",
            ) from exc
        if not isinstance(event, dict):
            raise OpenCodeAdapterError(
                f"OpenCode JSONL line {line_no} is not an object",
                kind="invalid_response",
            )
        event_count += 1
        if isinstance(event.get("sessionID"), str):
            session_id = event["sessionID"]

        event_type = event.get("type")
        if event_type == "tool_use":
            part = event.get("part")
            tool = part.get("tool") if isinstance(part, dict) else None
            if tool == _INTERNAL_STRUCTURED_OUTPUT_TOOL:
                structured_output_tool_uses += 1
                continue
            external_tool_uses += 1
            raise OpenCodeAdapterError(
                "OpenCode attempted an external tool action inside the decision-only boundary"
                + (f": {tool}" if tool else ""),
                kind="protocol_boundary_violation",
                retryable=False,
            )
        if event_type == "error":
            raise OpenCodeAdapterError(
                f"OpenCode session error: {event.get('error')!r}",
                kind="provider_error",
                retryable=True,
            )
        if event_type == "text":
            part = event.get("part")
            value = part.get("text") if isinstance(part, dict) else None
            if isinstance(value, str) and value.strip():
                text_parts.append(value.strip())
        if event_type == "step_finish":
            part = event.get("part")
            tokens = part.get("tokens") if isinstance(part, dict) else None
            if isinstance(tokens, dict):
                input_tokens = tokens.get("input") if isinstance(tokens.get("input"), int) else input_tokens
                output_tokens = tokens.get("output") if isinstance(tokens.get("output"), int) else output_tokens
                reasoning_tokens = (
                    tokens.get("reasoning")
                    if isinstance(tokens.get("reasoning"), int)
                    else reasoning_tokens
                )

    if not text_parts:
        raise OpenCodeAdapterError(
            "OpenCode run produced no completed text event; JSONL output may be incomplete",
            kind="protocol_truncated",
            retryable=True,
        )

    try:
        decoded = decode_decision_text(
            text_parts[-1],
            allow_control_character_repair=True,
        )
    except DecisionProtocolError as exc:
        raise OpenCodeAdapterError(
            f"OpenCode decision violates Harness protocol: {exc}",
            kind=exc.kind,
            retryable=exc.retryable,
        ) from exc

    return OpenCodeRunResult(
        decision_json=decoded.canonical_json,
        session_id=session_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        event_count=event_count,
        protocol_repaired=decoded.lexical_repaired,
        protocol_repair_kind=decoded.lexical_repair_kind,
        structured_output_tool_uses=structured_output_tool_uses,
        external_tool_uses=external_tool_uses,
    )


def run_opencode_decision(
    *,
    system: str,
    user: str,
    binary: str,
    model: str,
    agent: str = DEFAULT_OPENCODE_AGENT,
    timeout_seconds: float = 180.0,
) -> OpenCodeRunResult:
    if not binary.strip():
        raise OpenCodeAdapterError("OpenCode binary must not be empty", kind="configuration_error")
    if not model.strip():
        raise OpenCodeAdapterError("OpenCode model must not be empty", kind="configuration_error")
    if not agent.strip():
        raise OpenCodeAdapterError("OpenCode agent must not be empty", kind="configuration_error")
    if timeout_seconds <= 0:
        raise OpenCodeAdapterError("OpenCode timeout must be positive", kind="configuration_error")

    prompt = _decision_transport_prompt(system, user)

    with tempfile.TemporaryDirectory(prefix="base-harness-opencode-") as raw_tmp:
        temp_root = Path(raw_tmp).resolve()
        config_dir = temp_root / "config"
        work_dir = temp_root / "workspace"
        config_dir.mkdir()
        work_dir.mkdir()

        env = dict(os.environ)
        env["OPENCODE_CONFIG_CONTENT"] = _deny_external_tools_inline_config()
        env["OPENCODE_CONFIG_DIR"] = str(config_dir)

        argv = [
            binary,
            "run",
            "--format",
            "json",
            "--agent",
            agent,
            "--model",
            model,
            "--dir",
            str(work_dir),
        ]
        try:
            proc = subprocess.run(
                argv,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=float(timeout_seconds),
                cwd=str(work_dir),
                env=env,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenCodeAdapterError(
                "OpenCode run timed out",
                kind="timeout",
                retryable=True,
            ) from exc
        except OSError as exc:
            raise OpenCodeAdapterError(
                f"OpenCode failed to start: {exc}",
                kind="execution_error",
            ) from exc

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[-2000:]
            raise OpenCodeAdapterError(
                f"OpenCode exited with status {proc.returncode}: {detail}",
                kind="execution_error",
            )
        return _parse_jsonl(proc.stdout)


def _error_envelope(exc: OpenCodeAdapterError) -> str:
    return encode_model_error(
        kind=exc.kind,
        message=str(exc),
        retryable=exc.retryable,
    )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OpenCode decision-only bridge for base_harness CommandProvider."
    )
    parser.add_argument("--binary", default="opencode", help="OpenCode executable name/path")
    parser.add_argument("--model", required=True, help="OpenCode model in provider/model form")
    parser.add_argument(
        "--agent",
        default=DEFAULT_OPENCODE_AGENT,
        help="OpenCode agent; harness-model is the minimal decision-only default",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args(argv)

    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise OpenCodeAdapterError(
                "Harness command request must be a JSON object",
                kind="configuration_error",
            )
        system = request.get("system")
        user = request.get("user")
        if not isinstance(system, str) or not isinstance(user, str):
            raise OpenCodeAdapterError(
                "Harness command request requires string system/user",
                kind="configuration_error",
            )
        result = run_opencode_decision(
            system=system,
            user=user,
            binary=args.binary,
            model=args.model,
            agent=args.agent,
            timeout_seconds=args.timeout,
        )
    except json.JSONDecodeError as exc:
        wrapped = OpenCodeAdapterError(
            f"Harness command request JSON is invalid: {exc.msg}",
            kind="configuration_error",
        )
        print(_error_envelope(wrapped), file=sys.stderr)
        return 2
    except OpenCodeAdapterError as exc:
        print(_error_envelope(exc), file=sys.stderr)
        return 2

    print(result.decision_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
