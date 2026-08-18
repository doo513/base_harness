# Verified-State Harness — Current Agent Handoff

## Current status

```text
Stage 00  COMPLETE
Stage 01  COMPLETE
Stage 02  PASS / EXITED
Stage 03  PASS / EXITED   v0.4.0
Stage 04  PASS / EXITED   v0.5.0
Stage 05  PASS / EXITED   v0.6.0
Stage 06  PASS / EXITED   v0.7.0
Stage 07  PASS / EXITED   v0.8.0
Stage 08  PASS / EXITED   v0.9.0
package   0.9.1 hardening line
```

## Current branch policy

- `preprocessing`: frozen pre-integration snapshot
- `develop`: active implementation branch
- `main`: promotion target after validation

Do not create Stage 09+. Post-Stage08 product/integration work is managed under `docs/tracks/`.

## Core guarantee boundary

Actor/model/tool/retrieval output may propose or produce evidence, but only Kernel-owned verification/oracles can promote trusted truth or accepted completion. Recovery, progress, context projection, retrieval admission, persistence/resume, capability checks, and execution isolation remain Kernel-owned.

## Mandatory workflow

```text
inspect current implementation/evidence
-> reproduce or confirm baseline validation
-> freeze phase contract
-> implement one integration axis
-> targeted/adversarial checks
-> full regression + prior-Stage probes
-> logic/security/integrity re-review
-> record rationale/implementation/validation MD
-> PASS/PARTIAL/FAIL
-> continue only on PASS
```

## Current integration track

Read `docs/tracks/integration-runtime/README.md` and proceed in this order:

1. workspace contract
2. config/secrets
3. model gateway
4. agent control state
5. structured tool contracts
6. MCP/plugin gateway
7. context relevance
8. cross-run memory
9. Software/Hackathon domain completion
10. progress/recovery alignment
11. real E2E and benchmark/ablation
12. TUI

Historical Stage documents remain evidence for their original scopes; where old branch/status text conflicts with this handoff and current source, this handoff plus current source/CI is authoritative.
