from pathlib import Path
import tomllib

from harness.model_compat_benchmark import (
    ProtocolCase,
    benchmark_configured_opencode,
    run_protocol_benchmark,
)
from harness.opencode_adapter import OpenCodeAdapterError, OpenCodeRunResult


def _result(*, repaired=False, structured=0):
    return OpenCodeRunResult(
        decision_json='{"kind":"complete","payload":{"reason":"ok"}}',
        session_id="s",
        input_tokens=10,
        output_tokens=4,
        reasoning_tokens=1,
        event_count=2,
        protocol_repaired=repaired,
        protocol_repair_kind="raw_control_character" if repaired else None,
        structured_output_tool_uses=structured,
        external_tool_uses=0,
    )


def test_protocol_benchmark_keeps_protocol_and_task_competence_separate():
    calls = []

    def invoke(case: ProtocolCase):
        calls.append(case.case_id)
        if len(calls) == 2:
            return _result(repaired=True)
        if len(calls) == 3:
            raise OpenCodeAdapterError(
                "bad schema",
                kind="protocol_schema",
                retryable=True,
            )
        return _result()

    report = run_protocol_benchmark(
        model_ref="opencode/free-model",
        invoke=invoke,
        samples=5,
    )

    assert report["scope"] == "protocol_compatibility_not_task_competence"
    assert report["route"]["fixed_model"] is True
    assert report["route"]["fallback_disabled"] is True
    assert report["route"]["harness_tool_execution"] is False
    assert report["samples"]["valid"] == 4
    assert report["samples"]["lexical_repairs"] == 1
    assert report["samples"]["protocol_failures"] == 1
    assert report["samples"]["error_kinds"] == {"protocol_schema": 1}
    assert report["usage"]["input_tokens"] == 40


def test_external_tool_violation_is_separate_hard_metric():
    def invoke(case):
        raise OpenCodeAdapterError(
            "bash forbidden",
            kind="protocol_boundary_violation",
            retryable=False,
        )

    report = run_protocol_benchmark(
        model_ref="opencode/free-model",
        invoke=invoke,
        samples=3,
    )

    assert report["samples"]["external_tool_violations"] == 3
    assert report["samples"]["valid"] == 0


def test_configured_benchmark_pins_selected_opencode_route(tmp_path, monkeypatch):
    config = tmp_path / "harness.toml"
    config.write_text(
        '''default_model = "opencode"\n\n[models.opencode]\nprovider = "command"\nmodel = "opencode/free-model"\ntimeout_seconds = 42\n\n[models.opencode.options]\nadapter = "opencode"\nopencode_binary = "opencode"\nopencode_agent = "harness-model"\ncatalog_explicitly_free = true\ncontext_window = 65536\n''',
        encoding="utf-8",
    )
    seen = []

    def fake_run(**kwargs):
        seen.append(kwargs)
        return _result()

    monkeypatch.setattr("harness.model_compat_benchmark.run_opencode_decision", fake_run)
    report = benchmark_configured_opencode(config, samples=2)

    assert len(seen) == 2
    assert all(item["model"] == "opencode/free-model" for item in seen)
    assert all(item["timeout_seconds"] == 42 for item in seen)
    assert report["route"]["catalog_explicitly_free"] is True
    assert report["route"]["context_window"] == 65536

    parsed = tomllib.loads(config.read_text(encoding="utf-8"))
    assert parsed["default_model"] == "opencode"
