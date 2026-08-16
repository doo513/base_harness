# Stage 05 — Exit Decision

Decision: **PASS / EXITED**  
Release: `v0.6.0`

## Exit criteria

```text
preflight provenance hardening       PASS
stateful controller resume           PASS
Stage 05 unit/integration tests       PASS
Stage 05 direct recovery probe       PASS
Stage 05 adversarial probe           PASS
Stage 05 terminal probe              PASS
Stage 05 crash-window probe          PASS
Stage 05 strategy-generation probe   PASS
full regression                      PASS
Stage 03 direct resume probe         PASS
Stage 04 semantic probe              PASS
security retry bypass                0
ambiguous side-effect executions     0
verified-fact recovery mutations     0
lost scheduled recoveries            0
hard-budget step overshoot            0
repeat-after-switch immediate switch  0
unresolved Critical/High finding      0
```

Final candidate evidence is GitHub Actions run `31936441736`: 94 passed / 5 environment-dependent skips, with all direct probes passing.

## What this PASS means

The Kernel can now represent, persist, resume, supersede, apply, and terminally halt typed recovery-control transitions. Recovery cannot directly promote truth, declare completion, execute a tool, or replay an ambiguous non-idempotent effect.

## What this PASS does not mean

It does not establish universal automatic repair, semantic understanding of repeated strategies, exactly-once delivery to an LLM Actor, or rollback of arbitrary external systems.

## Next allowed stage

**Stage 06 — Loop / Progress Control.**

Stage 06 should begin by freezing a deterministic Progress Contract. It must answer how the harness determines that a strategy is making meaningful progress or semantically repeating itself without giving the Actor authority to self-report progress. Do not begin with embeddings/LLM similarity; first define observable progress signals, normalized action/failure signatures, generation boundaries, and fail-closed escalation behavior.
