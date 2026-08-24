# Model Compatibility Layer v1 — staged implementation record

Date: 2026-08-24
Branch: `develop`

## Research question

Can heterogeneous model routes be used under one Verified-State Harness authority boundary while separating:

1. protocol compatibility;
2. task/decision competence;
3. Harness/context effects?

This work does **not** classify model intelligence, parameter tier, local/remote quality, or SLM capability.

## Frozen authority boundary

```text
Model = untrusted proposal generator
        ↓
Canonical Harness Decision
        ↓
Harness Runtime
  ├ execution authority
  ├ evidence authority
  ├ verification authority
  └ completion authority
```

Frozen:
- model output cannot execute a Harness tool directly;
- model claims are not verified facts;
- model `complete` is not accepted completion;
- every route must normalize through the canonical Decision boundary.

Not frozen:
- JSON text transport;
- provider-native schema mechanisms;
- wrapper protocol;
- provider selection;
- model context size.

## Gate A — Common Decision Decoder

Status: implemented and regression validated before later work.

`src/harness/model_protocol.py` centralizes:
- decision kinds;
- envelope/schema validation;
- canonical JSON serialization;
- output-contract/enforcement vocabulary.

The only v1 lexical repair is:

```text
strict json.loads
  ↓ Invalid control character only
json.loads(strict=False)
  ↓
canonical json.dumps
  ↓
schema/Decision validation
```

Forbidden semantic repairs:
- completing truncated JSON;
- guessing tool names;
- creating missing payloads;
- dropping unknown fields;
- repairing task IDs/dependencies.

This specifically addresses the observed OpenCode/model failure:

```text
Invalid control character at
```

without turning the Harness into a semantic output guesser.

## Gate B — Typed boundary failures

Status: implemented.

Added runtime distinction:
- `MODEL_PROVIDER_ERROR`
- `MODEL_PROTOCOL_ERROR`
- `ACTOR_WORKFLOW_ERROR`
- existing `IMPLEMENTATION_ERROR`

Meaning:

```text
transport/provider failure  -> provider family
wire/schema failure         -> protocol family
valid Decision but bad DAG  -> actor workflow family
Harness/custom controller bug -> implementation family
```

Important correction discovered during CI:
A malformed `ScriptedController` Decision must remain an integration/implementation failure. Only the LLM/model boundary may classify model output as `MODEL_PROTOCOL_ERROR`.

## Gate C — OpenCode model-only text route

Status: implementation validated; live fixed-model evidence still required.

Current route:

```text
Harness
  ↓
OpenCode CLI adapter
  ↓ selected provider/model
```

External OpenCode action authority remains denied.

```text
read/edit/bash/web/subagent/etc.  DENY
StructuredOutput internal mechanism ALLOW
```

The exception exists because OpenCode Structured Output itself uses an internal StructuredOutput mechanism. The security Gate is therefore:

```text
external/action tool use = 0
```

not:

```text
all internal OpenCode tool events = 0
```

The adapter still uses a temporary workspace/config directory. This is application-level boundary hardening, not an OS sandbox claim.

The current CLI route remains **text generation + post-hoc canonical Decision validation**. `opencode run --format json` is treated as JSON event transport, not as proof that the model output was JSON-schema constrained.

## Gate D — Protocol compatibility benchmark

Status: benchmark tooling implemented; live 100–500-sample result pending operator environment.

`python -m harness.model_compat_benchmark harness.toml --samples 100`

The benchmark pins one OpenCode model and does not execute Harness tools.

Metrics include:
- valid decision rate;
- lexical repair rate;
- protocol failure rate;
- error kinds;
- external OpenCode tool violations;
- internal StructuredOutput events;
- token usage when reported;
- latency.

It explicitly records:

```text
scope = protocol_compatibility_not_task_competence
fixed_model = true
fallback_disabled = true
harness_tool_execution = false
```

A high protocol-validity score is not evidence that the model solves real tasks well.

## Gate E — Context/E2E diagnostics

Status: telemetry and comparison tooling implemented; live controlled ablation pending.

Runtime now records diagnostic-only events per LLM Actor attempt:
- `model.context_compile`
- `model.protocol_decode`
- `model.gateway_telemetry`

These diagnostics have no truth/progress/completion authority.

`context_ablation_report` compares integrity-verified run manifests/events and reports only observed deltas. It intentionally emits:

```text
causal_conclusion = not_inferred
```

A context causal claim requires at minimum the same model revision and task revision, plus otherwise pinned experiment settings.

Existing Stage-07 invariant remains unchanged:
- all current non-superseded verified fact identities remain represented;
- relevance may reduce detail/richness, not delete current truth identity.

## Gate F — ModelCapabilities route contracts

Status: implemented; final aggregate CI pending at the time this document was written.

ModelCapabilities now separates input/output route contracts.

Input:
```text
context_window
reserved_output_tokens
context_safety_margin_tokens
effective_input_budget
```

Output:
```text
contract:
  text | json | json_schema | tool_call

enforcement:
  prompt_only
  posthoc_validated
  wrapper_enforced
  provider_native
```

Examples:
- generic `command`: `text + prompt_only`;
- current OpenCode CLI route: `json + posthoc_validated`;
- Ollama native schema route: `json_schema + provider_native`;
- LM Studio native schema route: `json_schema + provider_native`;
- OpenAI-compatible route: unconstrained text unless its configured response format explicitly strengthens the route.

The generic `command` route is deliberately no longer labeled structured merely because a particular command might happen to return JSON.

## Structured Output A/B decision

OpenCode Structured Output is **not promoted to the default route yet**.

Reason:
- switching from current CLI text transport to SDK/server Structured Output changes more than one variable;
- making it default before measuring the current stabilized baseline would confound transport and schema effects;
- current OpenCode implementations/issues require careful handling of the internal `StructuredOutput` permission and model/provider compatibility.

Correct sequence:

```text
current text route baseline
  ↓
100–500 protocol samples
  ↓
StructuredOutput experimental arm
  ↓
A/B protocol comparison
  ↓
only then consider default promotion
```

## Native provider expansion Gate

GPT/Claude/Gemini native routes are intentionally not added before the fixed OpenCode baseline.

Adding providers earlier would increase independent failure surfaces before the current compatibility question is measured.

Required evidence before this Gate opens:
1. current aggregate repository CI PASS;
2. one fixed OpenCode model protocol benchmark result;
3. at least one small real E2E task run with the new diagnostic telemetry;
4. no external OpenCode tool-boundary violation.

## Recovery/Fallback rule

Production recovery and experiment recovery must stay separate.

Production may use typed retry/fallback.

Controlled model comparison must pin:
- model revision/ID;
- context policy;
- protocol policy;
- repair policy;
- fallback disabled.

Otherwise a second model can silently solve a first model's benchmark failure and invalidate the measurement.

## Current meta conclusion

The architecture has not required a Kernel rewrite.

The observed failures support a narrower conclusion:

> The primary instability is at the heterogeneous Model ↔ Harness compatibility boundary, while the Verified-State execution/evidence/verification/completion authority model remains appropriate.

Further work should be evidence-gated rather than adding more provider/agent complexity immediately.
