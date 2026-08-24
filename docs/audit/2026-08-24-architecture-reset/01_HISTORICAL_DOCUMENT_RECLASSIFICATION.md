# Historical Document Reclassification

Date: 2026-08-24

This document classifies repository material by **architectural epoch and current authority**. It does not physically move historical files because file movement would damage historical links, handoff references, and commit-level comparison.

---

# Epoch A — Genesis / Thin Context Harness

## Time boundary

Representative start:

- `35cbce265852ce5cc689ad1b4cfde14e3fb76221` — `feat: initialize base harness codebase` — 2026-06-30

## Product definition at the time

The initial `docs/architecture.md` described:

```text
single-agent, local-first MVP
raw user input/local files
→ bounded inspection
→ compact context packet
→ reasoning handoff
→ compact trace
```

The core modules were intake/classification/router/context-budget/packet/trace. It explicitly did not own managed agents, vector storage, MCP server execution, fabricated web/PDF behavior, or automatic experiment execution.

At the same time, the initial repository carried Codex-oriented skills/hooks/config. Historical examples included:

```text
.codex hooks
init-context
plan-work
implement-work
verify-work
/usr/bin/python3
$(git rev-parse ...)
```

## Current authority classification

- old `docs/architecture.md`: `SUPERSEDED-SHAPE` + `HISTORICAL-EVIDENCE`
- old Codex skills/hooks/config: `SUPERSEDED-SHAPE` + `HISTORICAL-EVIDENCE`
- bounded/local-first restraint: **retained as a meta design principle**, not as the current product API.

## Historical lesson

The original project did **not** intend to become a universal implementation of every model/OS/tool/provider surface. This matters when evaluating later Integration Runtime growth.

---

# Epoch B — Verified-State Research Kernel Convergence

## Time boundary

Primary convergence date: 2026-08-16.

Representative commits:

- Stage-02 production isolation work during 2026-08-16
- Stage-03 persistence/resume/reproducibility work during 2026-08-16
- `48fc5efa32ca50c77c31e86f01de649615811154` — `refactor: make research branch a standalone verified-state harness`
- Stage-04 semantic verification
- Stage-05 deterministic recovery
- Stage-06 deterministic progress
- Stage-07 context projection
- Stage-08 bounded retrieval / evidence hardening

## Canonical document families

### Stage 02 — Execution / trust boundary

Examples:

- `docs/STAGE2_DIRECTION_SUMMARY.md`
- `docs/STAGE2_EVIDENCE_MATRIX.md`
- `docs/STAGE2_RC2_IMPLEMENTATION_REPORT.md`
- `docs/STAGE2_RC2_FINAL_REREVIEW.md`
- `docs/STAGE2_RC2_EXIT_DECISION.md`

Classification:

- direction/invariants: `CANONICAL-INVARIANT`
- implementation/evidence/exit claims: `HISTORICAL-EVIDENCE` or `VALIDATION-EVIDENCE`, revision-bound

Important retained principles:

```text
Actor never owns trusted truth
Actor gets no live trusted state reference
evidence refs remain opaque
cwd != sandbox
mock/test attestation != production evidence
Actor/Verifier/Oracle authority boundaries remain distinct
negative evidence is preserved
stage exit is evidence-gated
```

### Stage 03 — Persistence / Resume / Reproducibility

Examples:

- `docs/STAGE3_PREFLIGHT_REREVIEW.md`
- `docs/STAGE3_DECISION_LOG.md`
- `docs/STAGE3_IMPLEMENTATION_REPORT.md`
- `docs/STAGE3_EVIDENCE_MATRIX.md`
- `docs/STAGE3_FINAL_REREVIEW.md`
- `docs/STAGE3_EXIT_DECISION.md`

Classification:

- persistence integrity rules: `CANONICAL-INVARIANT`
- implementation details: `HISTORICAL-EVIDENCE`
- old completeness claims must be read against newer manifest/model-route work.

### Stage 04 — Semantic Verification

Examples:

- `docs/STAGE4_IMPLEMENTATION_REPORT.md`
- `docs/STAGE4_EVIDENCE_MATRIX.md`
- `docs/STAGE4_FINAL_REREVIEW.md`
- `docs/STAGE4_EXIT_DECISION.md`

Classification:

- “model claims are not facts; verification promotes truth”: `CANONICAL-INVARIANT`
- specific verifier registry/version details: `HISTORICAL-EVIDENCE` unless corroborated by current source.

### Stage 05 — Recovery

Examples:

- `docs/STAGE5_PREFLIGHT_REREVIEW.md`
- `docs/STAGE5_IMPLEMENTATION_REPORT.md`
- `docs/STAGE5_EVIDENCE_MATRIX.md`
- `docs/STAGE5_FINAL_REREVIEW.md`
- `docs/STAGE5_EXIT_DECISION.md`

Classification:

- deterministic Kernel-owned recovery semantics: `CANONICAL-INVARIANT`
- old failure taxonomy: potentially superseded by 2026-08-24 `FailureContext` hardening.

### Stage 06 — Progress

Examples:

- `docs/STAGE6_PREFLIGHT_REREVIEW.md`
- `docs/STAGE6_IMPLEMENTATION_REPORT.md`
- `docs/STAGE6_EVIDENCE_MATRIX.md`
- `docs/STAGE6_FINAL_REREVIEW.md`
- `docs/STAGE6_EXIT_DECISION.md`

Classification:

- trusted progress must not be manufactured from Actor narration/activity: `CANONICAL-INVARIANT`
- exact no-progress heuristic: `CURRENT-CONTRACT` but **architecturally under re-review** because live task execution exposed a liveness/semantic-progress tension.

The Stage-06 final rereview itself documented two semantic limits:

```text
syntactically novel but semantically useless evidence
verified but goal-irrelevant facts
```

Those limits are now central audit inputs rather than minor future notes.

### Stage 07 — Context Governance

Examples:

- `docs/STAGE7_PREFLIGHT_REREVIEW.md`
- `docs/STAGE7_IMPLEMENTATION_REPORT.md`
- `docs/STAGE7_EVIDENCE_MATRIX.md`
- `docs/STAGE7_FINAL_REREVIEW.md`
- `docs/STAGE7_EXIT_DECISION.md`

Classification:

- trusted/untrusted/control separation and bounded projection: `CANONICAL-INVARIANT`
- a specific relevance/ranking algorithm is not canonical and may live in the Agent Shell/Context adapter.

### Stage 08 — Retrieval

Examples:

- `docs/STAGE8_PREFLIGHT_REREVIEW.md`
- later Stage-08 remediation/hardening docs

Classification:

- retrieved text remains untrusted and Kernel controls admission: `CANONICAL-INVARIANT`
- provider availability and retrieval strategy are integration-policy concerns and should not be confused with truth authority.

---

# Epoch C — Execution Boundary Operationalization

## Time boundary

2026-08-17 onward, immediately after the Verified-State stage convergence.

Representative evidence:

- structured argv/session binding tests
- Linux namespace session probes
- delayed-response session accumulation regression at `75834ac1ecb6c022771c2efee1f19495f356ee76`

## Meaning

The project moved from a mostly formalized/research Kernel toward a usable execution substrate:

```text
ToolCall
→ argv/shell/session abstraction
→ execution backend
→ observations/evidence
```

## Current authority classification

- execution authority and evidence boundary: `CANONICAL-INVARIANT`
- Linux namespace implementation: `CURRENT-CONTRACT` for supported Linux path
- shell syntax chosen by an Actor: **not** a canonical contract; it is an integration/runtime concern.

## Historical lesson

Stage 02 correctly insisted that `cwd` is not a sandbox. Later generic agent-shell responsibilities must be judged with the same rigor: a subprocess, PowerShell wrapper, OpenCode wrapper, or temp CWD cannot silently acquire an isolation claim.

---

# Epoch D — Integration Runtime Expansion

## Time boundary

Approximately 2026-08-18 through 2026-08-20.

The Integration Runtime track records starting integration baseline `75834ac1ecb6c022771c2efee1f19495f356ee76` and describes the added surface around the frozen Kernel.

## Main document family

`docs/tracks/integration-runtime/`

Key documents include:

- `README.md`
- `IMPLEMENTATION_REPORT.md`
- `POST_IMPLEMENTATION_AUDIT.md`
- `PHASE01_WORKSPACE.md`
- `PHASE02_CONFIG_SECRETS.md`
- `PHASE03_MODEL_GATEWAY.md`
- Agent Control / structured tool phases
- `PHASE06_MCP_PLUGIN.md`
- `PHASE07_CONTEXT_RELEVANCE.md`
- memory/domain/E2E/evaluation phases
- `PHASE13_TUI.md`

## Product expansion

The track explicitly added:

```text
workspace contract
config/secrets
Model Gateway
Agent Control
structured tool contracts
MCP/plugin gateway
context relevance
project memory
domain profiles
progress/recovery alignment
E2E/evaluation
CLI
TUI
```

## Current authority classification

- “integration is around a frozen Kernel”: `CANONICAL-INVARIANT`
- phase implementation documents: `HISTORICAL-EVIDENCE` and in some cases `STALE-CONTRACT-RISK`
- current source/CI/newer hardening docs override older implementation claims where they conflict.

## High-risk documents requiring current-source cross-check

### `PHASE03_MODEL_GATEWAY.md`

It explicitly records a non-streaming Harness API while capability metadata records provider streaming support. This is historically honest, but it also reveals that capability concepts were overloaded between:

```text
provider can theoretically support X
vs
current Harness route actually consumes X
```

Current `model_capabilities.py` was later changed to describe the route actually consumed by the Harness, so the old phase doc must not be used as the sole current capability contract.

Classification: `HISTORICAL-EVIDENCE` + `STALE-CONTRACT-RISK`.

### `PHASE06_MCP_PLUGIN.md`

It explicitly says:

```text
HTTP MCP represented in config but not implemented
Python plugin import = trusted host-code extension, not sandbox
interactive confirm path incomplete
strict isolation rejects MCP/plugin v1
```

Some failure-handling/config parts were hardened on 2026-08-24, but isolated plugin hosting and persisted approval remain open.

Classification: mixed `HISTORICAL-EVIDENCE` + active `OPEN-LIMITATION` content.

### `PHASE07_CONTEXT_RELEVANCE.md`

It intentionally implements deterministic lexical ranking and explicitly does not claim semantic relevance.

Classification: `CURRENT-CONTRACT` + known quality limitation, not a correctness bypass.

### `PHASE13_TUI.md`

TUI is deliberately a thin launcher/monitor and explicitly lacks an interactive persisted approval contract.

Classification: `CURRENT-CONTRACT` for thin-client boundary; approval limitation remains open.

---

# Epoch E — Windows / Live-Run Incident Remediation

## Time boundary

2026-08-20 through 2026-08-21.

Representative documents/commits:

- Windows artifact verification tests
- Windows content-addressed storage fixes
- `docs/tracks/integration-runtime/HARNESS_EVIDENCE_BASED_ARCHITECTURE_REVIEW_2026-08-21.md`
- TUI/runtime incident reports and CI remediation

## Main shift

For the first time, the repository's green Linux CI was confronted with substantial live Windows/provider behavior:

```text
artifact CRLF mismatch
empty tool name
invalid JSON / task graph
4K context overflow
```

## Current authority classification

- incident records: `INCIDENT-EVIDENCE`
- causal conclusions that were later fixed: `HISTORICAL-EVIDENCE`
- unresolved cross-platform patterns: active audit concerns.

## Historical lesson

This epoch showed a recurring failure mode in the development process itself:

> A deterministic Kernel invariant can be correct while the generic Agent Shell path that feeds it is operationally brittle.

That distinction must become explicit architecture, not only incident commentary.

---

# Epoch F — Memory / Context Compiler / Model Compatibility / OpenCode

## Time boundary

2026-08-22 through 2026-08-24.

Key current documents under `docs/tracks/integration-runtime/` include:

- `BASE_HARNESS_DEVELOPMENT_ARTIFACT_2026-08-24.md`
- `MODEL_CAPABILITIES_AND_OPENCODE_ADAPTER_2026-08-24.md`
- `MODEL_CAPABILITIES_OPENCODE_VALIDATION_2026-08-24.md`
- `MODEL_COMPATIBILITY_LAYER_V1_2026-08-24.md`
- `OPENCODE_MODEL_CATALOG_SELECTION_2026-08-24.md`
- `OPENCODE_PERSISTENT_AUTH_CONNECT_2026-08-24.md`
- context compiler / project memory related design and validation material

## Main shift

The project started treating heterogeneous model routes as an explicit compatibility problem:

```text
context adaptation
model/provider route capabilities
output protocol normalization
OpenCode as optional model transport
protocol benchmark
```

## Current authority classification

- OpenCode-specific docs: `HISTORICAL-EVIDENCE` / optional integration contract; **not** core architecture authority.
- Model compatibility contracts: useful `CURRENT-CONTRACT`, but belong primarily to Agent Shell/Model Boundary rather than Verified-State semantic core.
- P2 memory A-D: `PROPOSAL`, not stable implementation.

## Historical lesson

This work successfully separated several provider protocol failures, but it also demonstrates why provider/transport logic should be treated as a replaceable shell layer instead of becoming a reason to change Kernel truth semantics.

---

# Epoch G — Failure / Provider / Runtime Hardening

## Time boundary

2026-08-24.

Primary document:

- `docs/tracks/integration-runtime/FAILURE_PROVIDER_RUNTIME_HARDENING_2026-08-24.md`

Validated code source recorded there:

```text
c3083a51ed4de06ec88eca5605afd211baf327e2
418 passed, 7 skipped
Stage 02–08 listed gates PASS
```

## Resolved historical critiques

The following older critiques are now stale if stated as current facts:

- “FailureKind has no provider/protocol/workflow distinction.”
- “Controller owns provider retry/error interpretation.”
- “No common normalized provider response.”
- “seed is recorded without being sent by supported provider paths.”
- “command subprocess inherits arbitrary parent environment by default.”

The hardening introduced or recorded:

```text
FailureContext
FailurePolicyEngine
NormalizedModelResponse
Gateway-owned retry/fallback
config preflight/contracts
minimal command env + temporary cwd
MCP lifecycle state machine
profile/model snapshot isolation
model-route manifest fingerprint
seed forwarding
standardized diagnostics
```

## Still-open issues after the hardening

- arbitrary command/plugin processes do not have universal OS filesystem/network sandboxing;
- Python plugin import is still host-process trusted code;
- persisted interactive approval remains incomplete;
- HTTP MCP is parser-representable in `MCPServerConfig`, while executable contract rejects it pre-runtime;
- semantic context relevance remains intentionally limited;
- Stage-06 liveness/semantic-progress tension remains;
- retrieval unavailability/degraded operation policy remains a practical integration concern;
- platform-independent high-level file/build/test primitives remain incomplete if the Actor must still generate shell-specific command text for ordinary work.

---

# Epoch H — Architecture Reset Audit

## Time boundary

2026-08-24, this document set.

## Status

`PROPOSAL` + `META-REVIEW`, no runtime implementation is claimed.

## Purpose

Reframe the accumulated repository as two explicit systems:

```text
Agent Shell
  TUI / model / provider / input-output / tool adapters / OS / sessions / MCP hosting
         ↓ canonical contracts
Verified-State Core
  state / authority / evidence / verification / completion / durable recovery
```

This is a convergence plan around the existing Kernel, not a rewrite or an OpenCode/Codex-hosted plugin conversion.

---

# Current reading authority order

When documents disagree, use this order:

1. **Canonical invariants** in Stage-02/handoff architecture and current Verified-State README.
2. **Current executable source** and tests on the reviewed branch.
3. Latest causal/current-state hardening or audit document bound to a source SHA.
4. Integration Runtime phase docs as historical implementation rationale.
5. Stage implementation/exit docs as revision-bound evidence.
6. Initial June product docs as genesis intent/history, not current API.
7. Future proposal docs as non-implemented targets.

A green historical exit document must never override newer contrary runtime evidence.
