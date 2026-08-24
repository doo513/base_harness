# Causal Problem Atlas

Date: 2026-08-24

Purpose: make failure causes directly searchable and prevent future work from treating every live symptom as an isolated bug.

Status vocabulary:

```text
OPEN        = current structural problem remains
PARTIAL     = important mitigation exists, root issue remains
RESOLVED    = supplied critique is stale against current source
HISTORICAL  = useful causal evidence, not current defect
```

---

# P0-A — False stuck detection: Trusted Progress and Execution Liveness are coupled

**Status: OPEN / STRUCTURAL**

## Observable symptoms

```text
consecutive Actor decisions produced no recognized progress
repeated Actor decision family produced no recognized progress
strategy switch
hard budget exceeded
```

Often accompanied by repeated:

```text
directory.list
file.read
file.search
plan/task transitions
```

## Immediate code path

Primary locations:

- `src/harness/core/runtime_progress.py`
  - `RuntimeProgressMixin._progress_baseline()`
  - `RuntimeProgressMixin._evaluate_actor_progress()`
- `src/harness/core/progress.py`
  - `ProgressPolicy`
  - `decision_progress_signatures()`
- `src/harness/profiles/software.py`
  - `task_progress_snapshot()`
  - `workflow_contract()`

Search keywords:

```text
no_progress_streak
family_repeat_count
reset_credit_threshold
novel_successful_observation_content
credit=0.0
profile_task_progress_advanced
consecutive Actor decisions
```

## Current semantics

Activity novelty is logged but has zero progress-reset credit. Recognized progress is mainly:

```text
verified fact content change
or
profile-defined monotonic task milestone/score advance
```

The Software profile's task milestones are currently relatively late semantic events:

```text
verified_artifact_assertion
build_passed
tests_passed
behavioral_acceptance_verified
```

## Root cause

Stage 06 answered one security question correctly:

> Can the Actor manufacture trusted progress by staying busy?

Answer: no.

But the same progress horizon is later used to answer a different operational question:

> Is a multi-step implementation trajectory stuck before reaching its next verification point?

That equivalence is false.

Example legitimate path:

```text
read config
→ read source
→ search call sites
→ inspect test
→ patch source
→ compile
→ targeted test
→ propose verified build/test claim
```

Several actions may occur before trusted progress changes.

## Amplifier

If the Tool layer lacks high-level write/patch/build semantics, more intermediate shell/read decisions are needed, causing the Stage-06 threshold to fire sooner.

## Why naive fix is dangerous

Do **not** make every new file read or successful command trusted progress. That reopens the loop:

```text
read A
read B
read C
random changing output
...
```

and lets the Actor avoid stuck detection indefinitely.

## Required architectural correction

Separate:

```text
TrustedProgress      — Core authority
ExecutionLiveness    — diagnostic/control only
```

Use bounded workflow/phase obligations for liveness rather than unlimited activity credit.

Candidate phases:

```text
OBSERVE
REPRODUCE
CHANGE
VERIFY
RECOVER
COMPLETE-REQUEST
```

Each phase should define:

```text
allowed action families
maximum local actions
required transition condition
failure-directed next action
```

ExecutionLiveness may suppress a premature single-turn stuck decision **within a bounded phase**, but must never create trusted task progress or accepted completion.

---

# P0-B — Model/tool decision wire failures

**Status: PARTIAL → substantially hardened; live evidence still required**

## Historical symptoms

```text
model boundary failed
decision JSON is invalid
Invalid control character
protocol_truncated
empty tool name
extra plan fields
invalid task dependency
```

## Historical root cause

Different layers previously interpreted model output and provider errors:

```text
provider
→ ModelGateway
→ Controller parser/repair
→ Runtime classification
```

This caused error meaning and retry ownership to depend on route.

## Current remediation

Primary current locations:

- `src/harness/model_protocol.py`
- `src/harness/model_gateway.py`
- `src/harness/core/failures.py`
- `src/harness/core/controller.py`
- `docs/tracks/integration-runtime/FAILURE_PROVIDER_RUNTIME_HARDENING_2026-08-24.md`

Current design includes:

```text
NormalizedModelResponse
FailureContext
FailurePolicyEngine
Gateway-owned retry/fallback
one canonical decision decoder
syntax-only bounded control-character repair
```

Search keywords:

```text
NormalizedModelResponse
ModelGatewayFailure
FailureContext
protocol_invalid_json
protocol_truncated
protocol_schema
decode_decision_text
semantic_repair
```

## Remaining architectural concern

The Core should ultimately consume an already canonical `Decision` object and typed exhausted failure. Provider-native structured output, text JSON, tool-call APIs, OpenCode wrappers, and SDK-specific response shapes are Agent Shell concerns.

The current source is much closer to that boundary, but current live model benchmarks are still needed before declaring the operational problem closed.

## Do not do

```text
infer intended tool from empty name
complete truncated JSON semantically
delete unknown fields to make schema pass
repair task graph by guessing
```

---

# P0-C — OS/shell dialect leakage into the Actor

**Status: OPEN / HIGH PRACTICAL IMPACT**

## Observable symptoms

Windows host receives model-generated commands such as:

```text
cat > file <<'PYEOF'
python3 ...
.venv/bin/python ...
```

while actual environment is:

```text
PowerShell
C:\Users\...
.venv\Scripts\python.exe
```

## Concrete locations

- `src/harness/profiles/software.py`
  - `SoftwareProfile.tools()` exposes `shell` and `argv` as its writable/execution primitives.
  - workflow guidance says prefer structured read/argv over shell, but no generic structured write/patch tool is part of this profile.
- `src/harness/core/workspace_tools.py`
  - provides `file.read`, `directory.list`, `file.search` only.
  - no `file.write`, `file.patch`, `file.delete`, `directory.create` equivalents.
- `src/harness/core/tools.py`
  - `make_shell_tool`, `make_argv_tool`, structured execution backend machinery.
- `src/harness/cli.py`
  - chooses local vs Linux namespace backend, but does not transform Unix shell language into PowerShell semantics.

Search keywords:

```text
make_shell_tool
make_argv_tool
file.read
directory.list
file.search
shell
argv
execution_backend
```

## Root cause

The current abstraction is structured at the **process invocation boundary**, not the **developer intent boundary**.

It can safely execute:

```text
argv=[...]
```

but the Actor still has to know how to express ordinary developer operations in the current OS/toolchain.

For file modification this often collapses back to:

```text
Actor chooses shell language
→ shell dialect becomes part of reasoning burden
```

## Why this is structural

File edit/build/test operations are normal agent-shell infrastructure. They should not require the model to rediscover host dialect every run.

## Required correction

Provide platform-neutral primitives before shell escape hatches:

```text
file.read
file.write
file.patch
file.delete
file.search
directory.list
directory.create
process.run(argv)
runtime.resolve("python")
project.test(target?)
project.build(target?)    # optional profile adapter
```

The Core sees normal ToolCall/ToolResult. The Agent Shell maps these to `pathlib`, `subprocess`, PowerShell/Windows process rules, Linux, containers, or other providers.

Shell remains available only for actions that genuinely require shell semantics.

---

# P0-D — Runtime executable/path assumptions

**Status: OPEN / tied to P0-C**

## Symptoms

```text
python3
/usr/bin/python3
.venv/bin/python
/bin/sh
```

used in contexts that may run on Windows.

## Historical evidence

The initial Codex-oriented repository used `/usr/bin/python3` and POSIX substitution in hooks. Stage-02 real namespace probes are intentionally Linux-specific and correctly use `/bin/sh`; the problem occurs only when those environment assumptions leak into generic agent behavior.

## Root cause

The project has several distinct meanings of “runtime command”:

```text
Linux-specific security probe
portable Harness CLI invocation
Actor-selected project command
provider/adapter subprocess
completion oracle command
```

Those must not share undocumented executable naming assumptions.

## Required correction

Agent Shell RuntimeResolver:

```text
current_python = sys.executable
shell_dialect = powershell | cmd | posix-sh | none
path_style = windows | posix
project_runtime candidates = discovered + evidence-backed
```

Never rewrite Linux namespace tests to be platform-neutral if they are intentionally Linux evidence. Instead prevent Linux-only probe syntax from becoming a generic action template.

---

# P1-E — Evidence chain can stall before claim/verification transition

**Status: OPEN / caused by coordination of several layers**

## Symptom pattern

```text
compileall succeeded
pytest failed
repeated inspect/retry
hard budget exceeded
no verified build/test claim
completion never reached
```

## Relevant locations

- `src/harness/profiles/software.py`
  - verifier registry
  - `workflow_contract()`
  - `task_progress_snapshot()`
- `src/harness/profiles/software_verification.py`
- `src/harness/core/runtime_execution.py`
  - `_dispatch_decision()`
  - `_verify_claim()`
  - `_check_completion()`
- `src/harness/core/runtime_progress.py`
- `src/harness/core/budget.py`

Search keywords:

```text
software.build_result
software.test_result
verify_claim
completion.oracle
hard budget exceeded
targeted_verify
regression
```

## Root cause

The Harness has strong verification semantics but weak **workflow transition obligations** between execution and proof production.

A successful build command is only an observation. For it to become a verified fact, the Actor must later produce the correct proposal/claim shape and request verification.

If protocol or progress/recovery issues intervene, evidence exists but proof state is never promoted.

## Required correction

Do not automatically trust successful command output. Instead add a Kernel/Shell workflow bridge that can say:

```text
execution artifact satisfies candidate type X
→ candidate claim is available for Actor confirmation / deterministic framing
→ verifier remains authority
```

Alternative minimal direction:

- profile exposes `evidence_to_claim_candidates()` deterministic adapter;
- Actor chooses whether to propose;
- Kernel still verifies.

This reduces fragile manual JSON choreography without bypassing verification.

---

# P1-F — Retrieval capability availability and degraded operation

**Status: OPEN / PRACTICAL**

## Symptom

```text
retrieval gateway is unavailable
```

## Concrete locations

- `src/harness/core/runtime_retrieval_kernel.py`
  - `_build_retrieval_request()` raises `RetrievalUnavailable` if policy disabled/gateway missing.
- `src/harness/core/runtime_execution.py`
  - retrieval dispatch maps unavailable retrieval into failure/recovery.
- `src/harness/core/controller.py`
  - canonical decision language includes `retrieve`.
- context/model-visible capability construction should be reviewed to ensure unavailable retrieval is not advertised as a normal action.

Search keywords:

```text
RetrievalUnavailable
retrieval gateway is unavailable
retrieval_policy.enabled
kind == "retrieve"
retrieve.query
```

## Root cause

There are two different concerns:

```text
Core capability exists conceptually
vs
this run has a usable retrieval provider
```

If the Actor can choose `retrieve` when the current run has no provider, a capability configuration problem becomes an Actor failure/recovery event.

## Required correction

Use capability negotiation before model invocation:

```text
RunCapabilities
├─ retrieval_available
├─ write_tools
├─ shell_dialect
├─ approval_available
└─ provider output mode
```

Only advertise executable actions for the current run.

If retrieval becomes unavailable after startup, emit typed `CAPABILITY_UNAVAILABLE` / provider failure with a deterministic degraded path rather than repeatedly asking the Actor to rediscover the outage.

Core retrieval admission/trust rules remain unchanged.

---

# P1-G — Repeated read/tool family without phase transition obligation

**Status: OPEN / overlaps P0-A**

## Symptom

```text
directory.list
file.read
file.read
directory.list
...
```

## Root cause

There is a detector for repeated decisions, but no first-class workflow rule such as:

```text
After bounded inspection, either:
- enter reproduce/change,
- explain a specific missing-information dependency,
- or terminate/escalate.
```

Current `DomainWorkflowContract` describes phases as guidance, but the execution loop does not appear to enforce phase obligations as strongly as verification/recovery contracts.

## Required correction

Promote **phase transition constraints**, not Actor narrative, into deterministic control:

```text
inspect_budget
reproduce_budget
change_required_after_evidence_threshold
verify_required_after_mutation
```

The exact mechanism must be tested against legitimate large-repo exploration so it does not become another false-stuck detector.

---

# P1-H — Capability declaration has multiple levels of meaning

**Status: PARTIAL**

## Evidence

Historical `PHASE03_MODEL_GATEWAY.md` explicitly states:

```text
OpenAI-compatible Harness API = non-streaming
while provider capability metadata records streaming support
```

Current `model_capabilities.py` improved this by describing the capability consumed by the current Harness route and distinguishing output contract/enforcement.

However the codebase still has multiple capability surfaces:

- provider class capabilities;
- route capability inspection;
- config option declarations;
- docs phase descriptions;
- actual request construction.

## Risk

```text
provider supports X
!= route configured for X
!= Harness currently consumes X
```

## Required correction

Define three explicit namespaces if all are needed:

```text
provider_possible
route_enabled
harness_consumed
```

Never use a single `structured_output/streaming/native_tool_calling` boolean to mean all three.

---

# P1-I — MCP config parser vs executable capability

**Status: PARTIAL**

## Locations

- `src/harness/config.py`
  - `MCPServerConfig.__post_init__()` accepts `stdio` and `http`.
- `src/harness/config_contracts.py`
  - current executable contract rejects non-stdio for built-in MCP gateway.
- `src/harness/mcp_gateway.py`
  - built-in implementation is stdio.
- historical `docs/tracks/integration-runtime/PHASE06_MCP_PLUGIN.md`

## Current improvement

Unsupported HTTP is now rejected before first runtime action instead of failing during tool use.

## Remaining issue

The base config data model still communicates “HTTP is a valid built-in transport shape”. That may be acceptable only if the distinction is made explicit:

```text
schema-recognized extension transport
vs
built-in executable transport
```

Otherwise simplify the built-in config schema to current capability or introduce a transport registry whose registration makes a transport valid.

---

# P1-J — Plugin isolation and strict-mode feature disappearance

**Status: OPEN**

## Locations

- `src/harness/plugin_gateway.py`
- `src/harness/cli.py`
- `docs/tracks/integration-runtime/PHASE06_MCP_PLUGIN.md`
- `docs/tracks/integration-runtime/FAILURE_PROVIDER_RUNTIME_HARDENING_2026-08-24.md`

## Current truth

```text
Python module import executes host code
strict isolation therefore rejects plugin path
```

This is honest and safer than false sandbox claims.

## Root structural limitation

There is no isolated plugin-worker protocol, so security selection removes the extension rather than changing its execution backend.

## Future architecture

Agent Shell may introduce:

```text
Plugin Worker Process
→ serializable Tool Contract
→ capability manifest
→ sandbox backend
→ normalized ToolResult
```

The Core must remain unaware of Python import/module details.

---

# P1-K — Interactive approval gap

**Status: OPEN**

## Locations

- `docs/tracks/integration-runtime/PHASE06_MCP_PLUGIN.md`
- `docs/tracks/integration-runtime/PHASE13_TUI.md`
- `src/harness/core/tools.py` permission handling
- TUI/CLI composition.

## Current behavior

MCP default policy can produce:

```text
permission=confirm
```

but TUI v1 intentionally has no Kernel-owned interactive approval request/response mechanism. Approval-required calls therefore remain blocked unless policy is configured differently.

## Required split

```text
Core:
ApprovalRequest
ApprovalDecision
scope / expiry / provenance / replay policy

Shell:
render prompt
collect user choice
return decision
```

Do not make TUI itself an execution authority.

---

# P1-L — Context relevance quality vs trust governance

**Status: OPEN QUALITY LIMITATION / NOT A CORE TRUST FAILURE**

## Locations

- `docs/tracks/integration-runtime/PHASE07_CONTEXT_RELEVANCE.md`
- active context projector code
- `src/harness/core/context_compiler.py`
- model compatibility/context ablation tooling.

## Current design

Lexical deterministic overlap is intentionally used because it is replayable and Kernel-owned.

## Correct interpretation

This is safe but not necessarily good ranking.

Do not solve by letting an LLM silently decide truth or required evidence.

Possible architecture:

```text
Shell candidate ranking
  lexical / BM25 / embedding / semantic rerank
        ↓ untrusted ranking metadata
Core context admission/governance
        ↓
model-visible projection
```

Core preserves mandatory facts/trust boundaries; ranking mechanism remains replaceable and benchmarkable.

---

# P1-M — Reproducibility / seed gap

**Status: RESOLVED AS CURRENT CRITIQUE, historically valid**

Current hardening records/binds model route descriptor/revision into run config fingerprint and forwards integer seed for currently supported OpenAI-compatible/Ollama/LM Studio request paths.

Locations:

- `src/harness/model_gateway.py`
- `src/harness/core/runtime.py`
- `src/harness/core/runtime_persistence.py`
- `src/harness/config_contracts.py`
- `docs/handoff/05_VALIDATION_GATES.md`
- latest hardening record.

Remaining caution:

```text
seed supplied
!= provider guarantees deterministic output
```

Reproducibility evidence must record both request seed and empirical repeated-run variance.

---

# P2-N — Broad `except Exception` still requires boundary audit

**Status: PARTIAL**

Recent failure hardening resolves model/provider classification, but generic exception catches remain intentionally present in Runtime defensive boundaries.

Locations to inspect before future edits:

- `src/harness/core/runtime_execution.py`
- progress/retrieval/persistence mixins
- integration gateways.

Not every `except Exception` is wrong. The audit question is:

```text
Did a typed boundary exception already exist here?
If yes, broad wrapping destroys policy information.
If no, is this genuinely an unexpected Harness bug?
```

Use search keywords:

```text
except Exception
IMPLEMENTATION_ERROR
FailureContext
```

Future rule:

> Broad catch may be the final crash shield, but typed domain failures must be extracted before it.

---

# P2-O — Tool postcondition failure lacks domain-rich failure phase

**Status: OPEN / MODERATE**

## Symptom

```text
postcondition failed
```

may mean very different things:

```text
MCP returned isError
command output violated expected shape
file mutation did not produce expected state
build result adapter mismatch
```

## Root issue

Generic `ToolResult.ok/error` and ToolSpec postcondition give safety, but diagnostics/recovery can lack enough phase/type detail to select the next action.

## Proposed Tool Failure Context

Agent Shell/tool boundary should normalize:

```text
TOOL_SCHEMA
TOOL_PERMISSION
TOOL_CAPABILITY
TOOL_PRECONDITION
TOOL_TRANSPORT
TOOL_EXECUTION
TOOL_TIMEOUT
TOOL_POSTCONDITION
TOOL_AMBIGUOUS_EFFECT
```

with tool-call ID, backend, executable/transport, exit code and evidence ref where safe.

This is analogous to the model `FailureContext` hardening and should be considered only after the architecture reset contract is approved.

---

# P2-P — Checkpoint/resume exists, but workflow continuation can still be operationally weak

**Status: PARTIAL**

## Important distinction

Stage 03 persistence/resume is real and integrity-bound. Therefore “there is no resume” is incorrect.

The remaining problem is different:

> After a run stops due to repeated no-progress/budget/capability failure, the resumed Actor may not have a sufficiently explicit **next executable obligation** and can recreate the same trajectory.

## Locations

- `src/harness/core/runtime_recovery.py`
- controller-state persistence
- `HarnessState.pending_recovery`
- progress state
- context control namespace.

## Required improvement

Persist a recovery handoff object that is actionable but not truth-authoritative:

```text
failure boundary
last successful phase
blocked capability/tool
last attempted strategy
forbidden repeated action family
next required phase/action class
```

Resume should surface this before ordinary planning.

---

# Causal dependency graph

The main operational chain observed in software tasks is:

```text
Missing platform-neutral write/runtime tools       [P0-C/P0-D]
        ↓
Actor generates shell/OS-specific commands
        ↓
command fails or does not mutate workspace
        ↓
more inspect/read attempts                         [P1-G]
        ↓
no verified/profile milestone yet                  [P1-E]
        ↓
Stage-06 trusted progress remains zero              [P0-A]
        ↓
NO_PROGRESS / replan / strategy switch
        ↓
retrieval or alternative path attempted
        ├─ unavailable → capability failure          [P1-F]
        └─ more context/provider decisions
        ↓
protocol/tool error may occur                      [P0-B/P2-O]
        ↓
budget consumed
        ↓
hard budget exceeded
        ↓
resume contains state but weak next-action obligation [P2-P]
```

This graph explains why repeatedly fixing only JSON, only PowerShell, or only the no-progress threshold can improve one run while leaving the failure family intact.

---

# Highest-priority keywords for local audit

When working locally, start with these searches:

```text
# progress/liveness
rg -n "no_progress_streak|family_repeat_count|credit=0|task_progress_snapshot|strategy_exhausted" src tests docs

# shell/platform
rg -n "make_shell_tool|make_argv_tool|python3|/bin/sh|\.venv/bin|powershell|sys\.executable" src tests docs scripts

# retrieval capability
rg -n "RetrievalUnavailable|retrieval gateway is unavailable|kind == \"retrieve\"|retrieval_policy" src tests docs

# model boundary
rg -n "FailureContext|FailurePolicyEngine|NormalizedModelResponse|protocol_invalid_json|protocol_schema" src tests docs

# config/capabilities
rg -n "MCPServerConfig|transport.*http|structured_output|native_tool_calling|streaming|output_contract" src tests docs

# approvals/extensions
rg -n "approval|permission.*confirm|strict_tool_isolation|PluginGateway|MCPGateway" src tests docs

# broad error wrapping
rg -n "except Exception|IMPLEMENTATION_ERROR|postcondition failed" src tests
```

The local implementation proposal must cite the exact results of these searches before changing code.
