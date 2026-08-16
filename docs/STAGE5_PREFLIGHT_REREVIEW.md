# Stage 05 Entry Preflight Re-review

Status: **PASS / CLOSED — v0.5.1**

Baseline reviewed: `v0.5.0`, branch `research/verified-state-stage03`.

## Purpose

Stage 05 recovery depends on deterministic resume. Before adding durable recovery transitions, the existing Truth / Isolation / Persistence / Semantic Verification stack was re-reviewed across logic, implementation, structure, integrity, and reproducibility.

## Findings and resolution

| ID | Finding | Severity | Resolution |
|---|---|---:|---|
| PF01 | `CapabilityPolicy` grants were not included in the run config fingerprint. A resumed process could use a more permissive policy without a config mismatch. | Critical | Exact principal→capability grants are now fingerprinted. |
| PF02 | `ScriptedController` decision contents were not fingerprinted; only controller class/source were recorded. | High | Ordered decision script hash/count are bound into controller provenance. |
| PF03 | Unsealed `CommandCompletionOracle` commands were not fingerprinted. | Critical | Command hashes/count/timeout are now bound. |
| PF04 | Predicate-oracle callable semantics were not fingerprinted beyond oracle class. | High | Callable source/defaults/closure values are fingerprinted where stably representable. |
| PF05 | Tool handler source hash ignored closure-captured configuration such as target paths and timeouts. | High | Handler callable descriptor now includes stable closure values. |
| PF06 | Tool precondition/postcondition logic was absent from provenance. | High | Both callables are included in tool provenance. |
| PF07 | Execution backend provenance recorded mostly the backend name, not isolation-relevant configuration. | Critical | Backend class/MRO and network/env/writability/read-only-path configuration are bound. |
| PF08 | Oracle backend provenance recorded mostly the backend name. | High | Oracle backend uses the same full backend descriptor. |
| PF09 | Imported mixin implementation changes could be missed by a class-only source hash. | Medium | Non-builtin MRO class source hashes are included. |
| PF10 | Test backends with deterministic outcomes could change behavior while retaining the same backend name. | Medium | Configured deterministic outcomes are fingerprinted. |
| PF11 | Arbitrary opaque closure objects cannot be generically serialized into a complete semantic fingerprint without an explicit provider contract. | Residual | Stable primitive/path/enum/container values are bound; opaque objects remain type-identified and require explicit revision metadata when internal state matters. |
| PF12 | Failure recovery is advisory-only and has no durable transition state. | Stage-05 scope | Stage 05 contract frozen; implementation may now begin. |

## Validation

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
controller-script drift           FAIL CLOSED
capability-policy drift           FAIL CLOSED
oracle-command drift              FAIL CLOSED
predicate-closure drift           FAIL CLOSED
tool-closure drift                FAIL CLOSED
backend-config drift              FAIL CLOSED
```

The skipped tests remain environment-dependent production namespace tests; no skip is treated as substitute Stage 02 evidence.

## Methodology

The correction was intentionally confined to run provenance and resume compatibility. It did not add recovery behavior and did not weaken Stage 01–04 authority, isolation, verification, receipt, or completion rules.

## Residual boundary

A generic Python object may carry hidden mutable state that cannot be meaningfully serialized by the kernel. The kernel fingerprints stable built-in values and known execution configuration surfaces, while opaque objects are type-identified. Production users must still provide explicit revision/provenance identifiers for external model/tool/service semantics that are not introspectable.

## Decision

All Critical/High preflight findings PF01–PF10 are closed by implementation plus regression evidence. PF11 is an explicitly documented generic-introspection boundary rather than an undetected resume path.

**Stage 05 entry gate: OPEN.**
