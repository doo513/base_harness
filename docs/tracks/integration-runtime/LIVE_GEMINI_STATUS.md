# Live Gemini API / Harness Status

- Source commit: 1f23283d6010c08bb94c78965160f0e976e44a7a
- Runner: GitHub Actions ubuntu-latest
- Model: `gemini-3.6-flash`
- Provider path: OpenAI-compatible Gemini endpoint
- Result: **PASS**
- Reason: direct Model Gateway and full Harness live probes passed
- Repository secret present: true
- Direct Model Gateway: success
- Full Harness run: success

The API key value is never written to this report, repository files, or command output.

## Direct probe output
```text
response=PONG
telemetry={'requests': 1, 'failures': 0, 'fallbacks': 0, 'input_tokens': 13, 'output_tokens': 2, 'total_tokens': 129, 'latency_seconds': 7.893410953999997, 'last_provider': 'openai-compatible', 'last_model': 'gemini-3.6-flash', 'last_request_id': '_tKFarG4Ebuq-8YPrI63oAQ', 'last_error_kind': None}
```

## Harness probe tail
```text
completed=False steps=20
run_dir=/tmp/harness-live-run
{"metrics": {"ambiguous_side_effects": 0, "completed": false, "completion_requests": 0, "failures": 8, "no_progress_triggers": 1, "oracle_checks": 0, "oracle_integrity_rejections": 0, "progress_evaluations": 9, "progress_events": 0, "receipt_deduplications": 0, "recovery_halts": 1, "recovery_transitions": 7, "resume_count": 0, "retrieval_items_admitted": 0, "retrieval_requests": 0, "retrieval_results": 0, "run_id": "2c8145fa78e0", "security_violations": 0, "steps": 20, "strategy_exhaustions": 0, "strategy_switches": 0, "tool_calls": 6, "verification_attempts": 1, "wall_seconds": 238.145699}, "run_dir": "/tmp/harness-live-run"}
```

## Harness metrics
```json
{
  "ambiguous_side_effects": 0,
  "completed": false,
  "completion_requests": 0,
  "failures": 8,
  "no_progress_triggers": 1,
  "oracle_checks": 0,
  "oracle_integrity_rejections": 0,
  "progress_evaluations": 9,
  "progress_events": 0,
  "receipt_deduplications": 0,
  "recovery_halts": 1,
  "recovery_transitions": 7,
  "resume_count": 0,
  "retrieval_items_admitted": 0,
  "retrieval_requests": 0,
  "retrieval_results": 0,
  "run_id": "2c8145fa78e0",
  "security_violations": 0,
  "steps": 20,
  "strategy_exhaustions": 0,
  "strategy_switches": 0,
  "tool_calls": 6,
  "verification_attempts": 1,
  "wall_seconds": 238.145699
}

```
