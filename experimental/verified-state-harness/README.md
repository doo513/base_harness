# Verified-State Harness v0.3.0 — Stage 02

> Current status: **Stage 02 PASS / EXITED on the verified Linux namespace backend.**
>
> Inherited status at the start of this work was **PARTIAL / NOT EXITED**. The blocker was a missing production sandbox plus missing real filesystem/network attack evidence. This version closes that blocker with a live-probed Linux namespace backend and direct attack probes. The PASS is conditional on the backend's runtime attestation succeeding on the host; unsupported hosts fail closed.

The core invariant remains:

> **Actor output may propose and act; only harness-side verification/oracles may promote truth or success.**

## Kernel + Domain Profile

```text
Goal / Requirement Contract
        ↓
Observation Gate
        ↓
Trusted Working State
        ↓
Actor Decision
        ↓
Capability / Permission / Isolation Gate
        ↓
Tool Runtime
        ↓
Evidence / Hypothesis
        ↓
Verifier Chain
        ↓
Kernel-owned State Commit

Completion request
        ↓
Sealed Completion Oracle
        ↓
Kernel accepts / rejects

+ Domain Profile
  tools() · state_schema() · failure_taxonomy()
  memory_policy() · verification_contract() · completion_oracle()
```

## Stage 02 production boundary

`LinuxNamespaceSandboxBackend` provides a real Linux process boundary using:

- user namespace with root mapped only inside the namespace,
- mount namespace,
- PID namespace,
- fresh network namespace when `network_policy=deny`,
- chroot with no host root filesystem bind,
- read-only runtime mounts,
- writable actor workspace only as an explicit host-backed mount,
- read-only verifier/oracle candidate workspace,
- read-only sealed-oracle mounts,
- namespace-local ephemeral scratch (`/vsh-tmp`),
- all capabilities dropped before actor command execution,
- `no_new_privs` + locked `noroot` securebit,
- sanitized environment,
- workspace preflight rejection of special-file host channels and external hard links,
- live runtime attestation; configuration alone never counts as production evidence.

`LocalProcessBackend` remains available for non-strict local use, but deliberately attests filesystem/network isolation as false.

## Real attack evidence

The Stage 02 rc2 attack probe verifies the required 12 attacks plus four defense-in-depth probes:

1. `../` path traversal
2. absolute read outside workspace
3. absolute write outside workspace
4. harness-private read
5. harness-private write
6. sealed-oracle read by Actor
7. symlink escape
8. loopback connection
9. external network connection
10. parent secret environment inheritance
11. verifier candidate mutation
12. oracle asset mutation
13. rootfs chmod/write escape
14. nested user-namespace remount escape
15. workspace AF_UNIX host-channel escape
16. external hard-link escape

Current evidence:

```text
required probes:       12 / 12 PASS
defense-in-depth:       4 / 4 PASS
workspace control:           PASS
runtime attestation:         PASS
full pytest suite:      47 passed
compileall:                  PASS
```

See `evidence/stage2_rc2_attack_probe.json` and `docs/STAGE2_RC2_IMPLEMENTATION_REPORT.md`.

## Strict execution example

```bash
PYTHONPATH=src python -m harness.cli \
  --profile software \
  --workspace /path/to/actor-workspace \
  --run-dir /separate/path/run \
  --execution-backend linux-namespace \
  --network-policy deny \
  --strict-tool-isolation \
  --strict-layout \
  --accept-command 'pytest -q {workspace}' \
  --sealed-oracle-root /operator/private/acceptance \
  --require-sealed-oracle \
  --require-oracle-isolation
```

The Actor backend does **not** mount the sealed root. The Oracle backend is a separate namespace backend that sees the candidate workspace read-only and the sealed root read-only.

## Scope and non-claims

Stage 02 PASS means the declared Stage 02 isolation requirements were demonstrated on the recorded Linux environment. It does **not** mean:

- cross-platform sandbox support exists,
- resource exhaustion / cgroup isolation is solved,
- arbitrary in-process Python verifier plugins are untrusted/sandboxed,
- all semantic verification problems are solved,
- universal or benchmark superiority is proven.

Built-in in-process verifiers remain part of the trusted computing base. Untrusted verifier subprocesses must be launched through the read-only namespace backend.

## Next allowed stage

Stage 03 may now begin: **Persistence / Resume / Reproducibility**. Do not add RAG, skills, planners, subagents, or other feature breadth unless a later stage explicitly requires them.
