import json

import pytest

from harness.model_protocol import (
    DecisionProtocolError,
    OutputContract,
    OutputEnforcement,
    decode_decision_text,
)


def test_strict_valid_decision_is_canonicalized():
    decoded = decode_decision_text(
        '{"payload":{"args":{},"tool":"directory.list"},"kind":"tool"}'
    )
    assert decoded.kind == "tool"
    assert decoded.payload == {"args": {}, "tool": "directory.list"}
    assert json.loads(decoded.canonical_json) == {
        "kind": "tool",
        "payload": {"args": {}, "tool": "directory.list"},
    }
    assert decoded.lexical_repaired is False


def test_markdown_fence_is_transport_normalization_not_semantic_repair():
    decoded = decode_decision_text(
        '```json\n{"kind":"complete","payload":{"reason":"done"}}\n```'
    )
    assert decoded.kind == "complete"
    assert decoded.lexical_repaired is False


def test_raw_control_character_is_only_bounded_lexical_repair():
    raw = '{"kind":"complete","payload":{"reason":"line1\nline2"}}'
    decoded = decode_decision_text(raw)
    assert decoded.payload["reason"] == "line1\nline2"
    assert decoded.lexical_repaired is True
    assert decoded.lexical_repair_kind == "raw_control_character"
    # Canonical JSON escapes the raw newline again.
    assert "\\n" in decoded.canonical_json
    assert json.loads(decoded.canonical_json)["payload"]["reason"] == "line1\nline2"


def test_control_character_repair_can_be_disabled():
    raw = '{"kind":"complete","payload":{"reason":"line1\nline2"}}'
    with pytest.raises(DecisionProtocolError) as exc:
        decode_decision_text(raw, allow_control_character_repair=False)
    assert exc.value.kind == "protocol_invalid_json"


def test_truncated_json_is_not_completed_or_guessed():
    with pytest.raises(DecisionProtocolError) as exc:
        decode_decision_text('{"kind":"tool","payload":{"tool":"file.read","args":{')
    assert exc.value.kind == "protocol_truncated"


def test_empty_tool_name_is_not_semantically_repaired():
    with pytest.raises(DecisionProtocolError, match="tool.tool") as exc:
        decode_decision_text('{"kind":"tool","payload":{"tool":"","args":{}}}')
    assert exc.value.kind == "protocol_schema"


def test_unknown_fields_are_not_dropped():
    with pytest.raises(DecisionProtocolError, match="exactly kind and payload") as exc:
        decode_decision_text(
            '{"kind":"complete","payload":{"reason":"x"},"extra":"discard me"}'
        )
    assert exc.value.kind == "protocol_schema"


def test_plan_extra_fields_are_not_repaired():
    with pytest.raises(DecisionProtocolError, match="only supports objective and tasks"):
        decode_decision_text(
            '{"kind":"plan","payload":{"objective":"x","tasks":[{"id":"t1"}],"next":"tool"}}'
        )


def test_output_contract_axes_are_independent():
    assert OutputContract.JSON_SCHEMA.value == "json_schema"
    assert OutputEnforcement.PROVIDER_NATIVE.value == "provider_native"
    assert OutputEnforcement.POSTHOC_VALIDATED.value == "posthoc_validated"
