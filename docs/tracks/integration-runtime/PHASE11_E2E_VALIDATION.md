# Phase 11 — End-to-End Validation

Status: LOCAL FULL-PATH E2E IMPLEMENTED; live third-party provider execution remains an external evidence gate.

## Goal

Validate the integration as one system rather than as isolated modules.

The local E2E path intentionally crosses:

```text
Command Model Gateway
→ LLMController JSON Decision
→ Agent plan/task state
→ Tool Runtime + workspace execution
→ durable artifact/observation
→ completion request
→ harness-side acceptance oracle
→ completed state
```

## Implementation

- added `tests/test_e2e_integration_runtime.py`;
- the test uses a real subprocess-backed `CommandProvider`, not a mocked controller;
- the model subprocess reads governed context and emits plan/task/tool/complete decisions;
- both Software and Hackathon profiles execute a real workspace mutation;
- fixed harness-side acceptance commands independently verify the final workspace state;
- assertions cover completion, Agent Control persistence, tool metrics, completion/oracle metrics, and evidence artifact registration;
- added `scripts/run_live_case.py` as an opt-in runner for real configured model providers and real workspaces.

## Structural review

- E2E success still comes from the completion oracle, not the command-model actor;
- model subprocess output cannot directly mutate trusted state;
- workspace mutation occurs only through the existing tool runtime;
- model revision is recorded from the Gateway;
- the same runtime path is used for Software/Hackathon rather than a benchmark-only shortcut.

## Live provider evidence

This repository change does not claim that OpenAI-compatible or other third-party providers have been successfully exercised from this implementation environment. Live provider tests require operator credentials/network access and should be recorded as external evaluation evidence, not silently mocked.

A live case can be invoked with `scripts/run_live_case.py` using an explicit config, workspace, task revision, goal, and fixed acceptance command(s). The resulting run directory preserves the normal manifest/events/artifacts/metrics evidence.

## Exit interpretation

- local full-stack integration path: covered by automated test;
- live provider compatibility/rate-limit behavior: pending actual external run evidence;
- real repository quality/performance claim: deferred to Phase 12 benchmark/ablation.
