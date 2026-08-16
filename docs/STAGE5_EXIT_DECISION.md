# Stage 05 — Exit Decision

Decision: **PASS / EXITED**  
Release: `v0.6.0`  
Release commit: `7f2a167434abc9d1a000f285118c2757e149b8a0`

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

## Release verification

The actual `v0.6.0` release snapshot was independently executed in GitHub Actions run `31936623337` after version promotion and documentation updates:

```text
compileall                          PASS
pytest                              94 passed / 5 skipped
Stage 03 resume probe               4 / 4 PASS
duplicate external actions         0
Stage 04 semantic matrix            8 / 8 PASS
Stage 04 FP / FN                    0 / 0
Stage 05 base recovery              PASS
Stage 05 adversarial                PASS
Stage 05 terminal                   PASS
Stage 05 crash-window               PASS
Stage 05 strategy generation        PASS
unsafe automatic retries            0
verified fact mutations             0
ambiguous external executions       0
lost scheduled recoveries           0
hard-budget step overshoot           0
consecutive switch-after-new-fail   0
```

The five skipped tests are hosted-environment live Linux namespace tests and are not counted as Stage 02 production isolation evidence.

## What this PASS means

The Kernel can represent, persist, resume, supersede, apply, and terminally halt typed recovery-control transitions. Recovery cannot directly promote truth, declare completion, execute a tool, or replay an ambiguous non-idempotent effect.

## What this PASS does not mean

It does not establish universal automatic repair, semantic understanding of repeated strategies, exactly-once delivery to an LLM Actor, or rollback of arbitrary external systems.

## Next allowed stage

**Stage 06 — Loop / Progress Control.**

Stage 06 begins by freezing a deterministic Progress Contract. It must define how the harness determines meaningful progress versus repeated/no-progress behavior without trusting Actor self-reporting. Initial work must use inspectable deterministic signals before any embedding/LLM similarity mechanism is considered.
