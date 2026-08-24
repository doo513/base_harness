import json
from types import SimpleNamespace

import pytest

from harness.opencode_adapter import (
    OpenCodeAdapterError,
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


def test_parse_opencode_jsonl_rejects_internal_tool_execution():
    stdout = _event(
        "tool_use",
        part={"type": "tool", "tool": "bash", "state": {"status": "completed"}},
    )

    with pytest.raises(OpenCodeAdapterError, match="attempted a tool action"):
        _parse_jsonl(stdout)


def test_parse_opencode_jsonl_fails_closed_when_text_event_is_missing():
    stdout = "\n".join([
        _event("step_start", part={"type": "step-start"}),
        _event("step_finish", part={"type": "step-finish", "tokens": {"input": 10, "output": 0}}),
    ])

    with pytest.raises(OpenCodeAdapterError, match="no completed text event"):
        _parse_jsonl(stdout)


def test_run_opencode_uses_stdin_json_mode_temp_workspace_and_deny_all_permissions(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = list(argv)
        captured.update(kwargs)
        inline = json.loads(kwargs["env"]["OPENCODE_CONFIG_CONTENT"])
        assert inline["permission"] == "deny"
        assert inline["compaction"]["auto"] is True
        assert inline["compaction"]["prune"] is True
        assert kwargs["cwd"] == argv[argv.index("--dir") + 1]
        assert kwargs["input"].startswith("HARNESS DECISION TRANSPORT MODE")
        assert "Do NOT use OpenCode tools" in kwargs["input"]
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
        agent="plan",
        timeout_seconds=30,
    )

    assert json.loads(result.decision_json) == {
        "kind": "complete",
        "payload": {"reason": "ok"},
    }
    assert captured["argv"][:4] == ["opencode", "run", "--format", "json"]
    assert captured["argv"][captured["argv"].index("--agent") + 1] == "plan"
    assert captured["argv"][captured["argv"].index("--model") + 1] == "ollama/gemma3:latest"
    assert captured["shell"] is False


def test_parse_opencode_rejects_schema_invalid_decision():
    stdout = _event(
        "text",
        part={"type": "text", "text": '{"kind":"tool","payload":{"tool":"","args":{}}}'},
    )
    with pytest.raises(OpenCodeAdapterError, match="violates Harness protocol"):
        _parse_jsonl(stdout)
