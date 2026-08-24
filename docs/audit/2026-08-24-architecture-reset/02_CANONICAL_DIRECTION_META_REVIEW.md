# Canonical Direction Meta Review

Date: 2026-08-24

## Executive conclusion

The evidence does **not** justify discarding the Verified-State Core. The central authority model remains coherent and has repeatedly survived adversarial review:

```text
Actor proposes
Harness executes
Evidence is durable/integrity-bound
Verifier promotes truth
Oracle accepts completion
```

The primary structural problem is different:

> The repository gradually combined two systems — a Verified-State trust Kernel and a general-purpose Agent Runtime — without making their interface a first-class architectural boundary.

As a result, failures in model serialization, provider transport, OS command dialect, retrieval availability, extension hosting, and interactive UI can feed directly into Kernel progress/recovery behavior. The Kernel then appears unreliable even when its truth/authority rules are behaving exactly as designed.

The correct direction is therefore **Core/Shell separation and contract convergence, not rewrite**.

---

# 1. Review model

Every major feature is judged against two historical criteria.

## Criterion A — Genesis restraint

From the 2026-06-30 architecture:

```text
bounded
local-first
small context handoff
avoid unnecessary ownership of external runtime features
```

Question:

> Did this feature need to become part of the trusted semantic Kernel, or could it have remained replaceable infrastructure?

## Criterion B — Verified-State authority

From the 2026-08-16 standalone pivot and handoff architecture:

```text
Unverified Claim != Trusted Fact
Completion Request != Completion
Observation != Truth
Memory != Current State
Subagent Output != Trusted State
```

Question:

> Does the feature preserve the invariant that only the Harness's explicit verification/authority path changes trusted state or accepted completion?

Criterion B has priority over Criterion A. Criterion A is a complexity/restraint check; Criterion B is a correctness/security boundary.

---

# 2. What should remain in the Verified-State Core

The following responsibilities are justified by the canonical invariant and should remain first-class Core responsibilities.

## 2.1 Goal / acceptance contract

Why Core-owned:

- defines what completion means;
- cannot be delegated to model/provider/UI;
- participates in replay/config equivalence.

Verdict: **RETAIN IN CORE**.

## 2.2 Durable state and authority

Includes:

```text
facts
hypotheses
observations metadata
claim status
authority
agent control state
recovery state
progress state
retrieval admission metadata
```

Why Core-owned:

- this is the central security/reliability subject of the project.

Verdict: **RETAIN IN CORE**.

## 2.3 Evidence and artifact integrity

Why Core-owned:

- verification depends on exact evidence identity;
- persistence/replay guarantees require one authority.

Verdict: **RETAIN IN CORE**.

## 2.4 Verification and completion oracle

Why Core-owned:

- directly implements `proposal != truth` and `request != completion`.

Verdict: **RETAIN IN CORE**.

## 2.5 Durable recovery policy

The Core must own the durable meaning of:

```text
retry requested
replan required
strategy switch
rollback
checkpoint stop
escalation
```

But it does **not** need to know OpenAI, OpenCode, PowerShell, HTTP, or a specific MCP transport to make those decisions.

Verdict: **RETAIN POLICY IN CORE; MOVE TRANSPORT DETAILS OUT**.

## 2.6 Progress semantics

Trusted task/epistemic progress must remain Core-owned because allowing the Actor to declare progress defeats Stage 06.

However, the current model needs refinement; see Section 6.

Verdict: **RETAIN TRUSTED PROGRESS IN CORE; SEPARATE EXECUTION LIVENESS**.

---

# 3. What should become an explicit Agent Shell

These components are necessary for a standalone product, but their implementation should not define Verified-State semantics.

```text
TUI / CLI presentation
Model Gateway transports
provider SDKs/auth
LLM request construction
provider-native structured output mapping
context serialization/tokenization adapters
file/process/search tools
OS dialect/runtime discovery
MCP transport clients
plugin worker hosting
interactive approval UI
workspace/session UX
```

The Shell may implement these mechanisms, but it communicates with the Core only through canonical contracts.

Proposed boundary:

```text
┌──────────────── Agent Shell ────────────────┐
│ TUI / CLI                                   │
│ Model providers / auth / token budgets      │
│ Input builder / output decoder              │
│ Tool adapters / OS runtime                  │
│ MCP / plugin transports                     │
│ Approval presentation                       │
└────────────────────┬─────────────────────────┘
                     │
        Canonical Core Contracts
                     │
┌────────────────────▼─────────────────────────┐
│ Verified-State Core                         │
│ Goal / State / Evidence / Verification      │
│ Completion / Durable Recovery / Truth       │
└──────────────────────────────────────────────┘
```

This keeps `base_harness` independent. OpenCode/Codex/other agents are references or optional adapters, not host runtimes.

---

# 4. Historical expansion review

## 4.1 Genesis → standalone Verified-State pivot

### Assessment

**Appropriate intentional redesign.**

The June thin context harness and August Verified-State standalone Kernel are different products. Treating the transition as accidental scope creep would be inaccurate because commit `48fc5efa...` explicitly made the research branch standalone and removed old Codex-oriented integration artifacts.

### Meta finding

The standalone decision was not itself the structural error. The later problem was failing to make a second distinction:

```text
standalone product
≠
all product mechanisms belong inside semantic Kernel
```

---

## 4.2 Stage 02–05: isolation, persistence, verification, recovery

### Assessment

**Strong alignment with canonical direction.**

These stages directly implement the Verified-State thesis. They also show good methodological discipline:

```text
fail closed
negative evidence retained
stage-specific exit criteria
real isolation when claimed
replay integrity
verification authority separation
```

### Meta finding

Do not rewrite these stages to simplify Agent Shell work. They are the asset to preserve.

---

## 4.3 Stage 06 progress control

### Original reasoning

Correctly rejected:

```text
model narration = progress
new artifact ref = progress
speculative hypothesis churn = progress
strategy switch = progress
```

### Structural tension exposed later

Current implementation grants zero reset authority to successful activity unless it changes a verified fact or profile-defined milestone.

That is correct for **trusted progress**, but the same variable is also used to decide whether the Actor is operationally stuck.

These are not identical questions:

```text
A. Did trusted task knowledge advance?
B. Is the executor making bounded, useful movement toward the next verification point?
```

A model may legitimately need several operations:

```text
inspect files
→ inspect another file
→ modify file
→ run compile
→ run test
→ verify claim
```

before any new verified fact is committed.

If A and B share one counter, the system can falsely classify a healthy intermediate trajectory as no-progress. Conversely, if arbitrary activity resets the counter, a model can loop forever by producing novel reads.

### Verdict

**CORE CONCEPT RETAIN; CONTROL MODEL REVISE.**

Do not give activity trusted progress credit. Instead add a separate bounded execution-liveness/phase mechanism outside trusted progress accounting.

---

## 4.4 Stage 07/08 context and retrieval

### Strength

Trust separation is correct:

```text
relevant != trusted
retrieved != instruction
memory != current state
```

### Structural issue

Selection/provider mechanisms became increasingly tied to Kernel execution flow even though relevance and transport are replaceable strategies.

Examples:

- lexical deterministic relevance is safe but low quality;
- a missing retrieval gateway can become a typed runtime failure after the Actor chose `retrieve`;
- model-visible decision vocabulary may still make an unavailable retrieval action conceptually possible.

### Verdict

**KEEP admission/trust in Core; move ranking/provider/capability presentation to Shell/adapters.**

The Core should accept or reject an already-framed retrieval request/result under policy. The Agent Shell should ensure unavailable capabilities are not advertised as normal actions.

---

## 4.5 Integration Runtime Track

The track says it adds practical integration around a frozen Kernel, which is the correct intent.

The problem is that the codebase did not enforce that sentence as a module/contract boundary strongly enough.

### Good decisions

- TUI thin client rather than second authority;
- external tool paths normalize into ActionRuntime;
- MCP annotations remain untrusted hints;
- plugin import risk explicitly acknowledged;
- model/provider output never gains truth/completion authority.

### Problematic coupling patterns

#### Pattern 1 — theoretical provider capability vs consumed route capability

Historical `PHASE03_MODEL_GATEWAY.md` recorded a provider as streaming/native-tool capable while Harness execution remained non-streaming/text-decision based.

This did not break truth authority, but it created two meanings of “capability”:

```text
provider can support
vs
Harness route currently uses
```

Later `model_capabilities.py` corrected the route-level view, showing this should have been a shell contract from the start.

#### Pattern 2 — declared configuration broader than executable implementation

`MCPServerConfig` historically accepts `http`, while MCP execution is stdio-only. New config preflight now fails early, which is safer, but the parser-level schema still represents a capability the built-in runtime cannot instantiate.

This is a contract layering smell even if runtime failure has moved earlier.

#### Pattern 3 — extension/security trade-off becomes feature disappearance

Python plugin import is host-process trusted code. Strict isolation therefore rejects it. This is honest, but it means the integration mechanism has no isolated alternative.

The unresolved issue is not “strict mode too strict”; it is:

> the Agent Shell does not yet provide an isolated plugin worker contract.

#### Pattern 4 — approval belongs to Core policy + Shell interaction, but the bridge is missing

TUI intentionally does not fabricate approval authority, which is correct. However, without a durable Core approval request/response contract and a Shell presenter, `permission=confirm` becomes operationally unusable in autonomous runs.

### Verdict

**INTENT CORRECT; MODULE BOUNDARY UNDER-SPECIFIED.**

---

# 5. Current critique re-evaluation

The supplied critique contains a mixture of current, historical, and resolved observations.

## 5.1 FailureKind/provider/model separation

Older observation: valid historically.

Current status after 2026-08-24 hardening:

```text
MODEL_PROVIDER_ERROR
MODEL_PROTOCOL_ERROR
ACTOR_WORKFLOW_ERROR
IMPLEMENTATION_ERROR
FailureContext
FailurePolicyEngine
```

Verdict: **RESOLVED AS STATED; continue testing, do not redesign again without evidence.**

## 5.2 Controller/provider retry coupling

Older observation: valid historically.

Current hardening centralizes same-route retry/fallback in ModelGateway/FailurePolicyEngine and removes Controller provider reinterpretation/semantic repair.

Verdict: **RESOLVED AS STATED.**

## 5.3 normalized response contract

Current hardening introduces `NormalizedModelResponse` and one canonical decoder.

Verdict: **RESOLVED AS STATED.**

## 5.4 seed reproducibility gap

Historically valid. Latest hardening binds model route descriptor/revision to manifest and forwards integer seed through supported provider paths.

Verdict: **RESOLVED FOR CURRENT SUPPORTED PROVIDER PATHS; benchmark determinism still needs empirical evidence.**

## 5.5 HTTP MCP config mismatch

Partially hardened: executable contract rejects unsupported transport before runtime use.

But `MCPServerConfig` still recognizes `http` as a syntactically valid transport.

Verdict: **PARTIAL / CONTRACT CLEANUP REMAINS.**

## 5.6 plugin isolation

Still real.

Verdict: **OPEN STRUCTURAL LIMITATION.**

## 5.7 interactive approval

Explicitly documented as future work in TUI and MCP phase docs.

Verdict: **OPEN STRUCTURAL LIMITATION.**

## 5.8 semantic context ranking

Lexical ranking intentionally does not claim semantic relevance.

Verdict: **OPEN QUALITY/COST LIMITATION, not a trust-integrity failure.**

## 5.9 model/provider capability contract drift

Route-level capability work improved this, but old `ProviderCapabilities`, phase docs, and route capability reports can still communicate different meanings.

Verdict: **OPEN DOCUMENT/API CONVERGENCE ISSUE.**

## 5.10 Windows/OS command behavior

There is evidence of Windows-specific persistence bugs being corrected, but the more general problem remains if ordinary file/build/test work is expressed by model-generated shell strings.

```text
cat <<EOF
python3
.venv/bin/python
```

are not portable Agent actions.

Verdict: **OPEN AGENT-SHELL ABSTRACTION ISSUE.**

---

# 6. The most important structural correction: Progress != Liveness

This is the most important unresolved conceptual issue identified by the audit.

## Current safe principle

```text
activity cannot promote trusted progress
```

Keep it.

## Current problematic implication

```text
no trusted progress for N decisions
→ Actor is stuck
```

This is too strong for multi-step implementation work.

## Proposed conceptual split

### Trusted Progress

Core-owned, high authority:

```text
verified fact advanced
profile milestone advanced
accepted transition/evidence-backed task state advanced
```

Can reset long-horizon semantic progress and influence evaluation.

### Execution Liveness

Shell/Core-control observation, **zero truth authority**:

```text
new relevant file inspected
workspace patch committed
build state changed
compile phase completed
test phase entered
new failure class discovered
recovery directive consumed
```

It must not grant task success. It only answers whether execution is moving through a bounded phase.

### Why naive activity credit is still forbidden

```text
directory.list(A)
directory.list(B)
directory.list(C)
...
```

must not produce unlimited liveness.

The solution is phase/obligation budgets, not activity-as-progress:

```text
OBSERVE phase: bounded reads/searches
CHANGE phase: mutation required or explicit reason to remain observe-only
VERIFY phase: execution/verification action required
RECOVER phase: specific failure-directed action required
```

Each phase has allowed action families and a bounded transition horizon. This preserves Stage-06 safety while preventing false no-progress during normal implementation sequences.

---

# 7. Meta verdict by architecture layer

| Layer | Verdict | Reason |
|---|---|---|
| Goal/contract | Retain | Core authority. |
| Verified state | Retain | Core thesis. |
| Evidence/artifact | Retain | Core thesis. |
| Verification/oracle | Retain | Core thesis. |
| Durable recovery meaning | Retain/refine | Core-owned, transport-neutral. |
| Trusted progress | Retain/refine | Correct authority, needs liveness separation. |
| Context trust governance | Retain | Core authority. |
| Context ranking/tokenization | Shell/adapters | Replaceable strategy. |
| Retrieval admission/trust | Core | Security/authority. |
| Retrieval provider/search | Shell/adapters | Optional infrastructure. |
| Model Gateway | Agent Shell | Transport/capability infrastructure. |
| Provider output decoder | Agent Shell boundary | Must normalize to canonical Decision. |
| TUI/CLI | Agent Shell | Presentation only. |
| File/process/OS tools | Agent Shell | Platform abstraction. |
| MCP transport | Agent Shell | External integration. |
| Plugin hosting | Agent Shell | External integration/isolation. |
| Approval policy record | Core | Authority/provenance. |
| Approval prompt/UI | Shell | Interaction. |

---

# 8. Final meta conclusion

The project should not be reframed as:

```text
Verified-State was wrong
→ replace with OpenCode/Codex
```

Nor should it continue as:

```text
new live symptom
→ add another special case inside Runtime
```

The evidence supports:

```text
Verified-State Core = preserve
Integration Runtime = refactor into explicit Agent Shell
Cross-layer contracts = reduce and freeze
Live failures = classify by boundary before patching
```

This is the architectural baseline used by the causal problem atlas and the next proposal.
