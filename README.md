# Verified-State Harness

This research branch is the standalone implementation of the new harness architecture. `main` remains the preserved legacy Base Harness and is not the development line for this project.

## Core invariant

> **Actor output may propose and act; only harness-side verification/oracles may promote trusted truth or success. Recovery and progress control are kernel-owned and may not bypass those gates.**

## Architecture

```text
Goal Contract -> Observation/Evidence -> Trusted Working State
-> Actor Decision -> Capability/Isolation Gate -> Tool Runtime
-> Evidence/Hypothesis -> VerificationContract -> Kernel State Commit

Actor Decision -> deterministic Progress Control
  -> verified fact semantic change OR novel integrity-checked successful evidence
  -> no-progress family/global windows
  -> typed NO_PROGRESS -> Stage 05 recovery

Failure -> RecoveryTransition(PENDING) -> durable checkpoint
-> Kernel recovery before Actor -> APPLIED/SUPERSEDED -> checkpoint
-> bounded directive OR terminal fail-closed halt

Completion request -> Completion Oracle -> Kernel accepts/rejects
```

## Stage status

| Stage | Scope | Status |
|---|---|---|
| 00 | Research / contracts | COMPLETE |
| 01 | Truth + execution integrity | COMPLETE |
| 02 | Capability isolation + sealed oracle | PASS / EXITED |
| 03 | Persistence + resume + reproducibility | PASS / EXITED (`v0.4.0`) |
| 04 | Semantic verification | PASS / EXITED (`v0.5.0`) |
| 05 | Failure recovery | PASS / EXITED (`v0.6.0`) |
| 06 | Loop / deterministic progress control | PASS CANDIDATE — `v0.7.0` release verification pending |

Release snapshot package version: **v0.7.0**.

## Stage 06 candidate result

- durable `ProgressPolicy` / `ProgressState`;
- Actor narrative/speculative churn excluded from progress authority;
- verified fact semantic-content progress excluding evidence-ref churn;
- successful observation novelty only after integrity verification;
- historical successful evidence revalidation before Actor continuation;
- specific Stage 05 failure precedence;
- family/global no-progress windows;
- strategy-generation reset without treating strategy switch as progress;
- identical evidence remains known after a switch;
- strategy exhaustion -> Stage 05 terminal `ESCALATE`;
- deterministic resume and progress-policy provenance.

`v0.7.0-rc3` passed 112 tests with 5 hosted-environment namespace skips plus all Stage 03-06 direct probes. The actual `v0.7.0` snapshot must independently pass the same gates before Stage 06 is EXITED.

## Guarantee boundaries

Stage 06 is deterministic/syntactic progress control, not semantic usefulness. Novel evidence or a new verified fact is not automatically proven relevant to the active goal. Continually changing valid outputs can remain novel until hard budget. Historical successful-evidence scanning has a known cumulative performance cost.

## Development rule

Use `research/verified-state-stage03` as the single continuing research branch. Do not create a branch per Stage. `main` remains preserved.

## Next work after release verification

If `v0.7.0` release verification passes, the next Stage is **Stage 07 — Context Governance**. It must freeze a Context Projection Contract before summaries, retrieval, or memory are added.
