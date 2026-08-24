# Failure / Provider / Runtime Hardening — Causal Implementation Record

Date: 2026-08-24  
Branch: `develop`  
Validated source: `c3083a51ed4de06ec88eca5605afd211baf327e2`  
Validation: **418 passed, 7 skipped**, all recorded Core/Stage 02–08 gates PASS.

## 1. Scope and decision

This work reviewed 18 requested reliability/security changes around model/provider failures, retries, response normalization, configuration contracts, subprocess/plugin/MCP boundaries, reproducibility, and diagnostics.

The architecture invariant was not changed:

```text
Model / Provider
    ↓ untrusted proposal
Canonical Harness Decision
    ↓
Harness Runtime
    ├─ tool execution authority
    ├─ evidence authority
    ├─ verification authority
    └─ completion authority
```

Two requested ideas were deliberately refined rather than copied literally:

1. Unsupported configuration is **rejected fail-closed**, not silently stripped. Silent filtering makes operator intent and actual execution diverge.
2. Python plugin import is **not called isolated**. Import executes Python in the host process. Strict isolation therefore rejects Python plugins rather than claiming subprocess isolation that does not exist.

---

# 2. Root causal problem

Before this hardening, failures could cross several interpretation layers:

```text
provider/adapter exception
        ↓
ModelGateway provider-specific handling
        ↓
Controller re-interprets exception kind / stderr marker
        ↓
Runtime maps controller exception again
        ↓
FailureRouter
```

Consequences:

- the same underlying failure could be labeled differently depending on route;
- retry/fallback ownership was split between Gateway and Controller;
- provider output validation was partly provider-specific;
- command adapter stderr could become generic `execution_error` before being reinterpreted later;
- a Controller could perform semantic repair (`task` → generated `plan`) in a layer that should only normalize/validate;
- generic command subprocesses inherited more host context than required;
- configuration could describe MCP transport/options that current execution code did not implement;
- profile composition mutated reusable profile/tool objects;
- model route details were not fully bound into the run configuration fingerprint.

The target flow is now:

```text
Provider Adapter
     ↓ ModelResponse
Gateway Response Normalizer
     ↓ NormalizedModelResponse
Canonical Decision Decoder
     ↓
Gateway Failure Classification
     ↓ FailureContext
FailurePolicyEngine
     ├─ retry same route
     ├─ approved fallback
     └─ return typed failure
              ↓
          Controller
       validation only
              ↓
          Harness Runtime
              ↓
     durable failure evidence
```

---

# 3. Current implementation

## 3.1 Common failure context and policy

Implemented in `src/harness/core/failures.py`.

New stable policy inputs:

```text
FailureContext
├─ kind
├─ origin
├─ phase
├─ retryable
├─ fallback_safe
├─ route_alias
├─ provider_id
├─ model_id
├─ call_id
├─ exit_code
├─ stderr_digest
└─ metadata

PolicyDecision
├─ runtime_action
├─ retry_same_route
├─ fallback_allowed
└─ terminal
```

`FailurePolicyEngine` is the common error → policy layer.

Important correction found during re-review:

```text
provider_call_id = diagnostic identity
provider_call_id ≠ repeat/failure semantic identity
```

Therefore `call_id` is persisted for tracing but excluded from `Failure.signature`. Otherwise every retry would appear to be a new failure and repeat detection/strategy switching would be defeated.

## 3.2 Retry and fallback ownership moved to Gateway

Implemented in `src/harness/model_gateway.py` and `src/harness/core/controller.py`.

Before:

```text
Gateway retry
+
Controller empty-response retry
+
Controller provider error reinterpretation
```

After:

```text
Gateway
  ├─ classify
  ├─ normalize
  ├─ protocol repair
  ├─ same-route retry
  └─ fallback

Controller
  └─ accepts typed Gateway result/failure and validates only
```

The Controller no longer:

- inspects provider-specific exception kinds;
- parses OpenCode stderr markers;
- retries an empty response itself;
- promotes an initial `task` decision into a generated `plan`.

This removes both duplicated recovery policy and semantic repair from the Controller boundary.

## 3.3 One normalized provider response schema

`ModelResponse` remains the provider plugin output contract.

Every provider then passes through Gateway normalization into:

```text
normalized-model-response-v1
├─ route_alias
├─ provider_id
├─ model_id
├─ provider_call_id
├─ request_id
├─ usage
├─ latency_seconds
├─ raw_metadata
└─ canonical content
```

After normalization, all routes pass through the same `decode_decision_text()` path.

Provider-specific `protocol_enforced` flags can still describe native capability, but they no longer create different Gateway parsing/retry pipelines.

## 3.4 Bounded protocol repair remains syntax-only

The common decoder retains the previously established rule:

```text
strict JSON parse
   ↓ fail only on raw control character
bounded lexical repair
   ↓
strict schema / Decision validation
```

Still forbidden:

- inventing a missing tool name;
- completing truncated JSON;
- deleting unknown fields;
- generating a missing payload;
- repairing a task dependency graph.

## 3.5 Fail-closed configuration contracts

Implemented in `src/harness/config_contracts.py` and enforced by model/MCP/plugin construction paths.

Built-in model providers accept only declared option keys.

Examples of validated fields:

- context window / output reserve / safety margin;
- output contract / enforcement declaration;
- fallback aliases;
- provider generation options;
- seed type;
- command environment allowlist;
- OpenCode adapter metadata.

MCP:

- current `mcp-gateway-v2` supports stdio only;
- HTTP transport is rejected during Gateway construction instead of failing at first use;
- timeout and nested tool-policy keys are validated.

Plugins:

- non-empty plugin options require `harness_plugin_contract()`;
- option keys are checked before the option-consuming `harness_plugin(options=...)` factory is invoked.

This is deliberate rejection, not silent field removal.

## 3.6 Model preflight before Runtime

`ModelGateway.preflight()` validates all active routes (`default + fallback`) before `HarnessRuntime` starts.

For command routes it checks:

- command executable availability;
- OpenCode adapter executable availability when applicable;
- provider construction / required secret resolution.

The CLI records successful preflight as diagnostic-only evidence:

```text
model.preflight
```

No model request is made by preflight.

## 3.7 Command process host-impact reduction

Generic command model routes now default to:

```text
shell = false
cwd = temporary directory
environment = minimal allowlist
PYTHONPATH = not inherited by default
arbitrary parent env = not inherited
```

Explicit additional environment variables require `command_env_allowlist`.

The command response records:

```text
environment_policy = minimal_allowlist
cwd_policy = temporary_directory
host_isolation = process_boundary_not_sandbox
stderr_digest = SHA-256(stderr)
```

This reduces accidental path/env/token exposure but is **not** filesystem/network sandboxing. An arbitrary subprocess may still use absolute paths or network access allowed by the OS.

## 3.8 MCP lifecycle hardening

Implemented in `src/harness/mcp_gateway.py`.

State machine:

```text
NEW
 ↓
STARTING
 ↓
CONNECTED
 ↓ failure/timeout/process exit
BROKEN
 ↓ explicit safe reconnect
NEW → CONNECTED

CLOSED = terminal lifecycle state
```

Rules:

- request timeout or broken process forces process cleanup;
- `heartbeat()` checks subprocess liveness only;
- discovery/list may use explicit `reconnect_safe()`;
- `tools/call` is never automatically replayed after an ambiguous disconnect;
- close terminates/cleans the subprocess.

Why no automatic tool-call replay:

```text
request sent
→ connection fails
→ unknown whether server already executed side effect
→ automatic replay could duplicate effect
```

Therefore ambiguity is returned to Harness recovery instead.

## 3.9 Plugin host-process boundary is explicit

`PluginGateway` now declares:

```text
host_process_import = true
host_isolation = none-for-module-import
strict_isolation_compatible = false
```

CLI strict tool isolation rejects enabled MCP/plugin extensions before loading them.

Plugin config validation reduces configuration ambiguity, but **does not turn Python import into a sandbox**.

## 3.10 Profile/model mutation isolation

`augment_profile_tools()` no longer mutates the input profile.

Before:

```text
input profile
→ replace profile.tools method in-place
→ mutate ToolSpec provenance
→ reused profile may observe previous composition
```

After:

```text
input profile
→ shallow profile snapshot of same concrete class
→ structural ToolSpec copies
→ copied provenance/schema metadata
→ composed snapshot returned

original profile unchanged
```

Returned ToolSpecs are cloned again so a caller cannot modify stored composition through a returned object.

`ModelGateway` similarly snapshots each `ModelConfig.options` mapping at construction so later mutation of caller-owned dictionaries cannot change the running route or revision.

Stage-07 context projection/compiler remains pure with respect to durable state; this work did not weaken that contract.

## 3.11 Manifest / replay provenance expansion

`ModelGateway.descriptor()` now includes per-route:

- provider/model;
- endpoint;
- command;
- timeout;
- secret reference descriptor, never secret value;
- full configured options;
- deterministic `options_hash`;
- retry policy;
- normalized response schema;
- command environment/CWD policy.

`HarnessRuntime._config_descriptor()` embeds the ModelGateway descriptor + revision into the run configuration fingerprint.

Therefore resume equivalence detects model-route drift, not merely Controller class drift.

Generation `seed` is accepted only as an integer and is passed to currently supported OpenAI-compatible, Ollama, and LM Studio request paths. A seed recorded in the manifest therefore corresponds to a seed actually supplied by the Harness request code.

Existing tool provenance already records handler source hashes; plugin tool provenance additionally carries plugin version/module/API information.

## 3.12 Standardized diagnostics

Gateway telemetry now exposes and Runtime persists diagnostic events containing:

- failure kind/origin/phase;
- route/provider/model;
- `provider_call_id`;
- request ID when supplied by provider;
- exit code for command failures;
- `stderr_digest` rather than raw secret-bearing stderr as the stable diagnostic identity;
- retry/fallback policy decision;
- normalized response metadata;
- token/latency totals.

These remain `authority = diagnostic_only` and cannot promote facts or progress.

## 3.13 Capability declaration tests

The route capability layer distinguishes:

```text
output contract
  text | json | json_schema | tool_call

output enforcement
  prompt_only | posthoc_validated | wrapper_enforced | provider_native
```

A generic `command` route does not claim structured output merely because some command adapters happen to provide it.

Config contracts and declaration tests ensure declared `output_contract/output_enforcement` values are also accepted/validated by configuration parsing.

---

# 4. Requested-item disposition

| # | Priority | Result | Current disposition |
|---|---|---|---|
| 1 | P0 | Implemented | Common `FailureKind + FailureContext` across model/provider/runtime boundary |
| 2 | P0 | Implemented | Same-route retry/fallback owned by Gateway + `FailurePolicyEngine`; Controller retry removed |
| 3 | P0 | Implemented | `NormalizedModelResponse` + one canonical decision decoder |
| 4 | P0 | Implemented | Model preflight + MCP/plugin/built-in option contracts before first runtime action |
| 5 | P0 | **Partially mitigated** | command env/CWD reduction, MCP minimal env, strict extension rejection; no claim of full OS sandbox |
| 6 | P1 | Implemented for current built-ins | common `ModelProvider/ModelResponse`; provider-specific options isolated behind provider/config contract. External custom provider option contract remains provider-owned |
| 7 | P1 | Implemented | unsupported built-in/MCP/plugin option keys fail closed rather than being ignored |
| 8 | P1 | Implemented | profile composition + ToolSpec structural copies; ModelConfig options snapshot; Stage-07 context purity retained |
| 9 | P1 | Implemented for model/tool provenance | Gateway command/options hash/timeout/seed/revision in manifest; handler source hashes and plugin versions retained |
| 10 | P1 | Implemented | policy routes on `FailureContext/PolicyDecision`, not Python exception hierarchy |
| 11 | P1 | Implemented | provider failures remain `MODEL_PROVIDER_ERROR`, distinct from Harness implementation failures |
| 12 | P1 | Implemented by this document | current implementation and future target explicitly separated |
| 13 | P1 | Implemented | capability/config declaration regression tests added |
| 14 | P1 | Implemented | provider call ID, phase, exit code, stderr digest, policy decision telemetry |
| 15 | P2 | Implemented | common `FailurePolicyEngine` fixes error → classification → policy flow |
| 16 | P2 | Implemented | MCP state machine, timeout cleanup, liveness heartbeat, explicit safe reconnect, no automatic tool replay |
| 17 | P2 | Implemented | failure-domain policy matrix/property-style parametrized tests plus boundary tests |
| 18 | P2 | Implemented | provider adapters normalize through common Gateway response/protocol contract |

---

# 5. Validation and re-review history

The implementation was not treated as correct after the first edit.

Examples of issues caught during staged re-review:

1. **Failure signature mistake** — provider call ID was initially considered for failure identity. Re-review identified that this would defeat repeat detection. It was removed from semantic signature while retained in diagnostics.
2. **Profile composition regression** — old test expected in-place profile mutation. The new invariant intentionally preserves the source profile; test was changed to require a returned isolated snapshot.
3. **Controller policy ownership** — old tests expected Runtime/provider retry behavior. The contract was changed so Gateway exhausts provider retry/fallback first; Runtime receives a typed exhausted failure.
4. **Plugin option validation cycle** — validating plugin options through the option-consuming factory is too late, so a static contract was added before factory invocation.
5. **MCP reconnect semantics** — automatic replay was rejected because non-idempotent tool execution may have ambiguous completion status.
6. **Seed provenance gap** — merely persisting seed was rejected as false reproducibility; seed is now forwarded by supported provider requests.

Validated source:

```text
c3083a51ed4de06ec88eca5605afd211baf327e2
```

CI result:

```text
418 passed, 7 skipped
compile / CLI / TUI                     PASS
core-freeze-audit                       PASS
Stage 02–08 recorded gates              PASS
```

---

# 6. Future target — explicitly NOT current implementation

The following are not claimed as completed:

## 6.1 True OS isolation for arbitrary model/plugin processes

Current command isolation is:

```text
minimal env + temporary cwd + subprocess boundary
```

It is not:

```text
filesystem namespace sandbox
network namespace sandbox
mandatory syscall sandbox
```

Python plugin import still runs trusted code in the host process. A future isolated plugin worker would need a serializable tool RPC contract and independent process/sandbox boundary; that is a separate architectural change.

## 6.2 Remote MCP transport

Current MCP Gateway implements stdio. HTTP config is rejected early rather than advertised as supported. Remote transport should only be enabled after a real transport implementation and contract tests exist.

## 6.3 Active protocol heartbeat

Current MCP heartbeat is process liveness only. The Harness does not invent an unsupported protocol ping. A future protocol-level health check should be added only when its interoperability and side-effect semantics are defined.

## 6.4 Universal custom-provider option schema

Built-in providers have core option contracts. External providers registered programmatically still own validation of provider-specific extensions. A future provider-plugin registration contract may make those option schemas first-class.

---

# 7. Final architectural state

```text
Config
  ↓ fail-closed contracts / preflight
Immutable route/profile snapshots
  ↓
ModelGateway
  ↓ provider adapter
ModelResponse
  ↓ common normalization
NormalizedModelResponse
  ↓ canonical decision decoder
Decision
  ↓
Harness Runtime

Failures:
raw provider/model/runtime symptom
  ↓
FailureContext
  ↓
FailurePolicyEngine
  ↓
retry / fallback / repair / observe / replan / stop
  ↓
durable diagnostic + recovery evidence
```

The key outcome is not simply that more exceptions are caught. The change establishes one causal boundary where **failure meaning, response shape, retry ownership, configuration intent, and replay provenance are made explicit before Harness authority is exercised**.
