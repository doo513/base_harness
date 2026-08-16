# Stage 02 Remediation — Nested Submount FINAL REREVIEW

Decision candidate: **PASS for the reproduced nested-submount class; release freeze pending**

## Logic

### L1 — Was the issue proven rather than inferred?

**PASS.** The red probe demonstrated both raw Linux descendant writability and an actual Harness backend mutation with returncode 0.

### L2 — Does the fix merely make the top-level mount appear read-only?

**PASS.** The fix does not infer recursive read-only semantics. It refuses sandbox execution whenever a declared read-only directory contains a separate descendant mount.

### L3 — Does the attack remain detectable after the fix?

**PASS.** The raw mount fixture still proves the underlying descendant is writable. Only the Harness execution path changes from escape to preflight rejection.

## Implementation

### I1 — Mount topology source

`/proc/self/mountinfo` is snapshotted once per `_validate_ro_paths()` call.

### I2 — Source mount false positive

The source itself may be a mount point. Only strict descendants cause rejection.

### I3 — Escaped paths

Proc mountinfo octal escapes are decoded before path comparison.

### I4 — Actual attack result after fix

```text
preflight blocked  true
backend attempt    none
host escape        false
```

### I5 — Prior-stage regression

Green validation:

```text
134 passed / 5 skipped
Stage03–07 probes PASS
Stage08 single-buffer probe PASS
```

## Structure

### S1 — Security property ownership

The check is in the Linux namespace backend configuration boundary, before the setup script can create an unsafe recursive bind. Domain Profiles and Actor/controller code do not decide whether the topology is acceptable.

### S2 — Fail-closed compatibility tradeoff

A legitimate read-only source containing benign nested mounts is currently rejected even if a newer kernel could recursively enforce read-only flags. This is intentional: unsupported topology is refused rather than silently weakened.

### S3 — Race boundary

The mount topology snapshot precedes sandbox mount setup. An independently privileged host process capable of changing mount topology concurrently is outside the current Actor threat model. Eliminating that host-admin race would require a stronger FD/namespace construction protocol and is not claimed solved here.

## Cost

Measured added preflight cost on the GitHub runner:

```text
/proc/self/mountinfo input  2,457 bytes
mount points                24
median parse time           ~0.673 ms
max observed                ~1.073 ms
```

No model tokens, checkpoint bytes, event records, or Actor tool calls are added.

## Evidence distinction

The GitHub hosted runner is a fresh ephemeral host environment and therefore improves reproduction diversity compared with the original Stage-02 local evidence. It is still not described as independent third-party production certification.

## Remaining Stage-02 blocker before remediation sequence advances

The next distinct Stage-02 structural issue is **Tool backend attestation/execution binding**:

```text
attest spec.execution_backend
-> execute arbitrary spec.handler
```

A safe backend object can currently be paired with an unsafe side-effecting in-process handler. Nested-submount PASS does not close that issue.

## Verdict

```text
reproduced nested-submount escape before fix: 1
same escape after fix:                       0
unresolved Critical/High in this sub-scope:  0
```

**Recommendation:** release this sub-scope as `v0.8.2` after exact version-snapshot CI, then continue directly to execution-backend binding remediation.
