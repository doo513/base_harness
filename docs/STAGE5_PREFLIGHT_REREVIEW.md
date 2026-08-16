# Stage 05 Entry Preflight Re-review

Status: **PASS / CLOSED — v0.5.2**

Baseline reviewed: `v0.5.0`, branch `research/verified-state-stage03`.

## Purpose

Stage 05 recovery depends on deterministic resume. Before adding durable recovery transitions, the existing Truth / Isolation / Persistence / Semantic Verification stack was re-reviewed across logic, implementation, structure, integrity, and reproducibility.

## Findings and resolution

| ID | Finding | Severity | Resolution |
|---|---|---:|---|
| PF01 | `CapabilityPolicy` grants were absent from the run config fingerprint. | Critical | Exact principal→capability grants are fingerprinted. |
| PF02 | `ScriptedController` decision contents were absent from provenance. | High | Ordered script hash/count are bound. |
| PF03 | Unsealed completion-oracle commands were not fingerprinted. | Critical | Command hashes/count/timeout are bound. |
| PF04 | Predicate-oracle callable semantics were not fingerprinted beyond class identity. | High | Callable source/defaults/stable closure values are bound. |
| PF05 | Tool handler source hash ignored closure-captured configuration. | High | Stable closure values are included. |
| PF06 | Tool precondition/postcondition logic was absent from provenance. | High | Both callable descriptors are included. |
| PF07 | Execution backend provenance was mostly name-only. | Critical | Backend class/MRO and isolation-relevant configuration are bound. |
| PF08 | Oracle backend provenance was mostly name-only. | High | Oracle backend uses the same full descriptor. |
| PF09 | Mixin implementation changes could be missed by class-only hashing. | Medium | Non-builtin MRO source hashes are included. |
| PF10 | Deterministic test backend outcomes could drift under the same backend name. | Medium | Configured outcomes are fingerprinted. |
| PF11 | Opaque arbitrary Python objects cannot be generically reduced to complete semantic provenance. | Residual | Stable values are bound; opaque semantics require explicit revision/provenance. |
| PF12 | Failure recovery is advisory-only and has no durable transition state. | Stage-05 scope | Stage 05 contract is frozen and may now be implemented. |
| PF13 | Stateful controller runtime position was not checkpointed. After resume, `ScriptedController.index` could restart at zero even when harness state had advanced. Recovery steps make inference from `state.step` invalid because they consume harness steps without consuming Actor decisions. | Critical | Added explicit controller `snapshot_state()/restore_state()` protocol, persisted controller state in runtime metadata, restored it from the verified checkpoint before Actor execution, and added a cursor-resume regression test. |

## Validation history

### v0.5.1 provenance hardening

Candidate commit: `22066a8c95e262c924a3a4697f17f59084f8238f`  
GitHub Actions run: `31935087009`

```text
compileall                         PASS
full pytest                       75 passed / 5 skipped
Stage 03 direct resume probe      4 / 4 PASS
duplicate external actions        0
Stage 04 semantic probe           PASS
semantic false positives          0
semantic false negatives          0
configuration drift guards        FAIL CLOSED
```

### v0.5.2 controller-state hardening

Candidate commit: `a4bd38f15646db35fc80da091cb0cf8a06d7d0c0`  
GitHub Actions run: `31935462946`

```text
compileall                         PASS
full pytest                       76 passed / 5 skipped
controller cursor resume          PASS
Stage 03 direct resume probe      4 / 4 PASS
duplicate external actions        0
Stage 04 semantic probe           PASS
semantic false positives          0
semantic false negatives          0
```

The skipped tests remain environment-dependent production namespace tests and are not treated as substitute Stage 02 evidence.

## Methodology

The preflight corrections were intentionally separated from Stage 05 recovery semantics. They modify only provenance/resume correctness and the explicit checkpoint protocol for stateful controllers. No Truth, Capability, Isolation, Verification, Receipt, or Completion gate was weakened.

## Controller-state boundary

The kernel does not guess arbitrary controller internals. A stateful controller must expose both `snapshot_state()` and `restore_state(raw)`. The snapshot must be a JSON object. Stateless controllers need no runtime state. This keeps dynamic resume state separate from immutable controller configuration provenance.

## Residual boundary

Opaque external model/tool/service semantics still require explicit revision identifiers when their behavior cannot be introspected. The preflight does not claim generic serialization of arbitrary Python object semantics.

## Decision

All Critical/High preflight findings discovered before Stage 05 implementation are closed by code plus regression evidence. Remaining limitations are explicit interface boundaries rather than known silent resume-divergence paths.

**Stage 05 entry gate: OPEN.**
