# Verified-State Harness

`develop` is the active development line for the Verified-State Harness. `preprocessing` preserves the current pre-integration snapshot; `main` is the promotion target after validated work.

## Core invariant

> **Actor output may propose and act; only harness-side verification/oracles may promote trusted truth or success. Recovery, progress control, context projection, and retrieval admission are kernel-governed and may not bypass those gates.**

## Architecture

```text
Goal Contract -> Observation/Evidence -> Trusted Working State
-> Context Governor -> Actor Decision
-> Capability/Isolation Gate -> Tool Runtime
-> Evidence/Hypothesis -> VerificationContract -> Kernel State Commit

Actor Decision -> deterministic Progress Control
  -> activity novelty: credit 0
  -> verified fact transition: epistemic progress
  -> no-progress family/global windows -> typed recovery

Actor retrieval request
  -> Kernel-owned scope/top-k/provider/ranking/admission/request identity
  -> deterministic read-only Gateway
  -> content-addressed verified admission
  -> durable RetrievalState
  -> Context Governor as untrusted_retrieval / instruction_authority=none
  -> retrieval itself gives progress credit 0

Failure -> durable RecoveryTransition -> Kernel recovery before Actor
-> APPLIED/SUPERSEDED -> bounded directive OR terminal halt

Completion request -> Completion Oracle -> Kernel accepts/rejects
```

## Stage status

| Stage | Scope | Status |
|---|---|---|
| 00 | Research / contracts | HISTORICAL COMPLETE |
| 01 | Truth + execution integrity | HISTORICAL COMPLETE |
| 02 | Capability isolation + sealed oracle | PASS / EXITED + remediation hardening |
| 03 | Persistence + resume + reproducibility | PASS / EXITED (`v0.4.0`) + provenance hardening |
| 04 | Semantic verification | PASS / EXITED (`v0.5.0`) + claim-class hardening |
| 05 | Failure recovery | PASS / EXITED (`v0.6.0`) + controlled effectiveness evidence |
| 06 | Loop / deterministic progress control | PASS / EXITED (`v0.7.0`) + semantic-progress hardening |
| 07 | Context Governance | PASS / EXITED (`v0.8.0`) + trusted-context bounds |
| 08 | Retrieval / Memory Gateway | PASS / EXITED (`v0.9.0`) |

Current package version: **v0.9.1**.

## Guarantee boundaries

- Stage 02 production isolation requires a successful live runtime probe; hosted skips are not production proof.
- Stage 03 provides durable resume and at-most-once automatic handling for non-idempotent execution, not universal exactly-once semantics.
- Stage 04 claim-class contracts do not solve arbitrary natural-language truth.
- Stage 05 proves durable recovery control, not guaranteed semantic repair.
- Stage 06 proves deterministic progress control, not general semantic usefulness or goal relevance.
- Stage 07 proves governed context projection, not semantic relevance ranking.
- Stage 08 treats retrieval as evidence only; it does not provide autonomous trusted memory, semantic remote retrieval, or automatic cross-run learning.

## Post-Stage08 development

Core Stage 00-08 remains frozen except for confirmed defects. New product/integration work is tracked under `docs/tracks/` rather than creating Stage 09+.

Current integration order:

```text
workspace
-> config/secrets
-> model gateway
-> agent control
-> tool contracts
-> MCP/plugin
-> context relevance
-> cross-run memory
-> software/hackathon domain completion
-> progress/recovery alignment
-> real E2E/benchmark
-> TUI
```

Every phase must preserve Kernel authority and leave rationale, implementation, validation, structural-review, and limitation evidence in Markdown before the next phase begins.

## Development rule

Work on `develop`. Keep `preprocessing` frozen. Promote to `main` only after validation. Do not weaken existing Stage gates to make integration easier.
