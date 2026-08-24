import json
from types import SimpleNamespace

import pytest

from harness.opencode_adapter import (
    OpenCodeAdapterError,
    _error_envelope,
    _parse_jsonl,
    run_opencode_decision,
)


def _event(event_type, **extra):
    return json.dumps({"type": event_type, "sessionID": "ses-test", **extra})


def test_parse_opencode_jsonl_extracts_final_decision_and_usage():
    stdout = "\n".join([
        _event("step_start", part={"type": "step-start"}),
        _event(
            "text",
            part={
                "type": "text",
                "text": '{"kind":"tool","payload":{"tool":"directory.list","args":{}}}',
            },
        ),
        _event(
            "step_finish",
            part={
                "type": "step-finish",
                "tokens": {"input": 1200, "output": 40, "reasoning": 10},
            },
        ),
    ])

    result = _parse_jsonl(stdout)

    assert json.loads(result.decision_json)["kind"] == "tool"
    assert result.session_id == "ses-test"
    assert result.input_tokens == 1200
    assert result.output_tokens == 40
    assert result.reasoning_tokens == 10
    assert result.event_count == 3
    assert result.external_tool_uses == 0
    assert result.protocol_repaired is False


def test_parse_opencode_repairs_only_raw_control_character_json():
    # The newline is deliberately raw inside the JSON string. This reproduces
    # the observed OpenCode/model failure that Python reports as
    # "Invalid control character at".
    raw_decision = '{"kind":"complete","payload":{"reason":"line1\nline2"}}'
    stdout = _event(
        "text",
        part={"type": "text", "text": raw_decision},
    )

    result = _parse_jsonl(stdout)

    assert result.protocol_repaired is True
    assert result.protocol_repair_kind == "raw_control_character"
    assert json.loads(result.decision_json)["payload"]["reason"] == "line1\nline2"


def test_parse_opencode_jsonl_rejects_external_tool_execution():
    stdout = _event(
        "tool_use",
        part={"type": "tool", "tool": "bash", "state": {"status": "completed"}},
    )

    with pytest.raises(OpenCodeAdapterError, match="external tool action") as caught:
        _parse_jsonl(stdout)
    assert caught.value.kind == "protocol_boundary_violation"
    assert caught.value.retryable is False


def test_parse_opencode_allows_only_internal_structured_output_tool_marker():
    stdout = "\n".join([
        _event(
            "tool_use",
            part={
                "type": "tool",
                "tool": "StructuredOutput",
                "state": {"status": "completed"},
            },
        ),
        _event(
            "text",
            part={
                "type": "text",
                "text": '{"kind":"complete","payload":{"reason":"ok"}}',
            },
        ),
    ])
    result = _parse_jsonl(stdout)
    assert result.structured_output_tool_uses == 1
    assert result.external_tool_uses == 0


def test_parse_opencode_jsonl_fails_closed_when_text_event_is_missing():
    stdout = "\n".join([
        _event("step_start", part={"type": "step-start"}),
        _event("step_finish", part={"type": "step-finish", "tokens": {"input": 10, "output": 0}}),
    ])

    with pytest.raises(OpenCodeAdapterError, match="no completed text event") as caught:
        _parse_jsonl(stdout)
    assert caught.value.kind == "protocol_truncated"
    assert caught.value.retryable is True


def test_run_opencode_uses_temp_workspace_and_denies_external_tools(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured.update(kwargs)
        inline = json.loads(kwargs["env"]["OPENCODE_CONFIG_CONTENT"])
        assert inline["permission"]["*"] == "deny"
        assert inline["permission"]["StructuredOutput"] == "allow"
        agent_permission = inline["agent"]["harness-model"]["permission"]
        assert agent_permission["*"] == "deny"
        assert agent_permission["StructuredOutput"] == "allow"
        assert inline["compaction"]["auto"] is True
        assert inline["compaction"]["prune"] is True
        assert kwargs["cwd"] == argv[argv.index("--dir") + 1]
        assert kwargs["input"].startswith("HARNESS DECISION TRANSPORT MODE")
        assert "Do NOT use OpenCode shell" in kwargs["input"]
        assert "SYSTEM-SENTINEL" in kwargs["input"]
        assert "USER-SENTINEL" in kwargs["input"]
        assert "--dangerously-skip-permissions" not in argv
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=_event(
                "text",
                part={
                    "type": "text",
                    "text": '{"kind":"complete","payload":{"reason":"ok"}}',
                },
            ),
        )

    monkeypatch.setattr("harness.opencode_adapter.subprocess.run", fake_run)

    result = run_opencode_decision(
        system="SYSTEM-SENTINEL",
        user="USER-SENTINEL",
        binary="opencode",
        model="ollama/gemma3:latest",
        agent="harness-model",
        timeout_seconds=30,
    )

    assert json.loads(result.decision_json) == {
        "kind": "complete",
        "payload": {"reason": "ok"},
    }
    assert captured["argv"][:4] == ["opencode", "run", "--format", "json"]
    assert captured["argv"][captured["argv"].index("--agent") + 1] == "harness-model"
    assert captured["argv"][captured["argv"].index("--model") + 1] == "ollama/gemma3:latest"
    assert captured["shell"] is False


def test_parse_opencode_rejects_schema_invalid_decision_without_guessing():
    stdout = _event(
        "text",
        part={"type": "text", "text": '{"kind":"tool","payload":{"tool":"","args":{}}}'},
    )
    with pytest.raises(OpenCodeAdapterError, match="violates Harness protocol") as caught:
        _parse_jsonl(stdout)
    assert caught.value.kind == "protocol_schema"


def test_adapter_error_envelope_is_machine_readable_and_contains_no_secret_fields():
    error = OpenCodeAdapterError(
        "invalid JSON",
        kind="protocol_invalid_json",
        retryable=True,
    )
    line = _error_envelope(error)
    assert line.startswith("HARNESS_MODEL_ERROR:")
    payload = json.loads(line.split(":", 1)[1])
    assert payload == {
        "kind": "protocol_invalid_json",
        "message": "invalid JSON",
        "retryable": True,
    }
