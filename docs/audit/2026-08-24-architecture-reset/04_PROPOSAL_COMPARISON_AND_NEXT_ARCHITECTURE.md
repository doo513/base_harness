# Proposal Comparison and Next Architecture

Date: 2026-08-24

This is a **proposal**, not an implementation record.

The purpose is to compare the current/previous development direction against the architecture audit **before** recommending local code work.

---

# 1. Proposal A — continue hardening the current integrated runtime

This is the direction followed through recent work:

```text
existing Runtime
→ fix model protocol
→ fix provider failure taxonomy
→ fix context budget
→ fix OpenCode route
→ fix config/preflight
→ fix MCP lifecycle
→ fix provenance
→ continue fixing live failures
```

## Strengths

1. Preserves working code and regression history.
2. Small changes are easy to validate individually.
3. Several serious defects were genuinely fixed this way:
   - Windows artifact byte identity;
   - model protocol classification;
   - context-window compiler;
   - provider retry ownership;
   - failure diagnostics;
   - seed/model-route provenance;
   - MCP lifecycle cleanup.
4. Avoids risky large rewrite.

## Weaknesses

1. Each fix begins from the **location where the symptom surfaced**, not necessarily the layer that should own the behavior.
2. Generic agent infrastructure remains spread across:

```text
src/harness/core/*
src/harness/model_gateway.py
src/harness/model_protocol.py
src/harness/mcp_gateway.py
src/harness/plugin_gateway.py
src/harness/tui*.py
src/harness/cli.py
profiles
```

3. Progress/recovery can still react to Shell failures because the architecture has no explicit Shell/Core liveness contract.
4. Ordinary development work still relies heavily on shell/argv for mutation, which makes model reasoning carry OS/toolchain details.
5. Every new provider/MCP/plugin/runtime feature risks adding another path that must be reconciled with Core semantics.

## Meta verdict

**Do not discard the fixes. Do not continue this as the primary architecture strategy.**

Use it only for confirmed correctness/security defects while the structural boundary is being established.

---

# 2. Proposal B — host `base_harness` inside OpenCode/Codex/another agent

Concept:

```text
OpenCode / Codex runtime
        ↓ plugin/hooks
Verified-State logic
```

## Strengths

- fast access to mature file editing, terminal, provider, session, UI, and OS behavior;
- likely higher short-term task success;
- less generic Agent Runtime code to maintain.

## Weaknesses

- product identity and lifecycle become tied to another agent;
- host runtime changes can alter behavior outside our controlled release boundary;
- experimental attribution becomes difficult:

```text
model effect
vs host-agent prompt/tool effect
vs base_harness effect
```

- some host tool execution may occur before/around the Kernel boundary unless integration is extremely strict;
- difficult to make `base_harness` independently usable.

## Meta verdict

**Reject as the primary product architecture.**

Keep OpenCode/etc. as optional adapters and comparative references.

---

# 3. Proposal C — standalone Agent Shell + Verified-State Core

This is the recommended direction.

```text
┌─────────────────────────────────────────────┐
│ base_harness Agent Shell                    │
│                                             │
│ TUI / CLI                                   │
│ Model Gateway + providers                   │
│ LLM input/output adaptation                 │
│ Tool implementations                        │
│ File/process/OS abstraction                 │
│ MCP/plugin hosting                          │
│ Retrieval providers                         │
│ Approval presentation                       │
│ Session/workspace UX                        │
└──────────────────┬──────────────────────────┘
                   │ Canonical Ports
┌──────────────────▼──────────────────────────┐
│ Verified-State Core                        │
│                                             │
│ Goal Contract                               │
│ Verified State                              │
│ Authority / Evidence                        │
│ Verification                                │
│ Completion Oracle                           │
│ Durable Failure/Recovery Meaning            │
│ Trusted Progress                            │
│ Admission / Replay / Provenance             │
└─────────────────────────────────────────────┘
```

This is **not** another-agent shell. It is our own shell using design patterns proven by existing agents.

---

# 4. Required canonical ports

Do not begin by moving files. First define the contracts the two halves are allowed to exchange.

## 4.1 Actor Port

```text
Core → ActorRequest
Shell → CanonicalDecision | ActorBoundaryFailure
```

`ActorRequest` contains model-visible projection and currently available capabilities, not live mutable state objects.

The Shell may use:

```text
OpenAI
Anthropic
Gemini
Ollama
LM Studio
OpenCode optional adapter
```

but the Core only sees `CanonicalDecision`.

## 4.2 Tool Port

```text
Core → CanonicalToolCall
Shell Tool Adapter → CanonicalToolOutcome
```

Core owns:

```text
permission decision
capability decision
idempotency/receipt policy
evidence admission
```

Shell owns:

```text
pathlib/subprocess/platform behavior
command resolution
OS dialect
MCP/plugin transport
```

## 4.3 Failure Port

```text
Shell failure
→ FailureContext
→ Core recovery policy
```

Transport-specific exception classes never become Core routing APIs.

## 4.4 Retrieval Port

```text
Actor requests retrieve
→ Core policy framing
→ Shell provider execution
→ candidate results
→ Core admission/trust
```

Run capability negotiation must prevent unavailable providers from being advertised as ordinary actions.

## 4.5 Approval Port

```text
Core → ApprovalRequest
Shell → user interaction
Shell → ApprovalDecision
Core → persist/provenance/policy application
```

TUI never directly approves a tool outside Core policy.

## 4.6 Execution-Liveness Port

This is separate from trusted progress.

Shell/tool/runtime emits diagnostic execution transitions:

```text
inspected
mutation_attempted
workspace_changed
build_started/build_finished
test_started/test_finished
capability_unavailable
```

Core may use these only under a bounded liveness/phase policy. They never become trusted facts or accepted progress by themselves.

---

# 5. Recommended local work sequence

The order below deliberately avoids a big-bang rewrite.

## R0 — Historical audit freeze

**Goal:** establish the documents in this directory as the review baseline.

Actions:

- no semantic code changes;
- local clone `develop`;
- record exact source SHA;
- rerun current CI/test baseline locally where practical;
- retain the existing generated CI evidence separately.

Exit condition:

```text
current source understood
current tests reproducible enough for local work
no uncommitted accidental changes
```

Meta question before R1:

> Are we fixing a current defect, or changing the architecture based only on historical/stale criticism?

---

## R1 — Contract fence, no large file moves

**Goal:** make Shell/Core responsibilities mechanically inspectable before reorganizing packages.

Define/freeze canonical contract types for:

```text
CanonicalDecision
ActorBoundaryFailure / FailureContext
CanonicalToolCall
CanonicalToolOutcome
RunCapabilities
ApprovalRequest / ApprovalDecision
Retrieval provider result boundary
ExecutionLivenessEvent
```

Add architecture/import tests:

```text
Core must not import TUI
Core must not import OpenCode/provider SDK implementation
Core must not depend on PowerShell/bash syntax
Core policy must not branch on provider exception class
```

Do **not** rename/move the whole repository yet.

Exit condition:

- old behavior still passes;
- contract boundary is testable;
- no dual authority created.

Meta question before R2:

> Does each proposed contract contain only information needed by the receiving layer, or are we leaking provider/OS implementation details into Core?

---

## R2 — Portable developer tool primitives

**Why this comes early:** current live failures are strongly amplified by shell dialect leakage.

Implement Shell-side, workspace-scoped primitives such as:

```text
file.read          existing
file.search        existing
directory.list     existing
file.write         new
file.patch         new
file.delete        optional/permissioned
directory.create   new
process.run(argv)  standardized
runtime.resolve    new
```

Rules:

- use Python/platform APIs where possible;
- no shell required for ordinary file edits;
- preserve existing ActionRuntime permission/evidence path;
- shell remains explicit escape hatch;
- Windows and POSIX contract tests mandatory.

Exit evidence should include the previously failing class:

```text
create/modify Python file on Windows
run current Python interpreter
run pytest via resolved interpreter
```

Meta question before R3:

> Did success improve because the abstraction is portable, or did we merely special-case Windows command strings?

---

## R3 — Separate Trusted Progress from Execution Liveness

Do this **after** portable tools exist; otherwise liveness design will be tuned around broken shell behavior.

Keep trusted progress rules intact.

Add bounded phase/liveness control:

```text
OBSERVE
REPRODUCE
CHANGE
VERIFY
RECOVER
```

Example constraints:

- OBSERVE has bounded read/search budget;
- CHANGE requires actual workspace mutation or an explicit blocked reason;
- mutation should transition toward VERIFY;
- VERIFY requires execution/evidence-producing action;
- RECOVER is tied to FailureContext and forbids unrelated repeated exploration.

No liveness event gets truth authority.

Required tests:

```text
legitimate read→read→patch→test does not false-trigger
endless distinct reads still terminates
alternating tool families cannot evade phase budget
failed mutation does not count as trusted progress
resume restores phase/liveness obligation
```

Meta question before R4:

> Have we preserved Stage-06 anti-gaming guarantees while reducing false stuck detection?

---

## R4 — Capability-aware Actor input

Create one `RunCapabilities` snapshot at run start and update it only through explicit durable capability transitions.

Examples:

```text
retrieval_available
approval_available
workspace_write_available
shell_available
shell_dialect
python_runtime
mcp servers/tools available
output contract/enforcement
```

The model-visible action contract should not advertise impossible operations.

Key case:

```text
retrieval_gateway=None
→ Actor should not be encouraged to emit retrieve
```

If a capability fails after startup, emit one typed capability/provider failure and a deterministic degraded policy.

Meta question before R5:

> Are unavailable capabilities removed from presentation without silently weakening Core policy?

---

## R5 — Tool failure normalization

Apply the successful model-boundary hardening pattern to tools.

Canonical tool failure phases:

```text
schema
permission
capability
precondition
transport
execution
timeout
postcondition
ambiguous_effect
```

Do not route everything through generic `TOOL_ERROR` text.

The purpose is targeted recovery and diagnostics, not more exception classes.

Meta question before R6:

> Does the recovery policy depend on canonical observable failure context rather than implementation exception hierarchy?

---

## R6 — Durable approval contract

Add Core-owned request/decision persistence, then connect TUI as presenter.

Required properties:

- explicit scope;
- one-shot/session/run duration defined;
- user identity/provenance where available;
- resume semantics;
- deny cannot be silently converted to fallback allow;
- approval decision does not become evidence/truth by itself.

Meta question before R7:

> Could the same approval be replayed after resume or route change in a way the user did not authorize?

---

## R7 — Retrieval/context provider separation

Keep:

```text
Core trust/admission/mandatory context
```

Move/standardize:

```text
lexical/BM25/vector/semantic candidate ranking
provider availability
query execution
```

as replaceable Shell strategies.

Benchmark lexical baseline before semantic additions. Semantic ranking result is untrusted prioritization metadata.

Meta question before R8:

> Does semantic ranking only affect visibility/order, or did it accidentally gain truth/progress authority?

---

## R8 — Isolated extension workers

Only after R1–R7 are stable.

Design a serializable plugin/MCP worker boundary if strict-mode extension use is a real requirement.

Do not rush this into the Core.

Possible structure:

```text
Shell extension host
→ isolated worker/backend
→ tool manifest
→ canonical tool outcome
→ Core ActionRuntime/evidence
```

Meta question:

> Is the isolation property actually attested by the backend, or are we repeating the old `subprocess/cwd = sandbox` mistake?

---

## R9 — Physical package reorganization

Only now consider moving modules.

Possible target, subject to local import analysis:

```text
src/harness/core/               existing semantic Kernel
src/harness/agent_runtime/      model/input-output/tool/platform/session
src/harness/interfaces/         canonical ports if cyclic imports justify it
src/harness/integrations/       MCP/plugin/OpenCode/provider adapters
src/harness/ui/                 TUI/CLI presentation
```

Do not move files merely for aesthetics. The import graph and contract tests should prove the boundary first.

---

# 6. Comparison table

| Criterion | A. Continue patching | B. Host-agent plugin | C. Own Shell + Core |
|---|---:|---:|---:|
| Preserve Verified-State authority | High | Medium–High if carefully wrapped | **High** |
| Short-term task success | Medium | **High** | Medium → High |
| Independent product | High | Low | **High** |
| OS/tool maturity immediately | Low–Medium | **High** | Medium |
| Experimental attribution | Medium | Low | **High** |
| Maintenance burden | High | Low–Medium | Medium–High |
| Structural clarity long term | Low if continued indefinitely | Medium | **High** |
| Reuse current work | High | Partial | **Very high** |
| Big rewrite risk | Low per patch / high cumulative | Medium | **Low if staged** |

Recommendation: **Proposal C**.

---

# 7. What must NOT happen during the reset

1. Do not create a new branch tree explosion; continue controlled local work from the chosen development branch unless intentionally snapshotting.
2. Do not rewrite Stage 02–08 invariants to make Agent Shell integration easier.
3. Do not give TUI/model/provider direct state-commit or completion authority.
4. Do not count arbitrary activity as trusted progress.
5. Do not add provider/OS names to Core recovery policy.
6. Do not physically reorganize packages before canonical port tests exist.
7. Do not introduce semantic ranking before lexical baseline/ablation is preserved.
8. Do not claim subprocess/temp cwd/plugin worker as isolation without backend evidence.
9. Do not resolve a live failure by weakening verifier/oracle acceptance.
10. Do not implement several reset phases in one large commit; each phase gets its own meta review.

---

# 8. Proposal acceptance gate

Before local implementation begins, compare every planned work item to these questions:

```text
1. Which canonical invariant does this protect or enable?
2. Is this Core semantics or Agent Shell mechanism?
3. Is there already a current implementation that solves the stated historical critique?
4. What exact live symptom/evidence motivates the change?
5. What regression proves the old failure and the new behavior?
6. Could this change create a second authority path?
7. Could it reduce portability or reproducibility?
8. What is explicitly NOT being solved in this slice?
```

If these cannot be answered, implementation should not start.
