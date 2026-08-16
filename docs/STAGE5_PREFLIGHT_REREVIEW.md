# Stage 05 Entry Preflight Re-review

Status: **BLOCKERS FOUND — FIX BEFORE STAGE 05 IMPLEMENTATION**

Baseline reviewed: `v0.5.0`, branch `research/verified-state-stage03`.

## Purpose

Stage 05 recovery depends on deterministic resume. Before adding durable recovery transitions, the existing Truth / Isolation / Persistence / Semantic Verification stack was re-reviewed across logic, implementation, structure, integrity, and reproducibility.

## Findings

| ID | Finding | Severity | Decision |
|---|---|---:|---|
| PF01 | `CapabilityPolicy` grants were not included in the run config fingerprint. A resumed process could use a more permissive policy without a config mismatch. | Critical | Block Stage 05; fingerprint exact grants. |
| PF02 | `ScriptedController` decision contents were not fingerprinted; only controller class/source were recorded. | High | Bind ordered decision script hash. |
| PF03 | Unsealed `CommandCompletionOracle` commands were not fingerprinted. | Critical | Bind command hashes/count/timeout. |
| PF04 | Predicate-oracle callable semantics were not fingerprinted beyond oracle class. | High | Fingerprint callable source/defaults/closure values where stably representable. |
| PF05 | Tool handler source hash ignored closure-captured configuration such as target paths and timeouts. | High | Add callable closure descriptor. |
| PF06 | Tool precondition/postcondition logic was absent from provenance. | High | Fingerprint both callables. |
| PF07 | Execution backend provenance recorded mostly the backend name, not isolation-relevant configuration. | Critical | Bind backend class/MRO plus network/env/writability/read-only-path config. |
| PF08 | Oracle backend provenance recorded mostly the backend name. | High | Use the same backend descriptor for oracle execution. |
| PF09 | Imported mixin implementation changes could be missed by a class-only source hash. | Medium | Include source hashes for non-builtin MRO classes. |
| PF10 | Test backends with deterministic outcomes could change behavior while retaining the same backend name. | Medium | Fingerprint configured deterministic outcomes. |
| PF11 | Arbitrary opaque closure objects cannot be generically serialized into a complete semantic fingerprint without an explicit provider contract. | Residual | Stable primitive/path/enum/container values are bound; opaque objects remain represented by type and require explicit task/model/tool provenance when correctness depends on internal state. |
| PF12 | Failure recovery is advisory-only, has no durable pending transition, and therefore is not ready to rely on resume semantics. | Stage-05 scope | Proceed only after PF01–PF10 are closed and regression-tested. |

## Required preflight gate

Before Stage 05 implementation:

```text
compileall                         PASS
full pytest                       PASS
Stage 03 direct resume probe      PASS
Stage 04 semantic probe           PASS
controller-script drift           FAIL CLOSED
capability-policy drift           FAIL CLOSED
oracle-command drift              FAIL CLOSED
predicate-closure drift           FAIL CLOSED
tool-closure drift                FAIL CLOSED
backend-config drift              FAIL CLOSED
```

## Methodology

The correction is intentionally confined to run provenance and resume compatibility. It does not add recovery behavior. No Stage 01–04 authority, isolation, verification, receipt, or completion rule may be weakened to make the new tests pass.

## Residual boundary

A generic Python object may carry hidden mutable state that cannot be meaningfully serialized by the kernel. The kernel fingerprints stable built-in values and known execution configuration surfaces, while opaque objects are type-identified. Production users must still provide explicit revision/provenance identifiers for external model/tool/service semantics that are not introspectable.
