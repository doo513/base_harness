# Stage 02 Remediation — Tool Backend Binding FINAL REREVIEW

Decision candidate: **PASS for attestation/execution binding scope; release snapshot pending**

## Logic review

### L1 — Can a generic strict WRITE/EXTERNAL handler borrow a safe backend's attestation?

**PASS / blocked.** `ActionRuntime` rejects generic `ToolSpec` side-effect execution before attestation or handler invocation.

### L2 — Is the object attested the object executed?

**PASS.** `SandboxedCommandToolSpec` stores one `execution_backend`; `ActionRuntime` obtains attestation from that object and later calls `run_shell()` on the same object reference. An identity-counting test verifies identical object identity.

### L3 — Can the Actor promote the legacy type into a sandboxed type by payload text?

**PASS.** Execution type is trusted runtime configuration, not Actor payload. Actor controls command args only after a sandboxed spec is registered.

## Implementation review

### I1 — Built-in shell path

**PASS.** `make_shell_tool()` now returns `SandboxedCommandToolSpec`. It no longer relies on a host handler closure to call the backend.

### I2 — Existing non-strict trusted tools

**PASS.** Generic `ToolSpec` continues to work outside the strict WRITE/EXTERNAL sandbox claim. This preserves Stage-03 deterministic/receipt fixtures and trusted in-process extensions.

### I3 — Nonzero/timed-out tool result

**PASS.** Declarative sandbox execution retains the existing success contract: nonzero or timed-out output returns a failed ToolResult with output preserved.

### I4 — Resume provenance

**PASS in this scope.** Declarative command semantics lost from the removed handler closure are inserted into existing tool provenance fields and therefore participate in the run config hash.

A broader build/release provenance gap remains the next P1 remediation.

### I5 — Cost probe implementation error

**FOUND / FIXED.** The first cost-gate run used JSON-style lowercase `true` in Python and failed after all functional/security gates had passed. The probe was corrected to `True` and rerun; production binding code was unchanged by this correction.

## Structural review

### S1 — Runtime owns strict side-effect execution

**PASS.** Strict sandboxed command execution is no longer delegated to a generic arbitrary handler.

### S2 — Attestation is metadata only for legacy ToolSpec

**PASS.** A legacy ToolSpec may still carry `execution_backend` for compatibility/provenance, but strict WRITE/EXTERNAL policy does not treat it as authorization.

### S3 — Trusted registration boundary remains

A trusted registry can still intentionally mislabel a host-side effect as `SideEffect.NONE` or `READ`. This remediation does not claim to sandbox malicious harness configuration. The guarantee is:

> correctly declared strict WRITE/EXTERNAL tools cannot separate the attested backend from the actual execution object.

This limitation is explicit and does not invalidate the reproduced mismatch fix.

## Regression status

Green functional/security run `31948805281`:

```text
140 passed / 5 skipped
Stage03 resume                PASS 4/4
Stage04 semantic              PASS 8/8, FP=0/FN=0
Stage05                       PASS
Stage06                       PASS
Stage07                       PASS
Stage08 single-buffer         PASS
Stage02 nested-submount       PASS
backend-binding attack        BLOCKED
```

The subsequent cost-gate run failed only because of the cost-probe boolean typo, after all of the above gates had already passed. A corrected cost run is required before version promotion.

## Remaining remediation work

After this sub-scope is released, the planned sequence remains:

1. release/build provenance;
2. claim-class verification;
3. semantic progress;
4. trusted context growth control;
5. retrieval request/admission model;
6. Stage-08 feature integration only after these stop conditions are cleared.

## Candidate verdict

```text
red mismatch canary mutation     1
post-fix mismatch canary mutation 0
post-fix unsafe handler calls     0
valid backend attestation calls   1
valid backend execution calls     1
unresolved Critical/High in scope 0
```

**Recommendation:** once the corrected cost gate and full regression are green, promote to `v0.8.3rc1`, then validate the exact `v0.8.3` release snapshot.
