# 02 — Current Status

## Stage status

```text
Stage 00  COMPLETE
Stage 01  COMPLETE for scoped P0 defects
Stage 02  PASS / EXITED
Stage 03  PASS / EXITED   v0.4.0
Stage 04  PASS / EXITED   v0.5.0
Stage 05  PASS / EXITED   v0.6.0
Stage 06  PASS CANDIDATE  v0.7.0 release verification pending
```

## Existing guarantee boundaries

- Stage 02 production isolation requires a successful live `runtime_probe`; hosted namespace skips are not proof.
- Stage 03 non-idempotent execution is at-most-once automatic execution, not universal exactly-once semantics.
- Stage 04 generic structured verification does not solve arbitrary natural-language truth.
- Stage 05 proves durable recovery-control state, not guaranteed LLM semantic repair or arbitrary external rollback.

## Stage 06 candidate

Final candidate before release promotion: `v0.7.0-rc3`, commit `3188ea75f7ca3d503cd8557cd7dd8bd562eaa2d4`, GitHub Actions `31937830666`.

```text
pytest                              112 passed / 5 skipped
Stage 03 resume                     4 / 4 PASS; duplicate=0
Stage 04 semantic                   8 / 8 PASS; FP=0/FN=0
Stage 05 all direct probes          PASS
Stage 06 base                       3 / 3 PASS
Stage 06 adversarial                3 / 3 PASS
Stage 06 resume                     3 / 3 PASS
Stage 06 boundary                   4 / 4 PASS
Stage 06 strategy                   6 / 6 PASS
zero-tolerance Stage 06 counters    all 0
```

Implemented candidate semantics:

- progress policy and state are durable/provenance-bound;
- Actor narrative/speculation cannot self-declare progress;
- verified fact semantic-content changes can be progress while evidence-ref metadata churn cannot;
- successful evidence must be integrity checked and content-novel;
- historical successful evidence is revalidated before Actor continuation;
- specific Stage 05 failures outrank generic no-progress;
- recovery is not an Actor progress sample;
- same-family and global no-progress windows are deterministic;
- strategy switch resets local windows but is not progress;
- identical evidence remains known across strategies;
- strategy exhaustion routes to terminal Stage 05 `ESCALATE`.

Known boundaries: semantic relevance is not solved and historical evidence revalidation has cumulative performance cost.

## Current gate

The package/version is being promoted to the `v0.7.0` release snapshot. **Do not begin Stage 07 until the release snapshot independently passes the same CI/probe matrix and `STAGE6_EXIT_DECISION.md` records PASS / EXITED.**

After that gate, the next planned Stage is **Stage 07 — Context Governance** with a Context Projection Contract first.
