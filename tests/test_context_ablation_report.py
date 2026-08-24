from harness.context_ablation_report import compare_context_runs, summarize_run_records


def _event(event_kind, telemetry=None, **payload):
    body = dict(payload)
    if telemetry is not None:
        body["telemetry"] = telemetry
    return {"kind": event_kind, "payload": body}


def test_run_summary_separates_context_protocol_and_failure_observations():
    records = [
        _event(
            "model.context_compile",
            {
                "level": 2,
                "source_estimated_input_tokens": 4000,
                "compiled_estimated_input_tokens": 2000,
                "estimated_reduction_ratio": 0.5,
                "budget": {"max_input_tokens": 3000},
            },
        ),
        _event(
            "model.protocol_decode",
            {
                "kind": "tool",
                "lexical_repaired": True,
                "lexical_repair_kind": "raw_control_character",
            },
        ),
        _event("failure", kind="actor_workflow_error"),
    ]
    summary = summarize_run_records(
        records=records,
        metrics={
            "completed": False,
            "steps": 3,
            "tool_calls": 1,
            "failures": 1,
            "model_attempts": 1,
        },
        manifest={
            "model_revision": "model:fixed",
            "task_revision": "task:v1",
            "config_hash": "abc",
        },
    )

    assert summary["context"]["compiled_tokens_mean"] == 2000
    assert summary["context"]["minimum_estimated_headroom_tokens"] == 1000
    assert summary["protocol"]["lexical_repairs"] == 1
    assert summary["failure_kinds"] == {"actor_workflow_error": 1}


def test_context_comparison_never_auto_claims_causality():
    baseline = {
        "model_revision": "model:fixed",
        "task_revision": "task:v1",
        "steps": 10,
        "tool_calls": 4,
        "failure_count": 2,
        "context": {"compiled_tokens_mean": 3000, "reduction_ratio_mean": 0.25},
        "protocol": {"lexical_repairs": 1},
    }
    variant = {
        "model_revision": "model:fixed",
        "task_revision": "task:v1",
        "steps": 8,
        "tool_calls": 4,
        "failure_count": 1,
        "context": {"compiled_tokens_mean": 2200, "reduction_ratio_mean": 0.45},
        "protocol": {"lexical_repairs": 0},
    }

    report = compare_context_runs(baseline, variant)

    assert report["controlled_ablation_eligible"] is True
    assert report["causal_conclusion"] == "not_inferred"
    assert report["observed_deltas"]["steps"] == -2
    assert report["observed_deltas"]["context_compiled_tokens_mean"] == -800


def test_mismatched_model_revision_blocks_controlled_ablation_claim():
    baseline = {
        "model_revision": "model:a",
        "task_revision": "task:v1",
        "context": {},
        "protocol": {},
    }
    variant = {
        "model_revision": "model:b",
        "task_revision": "task:v1",
        "context": {},
        "protocol": {},
    }

    report = compare_context_runs(baseline, variant)

    assert report["controlled_ablation_eligible"] is False
    assert report["same_model_revision"] is False
    assert report["causal_conclusion"] == "not_inferred"
