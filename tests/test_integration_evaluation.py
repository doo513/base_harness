import json

import pytest

from harness.evaluation import (
    EvaluationControl,
    EvaluationError,
    EvaluationRecord,
    MatchedAblationReport,
    append_evaluation_record,
    load_evaluation_records,
)


def _control(**overrides):
    values = {
        "task_id": "task-1",
        "task_revision": "task-v1",
        "model_revision": "model-v1",
        "profile": "software",
        "toolset_revision": "tools-v1",
        "budget_revision": "budget-v1",
        "oracle_revision": "oracle-v1",
        "environment_revision": "env-v1",
    }
    values.update(overrides)
    return EvaluationControl(**values)


def _record(arm, repeat, completed, *, control=None, tokens=100):
    return EvaluationRecord(
        arm=arm,
        repeat=repeat,
        control=control or _control(),
        completed=completed,
        steps=5,
        tool_calls=2,
        failures=0,
        completion_requests=1,
        oracle_checks=1,
        model_requests=4,
        total_tokens=tokens,
        model_latency_seconds=1.5,
    )


def test_matched_ablation_rejects_control_drift():
    with pytest.raises(EvaluationError):
        MatchedAblationReport([
            _record("baseline", 0, True),
            _record("harness", 0, True, control=_control(model_revision="other-model")),
        ])


def test_matched_ablation_summarizes_repeated_arms():
    report = MatchedAblationReport([
        _record("baseline", 0, False, tokens=80),
        _record("baseline", 1, True, tokens=120),
        _record("harness", 0, True, tokens=100),
        _record("harness", 1, True, tokens=140),
    ]).summarize()
    assert report["arms"]["baseline"]["solve_rate"] == 0.5
    assert report["arms"]["harness"]["solve_rate"] == 1.0
    assert report["arms"]["harness"]["avg_total_tokens"] == 120.0
    assert report["control_fingerprint"] == _control().fingerprint


def test_evaluation_jsonl_round_trip_and_fingerprint_tamper_rejection(tmp_path):
    path = tmp_path / "records.jsonl"
    record = _record("harness", 0, True)
    append_evaluation_record(path, record)
    loaded = load_evaluation_records(path)
    assert loaded[0].dump() == record.dump()

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["control"]["model_revision"] = "tampered"
    path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    with pytest.raises(EvaluationError):
        load_evaluation_records(path)
