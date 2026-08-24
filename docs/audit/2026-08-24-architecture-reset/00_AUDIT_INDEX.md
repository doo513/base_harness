# Base Harness Historical Architecture Audit — Index

Date: 2026-08-24  
Branch reviewed: `develop`  
Purpose: historical reclassification, canonical-direction review, causal problem mapping, and proposal comparison before further local implementation.

## 0. Why this audit exists

Recent live runs exposed symptoms such as:

```text
consecutive Actor decisions produced no recognized progress
model boundary failed
retrieval gateway is unavailable
hard budget exceeded
```

Those symptoms must not be treated as isolated bugs until the repository's design history is reconstructed. `base_harness` changed product shape at least twice:

1. the repository began as a thin, local-first context/intake harness;
2. it was deliberately converted into a standalone Verified-State Harness;
3. a later Integration Runtime track added TUI, model/provider, MCP/plugin, context relevance, memory, domain profiles, and E2E plumbing around the frozen Kernel.

Therefore this audit separates **historical product shape** from **canonical trust/authority invariants**.

---

## 1. Absolute review criteria

### 1.1 Genesis intent — architectural restraint

Evidence: initial commit `35cbce265852ce5cc689ad1b4cfde14e3fb76221`, especially the then-current `docs/architecture.md`.

The initial product was:

```text
single-agent
local-first
bounded input reduction
compact reasoning handoff
small trace
```

It explicitly did not attempt to own every agent/runtime capability.

This is retained as a **restraint principle**:

> Do not pull generic agent-shell complexity into the trust Kernel unless the Kernel must own it to preserve an authority or evidence guarantee.

### 1.2 Canonical Verified-State invariants — highest authority

Evidence: standalone pivot `48fc5efa32ca50c77c31e86f01de649615811154`, `docs/STAGE2_DIRECTION_SUMMARY.md`, and `docs/handoff/01_ARCHITECTURE.md`.

These are the non-negotiable criteria for current architecture:

1. Actor/model output is an untrusted proposal, never trusted truth.
2. Only Harness-side verification can promote trusted facts.
3. A model completion request is not accepted completion.
4. Tool execution authority remains Harness-owned.
5. Evidence admission, integrity, persistence, replay, and completion remain Harness-owned.
6. Retrieval/memory/skills/plugins/model output cannot gain instruction, truth, progress, or completion authority by being present.
7. Isolation claims must be evidence-backed; `cwd`, subprocess, mocks, or test attestation must not be described as stronger isolation than they provide.
8. Recovery/progress policy must be deterministic and Kernel-owned where it changes durable run semantics.
9. Documentation contract, executable contract, and validation evidence must not contradict one another.
10. Optional integration surfaces must not silently redefine the Verified-State Kernel.

### 1.3 New boundary criterion derived from the history

The current audit adds one architectural test without changing the invariants above:

```text
Agent Shell / Integration Infrastructure
        must be replaceable
              ↓
Canonical Kernel Contracts
              ↓
Verified-State Core
```

TUI, provider SDKs, model transports, OS/shell adaptation, MCP transports, plugin hosting, workspace UI, and session presentation belong outside the semantic trust core unless they implement one of the canonical contracts.

This criterion is a refinement intended to preserve both the original architectural restraint and the later Verified-State authority model.

---

## 2. Audit documents

Read in this order:

1. [`01_HISTORICAL_DOCUMENT_RECLASSIFICATION.md`](01_HISTORICAL_DOCUMENT_RECLASSIFICATION.md)  
   Reclassifies repository documents and representative commits by historical epoch and current authority.

2. [`02_CANONICAL_DIRECTION_META_REVIEW.md`](02_CANONICAL_DIRECTION_META_REVIEW.md)  
   Reviews each major design expansion against the canonical criteria and identifies where the Kernel remained sound versus where the shell/core boundary blurred.

3. [`03_CAUSAL_PROBLEM_ATLAS.md`](03_CAUSAL_PROBLEM_ATLAS.md)  
   Maps current and historical symptoms to root causes, amplification chains, concrete files/functions/docs, search keywords, and current disposition.

4. [`04_PROPOSAL_COMPARISON_AND_NEXT_ARCHITECTURE.md`](04_PROPOSAL_COMPARISON_AND_NEXT_ARCHITECTURE.md)  
   Compares the prior patch-by-patch / integration-runtime proposal with the new `Agent Shell + Verified-State Core` convergence proposal before any new implementation.

5. [`05_META_REVIEW_AND_LOCAL_WORK_PROTOCOL.md`](05_META_REVIEW_AND_LOCAL_WORK_PROTOCOL.md)  
   Records the meta checkpoints used during this audit and defines the local workflow that should precede each future implementation slice.

---

## 3. Document authority labels

This audit uses the following labels. They are about **current architectural authority**, not historical quality.

| Label | Meaning |
|---|---|
| `CANONICAL-INVARIANT` | Still an active non-negotiable architecture rule. |
| `CURRENT-CONTRACT` | Describes current executable behavior and should match current tests/code. |
| `HISTORICAL-EVIDENCE` | Important to explain why a decision was made, but not a current product contract. |
| `SUPERSEDED-SHAPE` | Historical implementation/product shape intentionally replaced by a later design. |
| `INCIDENT-EVIDENCE` | Runtime/bug evidence useful for causal reasoning, not a design spec. |
| `PROPOSAL` | Future direction; must not be described as implemented. |
| `VALIDATION-EVIDENCE` | Test/CI/benchmark result bound to a specific source revision. |
| `STALE-CONTRACT-RISK` | Still readable as a current contract but known to disagree with newer implementation/docs. |

Original documents are intentionally **not moved or rewritten** by this audit. Historical paths and commit evidence are part of the evidence chain.

---

## 4. Preliminary thesis

The strongest evidence does **not** support the claim that the Verified-State authority model itself should be discarded.

It supports a narrower but important conclusion:

> The standalone Kernel accumulated an increasingly large Agent/Integration Runtime around itself. Several real failures arose where generic agent-shell responsibilities — provider protocol, OS command generation, interactive approvals, retrieval availability, TUI/runtime composition, and extension hosting — became coupled to progress/recovery semantics or were described by overlapping contracts.

The reset target is therefore **convergence, not rewrite**:

```text
retain Verified-State authority/evidence Kernel
        +
make generic Agent Shell explicit and replaceable
        +
reduce cross-layer semantic repair and platform assumptions
```

No implementation work should be proposed until the historical classification, canonical review, and causal atlas have been read together.
