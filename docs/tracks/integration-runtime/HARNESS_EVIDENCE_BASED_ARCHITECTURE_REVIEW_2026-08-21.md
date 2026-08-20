# Base Harness — Evidence-Based Architecture Review

Date: 2026-08-21

Repository: `doo513/base_harness`

Evidence snapshot:

- `main` HEAD observed at `0238c9912442d11423730a7ab96be40c54792610` (`ci: record integration runtime verification [skip ci]`)
- runtime source under test: `4c42232d6ad75c6f0840c5265087025d584ea17a`
- CI result for that source commit: `306 passed, 7 skipped`, all listed core/stage gates PASS
- CI runner: `ubuntu-latest`, Python 3.11

Status: architecture review and causal diagnosis. This document does not weaken or redefine Kernel authority. It separates confirmed repository evidence, operator-supplied runtime evidence, causal conclusions, and remaining evidence gaps.

---

## 1. Review question

Recent live runs established that the Harness can reach planning and tool execution, but also exposed several failures:

1. content-addressed artifact verification failed on Windows after a successful tool call;
2. an Actor model emitted an empty tool name;
3. earlier runs emitted malformed/invalid decision JSON and invalid task graphs;
4. a 4096-token model route eventually rejected the growing Harness request because the prompt exceeded the provider context limit.

The purpose of this review is to determine which failures are:

- model/provider failures;
- Harness protocol-design weaknesses;
- platform/persistence defects;
- expected fail-closed behavior;
- evidence that the existing architecture itself should be replaced.

The conclusion is that the core verified-state architecture should be retained. The strongest remaining weaknesses are concentrated at the **Model ↔ Harness protocol boundary**, **token-budget awareness**, and **Windows-specific runtime validation**.

---

# 2. Evidence method

## 2.1 Evidence classes

### A. Repository-attested evidence

Used for firm architectural claims:

- current source under `src/harness/`;
- commit diffs;
- current integration documents;
- test files;
- `.github/workflows/research-ci.yml`;
- `docs/tracks/integration-runtime/CI_STATUS.md`.

### B. Operator-supplied runtime evidence

Used for runtime symptoms that are not committed as immutable logs in this repository.

Examples supplied during manual Windows runs include:

```text
tool.tool must be a non-empty string
artifact content hash mismatch
request (4154 tokens) exceeds the available context size (4096 tokens)
request (4219 tokens) exceeds the available context size (4096 tokens)
...
hard budget exceeded
```

These observations are valid operational evidence, but this document does not treat them as repository-attested facts beyond what the source code independently corroborates.

### C. Inference

An inference is stated only when the code and observed behavior support the causal chain. Where direct Windows replay evidence is missing, the document says so explicitly.

---

# 3. Incident A — Windows CRLF artifact hash mismatch

## 3.1 Observed result

A tool call such as `directory.list` succeeded, an observation artifact was created, and later deterministic progress/evidence verification rejected that artifact with:

```text
artifact content hash mismatch
```

The run then followed the persistence-integrity fail-closed path and stopped rather than treating unverifiable evidence as valid progress.

## 3.2 Confirmed root cause

The root cause was a byte-identity violation between the bytes hashed by `ArtifactStore.put_text()` and the bytes written by the text writer on Windows.

The content-addressing contract is conceptually:

```text
content string
    ↓ UTF-8
SHA-256(content bytes)
    ↓
artifact://<digest>_<name>
    ↓
write exactly those bytes
```

Before commit `4c42232`, `atomic_write_text()` opened the temporary file in ordinary text mode:

```python
os.fdopen(fd, "w", encoding="utf-8")
```

On Windows, newline translation can transform `\n` in the logical content into `\r\n` in the stored file. `ArtifactStore.put_text()` had already generated the content-address digest from the pre-translation UTF-8 content. A later verified binary read therefore hashed different bytes.

This diagnosis is directly corroborated by commit:

- `4c42232` — `fix(storage): fix Windows CRLF newline corruption in atomic_write_text causing artifact hash mismatch`

The fix changes the writer to:

```python
os.fdopen(fd, "w", encoding="utf-8", newline="")
```

so Python does not perform platform newline translation.

## 3.3 Why the integrity failure was correct

The failure must **not** be fixed by normalizing CRLF/LF during verification or accepting multiple hashes.

The content-addressed reference is intended to identify exact bytes. If the bytes on disk differ from the bytes represented by the digest, verification must fail. The defect was therefore in the writer, not in the hash verifier.

Correct invariant:

```text
bytes hashed before persistence
==
bytes durably written
==
bytes returned by verified read
```

## 3.4 Result of the defect

The observed causal chain is:

```text
Actor requests directory.list
        ↓
Tool Runtime succeeds
        ↓
Tool output becomes an observation artifact
        ↓
artifact reference records digest of logical UTF-8 content
        ↓
Windows text writer changes newline bytes
        ↓
Progress Controller later verifies raw artifact bytes
        ↓
SHA-256 differs
        ↓
PersistenceError / IntegrityError path
        ↓
checkpoint_stop
```

Therefore this failure is **not evidence that Ollama or the Actor lacked filesystem access**. Tool execution had already succeeded.

## 3.5 Current remediation status

Current `src/harness/core/storage.py` contains both:

- `newline=""` in `atomic_write_text()`;
- a Windows portable verified-read path selected when `os.name == "nt"`.

The repository regression suite for source commit `4c42232` passes:

```text
306 passed, 7 skipped
core-freeze-audit        PASS
stage03-resume           PASS
stage06-progress         PASS
stage08-artifact-integrity PASS
```

## 3.6 Remaining evidence gap

The current main regression workflow explicitly uses:

```yaml
runs-on: ubuntu-latest
```

There is no Windows CI matrix in `.github/workflows/research-ci.yml` at this evidence snapshot.

The current Windows compatibility test exercises the portable verified-read helper and tamper rejection, but repository search did not show a dedicated Windows/CRLF write regression that executes the actual Windows newline behavior.

Therefore the strongest defensible status is:

> **Code defect identified and corrected; Linux CI remains green; native Windows replay and/or Windows CI is still required to close the platform evidence gap.**

---

# 4. Incident B — empty tool name

## 4.1 Observed result

The model emitted a decision equivalent to:

```json
{
  "kind": "tool",
  "payload": {
    "tool": ""
  }
}
```

and the Harness reported:

```text
tool.tool must be a non-empty string
```

## 4.2 Confirmed immediate cause

`Decision.validate()` in `src/harness/core/controller.py` intentionally requires a non-empty tool identifier:

```python
if not isinstance(tool, str) or not tool.strip():
    raise ValueError("tool.tool must be a non-empty string")
```

Therefore the immediate cause is an **invalid Actor decision generated by the model**.

The Harness must not infer an intended tool such as `directory.list` from an empty field. Doing so would move action-selection authority from an explicit model request into an implicit repair heuristic.

Correct behavior at the Kernel boundary is:

```text
invalid Actor tool request
→ do not execute anything
```

## 4.3 Secondary Harness weakness: failure taxonomy

Although rejecting the decision is correct, current runtime classification is coarse.

`RuntimeExecutionMixin.step_once()` catches generic Controller exceptions and records them as:

```text
FailureKind.IMPLEMENTATION_ERROR
```

`FailureRouter` maps `IMPLEMENTATION_ERROR` to `REPAIR`.

This means several semantically different cases can collapse into one class:

```text
malformed model JSON
invalid decision schema
empty tool name
actual Harness implementation exception
```

That reduces observability and can make recovery prompts broader than necessary.

## 4.4 Architectural conclusion

The fix should **not** relax `Decision.validate()`.

The better direction is to add an explicit Actor/model protocol failure class, for example:

```text
MODEL_PROTOCOL_ERROR
or
INVALID_ACTOR_DECISION
```

and route it to targeted protocol repair.

Example:

```text
tool=""
  ↓
INVALID_ACTOR_DECISION
  ↓
repair request containing only:
- allowed decision shape
- currently available tool names
- exact invalid field
  ↓
model retries one decision
```

This preserves explicit action authority while reducing unnecessary context and recovery churn.

---

# 5. Incident C — malformed plan/JSON and invalid task graph

Operator logs previously showed several distinct failures:

```text
model did not return valid JSON object
plan payload only supports objective and tasks
task 't1' cannot depend on itself
```

These are not one root cause.

## 5.1 Syntax failure

`LLMController` currently receives provider output as text and performs:

1. direct `json.loads()`;
2. Markdown-fence extraction;
3. first-`{` to last-`}` extraction.

If none produces one object, it raises:

```text
model did not return valid JSON object
```

This is a **wire-format/protocol failure**.

## 5.2 Schema failure

A syntactically valid object can still include unsupported fields. `plan` intentionally allows only:

```text
objective
tasks
```

Extra fields are rejected. This is a **decision-schema failure**, not a JSON parse failure.

## 5.3 Semantic workflow failure

`AgentControlState.replace_plan()` separately checks the task graph:

- missing dependency IDs;
- self-dependency;
- duplicate dependencies;
- dependency cycles;
- duplicate task IDs;
- task-count/text bounds.

Therefore:

```text
t1 depends_on [t1]
```

is a **semantic plan error** and is correctly rejected even though its JSON and schema may be valid.

## 5.4 Why the current separation should remain

The Harness should continue distinguishing:

```text
wire syntax
→ Decision schema
→ plan/task semantics
→ tool/runtime execution
```

The improvement needed is failure classification and targeted repair, not removal of these validation layers.

---

# 6. Incident D — 4096-token context exhaustion

## 6.1 Operational evidence

The supplied provider responses included repeated HTTP 400 errors such as:

```text
request (4154 tokens) exceeds the available context size (4096 tokens)
request (4219 tokens) exceeds the available context size (4096 tokens)
request (4341 tokens) exceeds the available context size (4096 tokens)
...
```

This is direct evidence that the selected model route could no longer accept the generated request.

## 6.2 Repository evidence

The existing `ContextPolicy` is already bounded, but primarily by item counts and **character limits**:

```text
max_observations = 12
max_preview_chars_per_observation = 1200
max_total_observation_preview_chars = 6000
max_recent_failures = 5
max_tool_description_chars = 500
max_failure_message_chars = 800
...
```

`ModelGateway` records token usage returned by providers, but repository search at this snapshot does not show a model `context_window`/`n_ctx` contract feeding a pre-request token budget into `ContextProjector`.

## 6.3 Confirmed architectural gap

The Context Governor is bounded, but it is not currently **model-context-window aware**.

Character limits are useful for deterministic state projection, but they cannot guarantee:

```text
system prompt
+ goal
+ tool schemas
+ workflow state
+ observations
+ failures/recovery
+ output-token reserve
<= provider context window
```

for a 4K, 32K, or 128K model equally.

## 6.4 Result

Repeated repair/replan attempts can add recent failure/control information while the route remains fixed at 4096 tokens. Once the request exceeds the window, the provider rejects the request before the model can make any further decision. Continued retries then consume Harness budget without a realistic chance of recovery unless context is reduced or the route changes.

## 6.5 Required improvement

Introduce a provider/model-aware context budget contract:

```text
Model route
  context_window
  reserved_output_tokens
       ↓
Context Compiler
       ↓
mandatory system + goal + control
       ↓
remaining budget allocated to:
  tool schemas
  active workflow
  verified facts
  observations
  failures
  retrieval/memory
```

This should be a general Harness improvement, not an Ollama-only workaround.

---

# 7. Model ↔ Harness protocol review

## 7.1 Current boundary

Current `LLMController` explicitly instructs the Actor to return exactly one JSON object:

```json
{"kind":"plan|task|propose|verify_claim|tool|retrieve|refute|complete","payload":{}}
```

The first action is expected to be a `plan`; later actions are expressed through the same custom JSON decision protocol.

## 7.2 Existing provider capabilities are not fully consumed

`ProviderCapabilities` already contains:

```text
structured_output
native_tool_calling
streaming
vision
reasoning
```

The OpenAI-compatible provider advertises:

```text
structured_output = true
native_tool_calling = true
streaming = true
```

However, the existing Phase-03 contract explicitly states that native tool-calling capability is metadata only for now. `ModelGateway.complete()` returns assistant `content`, and `LLMController` still parses that content into the canonical Harness `Decision`.

Therefore the current architecture is effectively:

```text
Provider
  ↓ text content
LLMController JSON parser
  ↓
Canonical Decision
  ↓
Kernel
```

rather than:

```text
Provider-native structured response/tool call
  ↓
Protocol Adapter
  ↓
Canonical Decision
  ↓
Kernel
```

## 7.3 Consequence

The model currently bears unnecessary responsibility for reproducing Harness wire syntax exactly. This explains why malformed JSON, extra fields, and empty tool names can become operationally significant even when the model broadly understands the task.

## 7.4 Recommended architecture

Keep one canonical Kernel decision model, but add provider adapters before it:

```text
                    Model Protocol Adapter
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
 provider-native      structured JSON       text JSON
 tool calling            output             fallback
          │                 │                 │
          └─────────────────┼─────────────────┘
                            ↓
                   Canonical Decision
                            ↓
                 existing validation
                            ↓
                         Kernel
```

This is not permission to execute provider tool calls directly. Every route must normalize into the existing canonical `Decision` and pass the same capability, tool-schema, evidence, progress, verification, and completion boundaries.

---

# 8. Full architecture review

## 8.1 Task Intake / Workspace — RETAIN

Current direction is sound:

```text
explicit user path
→ bounded pre-runtime Task Intake
→ one WorkspaceContract root
→ actor tools remain confined
```

The model does not gain authority to expand its workspace during execution.

**Assessment:** retain.

## 8.2 Planning / AgentControl — RETAIN

`AgentControlState` provides durable objective/tasks/dependencies/status while explicitly stating that Actor workflow has no truth/progress/completion authority.

Graph validation is deterministic and catches self-dependency/cycles/missing IDs.

**Assessment:** retain explicit planning. Improve protocol generation, not planning authority.

## 8.3 Model Gateway / LLMController — PRIMARY IMPROVEMENT AREA

Strengths:

- provider-neutral routing;
- retry/fallback;
- secret separation;
- usage telemetry;
- Ollama JSON/reasoning compatibility guard;
- canonical Kernel decision validation.

Weaknesses:

- custom text JSON remains the primary Actor wire protocol;
- provider-native structured/tool facilities are metadata rather than an active normalization path;
- protocol errors are not a first-class failure family;
- no model-window-aware context budget is evident.

**Assessment:** improve without moving trust authority into the provider layer.

## 8.4 Tool Runtime — RETAIN

Tool execution uses layered checks:

```text
ToolCall
→ tool exists
→ args schema
→ capability
→ permission
→ isolation
→ execution
→ output schema/postcondition
```

Software runs can expose built-in workspace read tools plus `shell`/`argv`; MCP/plugins are optional additions through profile composition.

The observed successful `directory.list` demonstrates that the model can cause real local operations **through the Harness**, even though the LLM/Ollama process itself has no direct filesystem authority.

**Assessment:** retain.

## 8.5 Evidence / Persistence — RETAIN, EXPAND PLATFORM VALIDATION

Strengths:

- content-addressed artifacts;
- exact-byte verification;
- durable observations/evidence refs;
- verified reads before progress/novelty use;
- receipt/checkpoint/run-manifest integrity;
- fail-closed behavior on persistence errors.

Weakness exposed by live use:

- POSIX assumptions and Windows text behavior were not sufficiently exercised before Windows operation.

**Assessment:** architecture is sound; cross-platform evidence is insufficient.

## 8.6 Progress Control — RETAIN

Existing Phase-10 contract correctly refuses to equate arbitrary tool activity or Actor task status with verified progress.

The intended bridge remains:

```text
activity
→ evidence
→ verifier/domain milestone
→ Stage-06 progress credit
```

This prevents an Actor from resetting no-progress limits merely by producing activity.

**Assessment:** retain.

## 8.7 Recovery — RETAIN, REFINE TAXONOMY

The failure router has meaningful classes for tool/environment/persistence/security/verification/budget failures and preserves fail-closed behavior for persistence/security.

The weakness is that Controller protocol errors currently collapse into `IMPLEMENTATION_ERROR`.

**Assessment:** retain recovery state machine; add explicit model/actor-protocol failure classification and targeted repair.

## 8.8 Context Governor — RETAIN, MAKE TOKEN-AWARE

Current Stage-07 structure correctly separates trusted, untrusted, control, workflow, active context, tools, and memory namespaces and uses deterministic visibility bounds.

The observed 4K failure proves character limits alone are insufficient for heterogeneous model routes.

**Assessment:** retain authority/trust projection; add route-specific token budgeting.

## 8.9 Retrieval / Memory — RETAIN

Retrieval request text is Actor-controlled, while scope/top-k/provider/ranking/admission remain Kernel-owned. Retrieved material remains untrusted until it goes through normal evidence/proposal/verification paths.

**Assessment:** retain.

## 8.10 Verification / Completion — RETAIN

The runtime keeps Actor completion requests separate from Oracle acceptance. Evidence-backed artifact tasks require actual workspace observations and a concrete artifact rather than accepting Actor narrative completion.

**Assessment:** retain. Future semantic report-claim verification may be added separately; do not weaken the current oracle.

## 8.11 TUI — RETAIN AS THIN PRODUCT LAYER

The TUI should continue to:

- collect user input;
- select workspace/model/config;
- launch ordinary CLI/runtime flows;
- display plan/tool/evidence/recovery/final-result state.

It should not own trusted state or synthesize acceptance.

**Assessment:** retain.

---

# 9. Consolidated causal findings

| Finding | Immediate cause | Harness behavior | Classification | Status |
| --- | --- | --- | --- | --- |
| Windows artifact hash mismatch | Windows newline translation changed bytes after content digest creation | verified read rejected mismatch; persistence failure stopped run | confirmed Harness platform defect + correct fail-closed detection | writer fixed in `4c42232`; native Windows evidence still needed |
| `tool.tool` empty | model emitted invalid Actor decision | `Decision.validate()` rejected it before tool execution | confirmed model/protocol failure | validator correct; failure taxonomy/repair should improve |
| invalid JSON | model response not parseable as one decision object | parser rejected response | model/protocol failure | syntax normalization exists; adapter improvement recommended |
| extra plan fields | model returned schema-invalid plan payload | decision validation rejected it | model/protocol schema failure | correct rejection |
| self-dependent task | model produced invalid task graph | `AgentControlState` rejected plan | Actor semantic workflow failure | correct rejection |
| 4096 context overflow | generated request exceeded selected route context window | provider HTTP 400; retries could not recover without smaller context/route change | confirmed provider limit + Harness token-budget gap | unresolved general improvement |
| successful `directory.list` before persistence stop | Harness tool runtime executed workspace operation successfully | observation/evidence was created before later integrity failure | positive evidence of real tool connectivity | confirmed operationally |

---

# 10. Development priorities derived from evidence

## P0 — Windows runtime evidence

Add Windows CI or an equivalent committed Windows E2E gate for the portable subset.

Minimum evidence:

1. `atomic_write_text()` round-trip with `\n` produces exact UTF-8 bytes expected by the content digest;
2. `ArtifactStore.put_text/put_json → verified_read_bytes` succeeds on Windows;
3. tampered bytes are rejected;
4. normal `directory.list/file.read` run proceeds through Stage-06 progress verification;
5. existing platform-specific POSIX anti-symlink/swap tests remain on Linux.

Do not claim identical POSIX and Windows filesystem race-hardening primitives where the OS does not provide them.

## P1 — First-class Actor protocol failures

Add a distinction such as:

```text
MODEL_PROVIDER_ERROR
MODEL_PROTOCOL_ERROR / INVALID_ACTOR_DECISION
ACTOR_WORKFLOW_ERROR
HARNESS_IMPLEMENTATION_ERROR
```

The exact names are secondary; the key requirement is that invalid model output must not be indistinguishable from an internal Harness bug.

## P2 — Model Protocol Adapter

Activate provider capability-aware normalization:

```text
native tool/structured response
→ canonical Harness Decision
```

with text JSON as fallback.

Security invariant:

> Provider-native tool calls are proposals only. No provider response may bypass canonical Decision validation or ActionRuntime policy.

## P3 — Token-aware Context Compiler

Add model-route metadata and reserve-aware budgeting before model invocation.

The compiler must keep mandatory control/authority context first, then allocate the remaining budget to lower-priority observations/tools/memory.

A retry after `context_length_exceeded` should not blindly resend a larger equivalent context.

## P4 — Real-model A/B evidence

After P1–P3, compare at least:

- one strong API model;
- one second independent provider/model route;
- Ollama/local route as compatibility/regression evidence.

Measure separately:

```text
valid decision rate
plan acceptance rate
tool-call success rate
protocol-repair rate
context-overflow rate
verified completion rate
steps/tokens/time to first useful evidence
```

This prevents local-model weaknesses from being mistaken for Harness architecture weaknesses and prevents strong-model capability from hiding Harness protocol defects.

---

# 11. Architecture decision

The evidence does **not** support replacing the current verified-state Kernel.

The retained architecture should remain:

```text
User Goal
   ↓
Task Intake / Workspace Contract
   ↓
Model Gateway
   ↓
[future: Model Protocol Adapter]
   ↓
Canonical Actor Decision
   ↓
Agent planning / tool request
   ↓
Capability + Tool Runtime
   ↓
Observation / Content-addressed Evidence
   ↓
Progress + Recovery + Context governance
   ↓
Verification
   ↓
Completion Oracle
   ↓
FinalResult / TUI
```

The central invariant remains valid:

> The model may plan, request actions, propose claims, and request completion; only Harness-side deterministic authority may execute governed capabilities, promote trusted truth, grant verified progress, or accept completion.

The next development work should therefore concentrate on making the **front edge of the Kernel easier and more reliable for heterogeneous models**, rather than weakening the evidence/verification/recovery architecture that detected the recent failures.

---

# 12. Evidence index

Primary source locations used by this review:

- `src/harness/core/storage.py`
  - `atomic_write_text`
  - `ArtifactStore.put_text`
  - `ArtifactStore.verified_read_bytes_from_root`
  - Windows portable verified-read path
- commit `4c42232d6ad75c6f0840c5265087025d584ea17a`
  - Windows CRLF writer correction
- `src/harness/core/controller.py`
  - `Decision.validate`
  - `_extract_json_object`
  - `LLMController.SYSTEM`
- `src/harness/core/agent_control.py`
  - deterministic task DAG validation
  - non-authoritative workflow state
- `src/harness/model_gateway.py`
  - `ProviderCapabilities`
  - OpenAI-compatible provider
  - Ollama compatibility options
  - usage/retry/fallback telemetry
- `docs/tracks/integration-runtime/PHASE03_MODEL_GATEWAY.md`
  - native tool calling explicitly documented as metadata-only/current limitation
- `src/harness/core/tools.py`
  - tool schema/capability/permission/isolation/execution path
- `src/harness/core/runtime_execution.py`
  - tool observation persistence
  - Controller exception handling
  - completion/verification dispatch
- `src/harness/core/failures.py`
  - current failure taxonomy and recovery routing
- `src/harness/core/context.py`
  - character/item-bounded `ContextPolicy`
- `src/harness/core/runtime_context.py`
  - governed context namespaces and Agent workflow projection
- `src/harness/core/runtime_retrieval_kernel.py`
  - Kernel-owned retrieval request/admission
- `src/harness/task_contracts.py`
  - evidence-backed artifact completion contract
- `docs/tracks/integration-runtime/PHASE10_PROGRESS_RECOVERY_ALIGNMENT.md`
  - activity vs verified progress invariant
- `tests/test_windows_tui_artifact_compat.py`
  - portable verified-read/tamper/TUI state tests
- `.github/workflows/research-ci.yml`
  - current `ubuntu-latest` regression runner
- `docs/tracks/integration-runtime/CI_STATUS.md`
  - source `4c42232`, PASS, `306 passed, 7 skipped`
- `docs/tracks/integration-runtime/WINDOWS_TUI_ARTIFACT_INCIDENT_2026-08-20.md`
  - prior Windows directory-fd/TUI incident analysis

## Evidence boundary

This document deliberately does **not** claim:

- that every Windows issue is closed without a native Windows replay/CI result;
- that all model failures are caused by weak models;
- that native tool calling can be trusted directly;
- that current report completion proves every natural-language report sentence;
- that passing Ubuntu CI proves platform equivalence.

Those claims require additional evidence.