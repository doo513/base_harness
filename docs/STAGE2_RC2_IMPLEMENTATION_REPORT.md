# Stage 02 rc2 — Production Sandbox Implementation Report

## 1. Stage status

**PASS / EXITED** for the declared Linux namespace backend, conditional on live runtime attestation succeeding on the host.

Historical entry status was **PARTIAL / NOT EXITED**. This report does not rewrite that rc1 result; it documents the work that removed the specific blockers.

## 2. Objective

Implement a production-capable execution boundary and prove it with actual filesystem/network attack probes rather than configuration claims or mock attestations.

Primary inherited blockers:
- unrestricted `LocalProcessBackend` could read/write host paths outside workspace;
- host loopback remained reachable;
- sealed-oracle confidentiality was not established;
- verifier subprocess write confinement was not established;
- test-only/mock isolation evidence could not count as production proof.

## 3. Threat model

Untrusted Actor commands know host absolute paths and may attempt traversal, symlink, direct read/write, environment-secret access, host loopback/external sockets, namespace/remount tricks, filesystem IPC, and inode-based hard-link escape. Oracle acceptance assets are operator-owned. Verifier/oracle subprocesses may execute tools but must not mutate candidate/sealed assets when configured read-only.

Out of scope for this stage: kernel escape exploits, cgroup/resource exhaustion, cross-platform sandboxing, and arbitrary untrusted in-process Python verifier plugins. Built-in in-process verifiers remain trusted computing base.

## 4. Implementation

### 4.1 Backend

Added `LinuxNamespaceSandboxBackend` split into small modules:
- `sandbox_primitives.py`: shared execution/attestation primitives and the deliberately non-isolated local backend;
- `linux_namespace_backend.py`: public production backend;
- `linux_namespace_config.py`: environment, runtime-path and workspace preflight;
- `linux_namespace_exec.py`: chroot construction and namespace execution;
- `linux_namespace_setup.py`: mount setup + capability drop;
- `linux_namespace_probe.py`: live isolation attestation;
- `sandbox.py`: public re-export surface.

The backend uses Linux user + mount + PID namespaces and a fresh network namespace for DENY mode. The actor gets only an explicit workspace host bind. Runtime paths are read-only. The sandbox root itself is a bind mount remounted read-only. Execution enters a chroot and drops bounding/inheritable/ambient capabilities with `setpriv`, `no_new_privs`, and locked `noroot` securebits.

### 4.2 Separate actor/verifier/oracle views

Actor workspace is writable for productive work. Verifier/oracle candidate workspace can be mounted read-only. Oracle additionally receives the sealed acceptance root read-only. Actor does not receive that mount. A namespace-local `/vsh-tmp` tmpfs permits scratch files without granting candidate or host writes.

### 4.3 Attestation

Strict policy accepts production isolation only when backend attestation source is `runtime_probe`. A backend declaration is not enough. `test_fixture` is rejected unless an explicit test-only opt-in is set.

The live probe checks:
- actor workspace positive write control;
- outside absolute read failure;
- outside absolute write failure/no host file creation;
- sandbox-root chmod/write escape failure;
- parent secret environment absence;
- host loopback failure in DENY mode.

If required Linux primitives or the runtime probe fail, strict mode fails closed.

### 4.4 Workspace channel preflight

During final re-review, two channels were identified that a bind-mounted workspace could preserve despite chroot/network namespaces:
- AF_UNIX/special filesystem nodes;
- a regular file hard-linked to an inode outside the workspace.

The backend now fails closed on special files/nested mounts and rejects regular-file inodes whose full link count is not contained in the workspace. Workspace symlinks remain allowed because the chroot blocks path resolution outside, and a direct escape probe covers this property.

## 5. Failures found while implementing

### F1 — chmod-only root skeleton was insufficient

An early prototype relied on mode `0555`. Because the namespace-mapped user could own that inode, chmod could re-enable write. Correction: make the root skeleton a mount and remount it read-only. Added D13 rootfs chmod/write probe.

### F2 — read-only verifier needed scratch

A fully read-only verifier environment broke common tools that need temporary files. Correction: keep candidate workspace read-only but add isolated `/vsh-tmp` tmpfs. A test proves scratch succeeds while candidate mutation fails.

### F3 — generic `/tmp` scratch could shadow a workspace

A prototype scratch mount at `/tmp` could hide a workspace located beneath `/tmp`. Correction: dedicated `/vsh-tmp`.

### F4 — network namespace does not isolate filesystem AF_UNIX sockets

A host socket already present under a bind-mounted workspace remains a host IPC channel. Correction: special-file preflight + D15.

### F5 — pathname isolation does not neutralize external hard links

A workspace hard link may reference the same inode as an outside file. Correction: inode/link-count preflight + D16.

### F6 — connector delivery exposed oversized-module fragility

During branch packaging, the large sandbox module was split into behavior-preserving modules. An initial automated split introduced a SyntaxError; it was corrected and the complete 47-test regression plus attack probe was rerun before delivery. This failure was not used as final evidence.

## 6. Direct attack probes

Required Stage 02 attacks:

| ID | Attack | Result |
|---|---|---|
| A01 | `../` traversal | PASS / blocked |
| A02 | absolute outside read | PASS / blocked |
| A03 | absolute outside write | PASS / blocked |
| A04 | harness-private read | PASS / blocked |
| A05 | harness-private write | PASS / blocked |
| A06 | Actor sealed-oracle read | PASS / blocked |
| A07 | symlink escape | PASS / blocked |
| A08 | host loopback connect | PASS / blocked |
| A09 | external network connect | PASS / blocked |
| A10 | parent env secret inheritance | PASS / secret absent |
| A11 | verifier candidate write | PASS / blocked; isolated scratch works |
| A12 | Oracle sealed asset mutation | PASS / blocked; hash unchanged |

Defense in depth:

| ID | Attack | Result |
|---|---|---|
| D13 | rootfs chmod/write escape | PASS / blocked |
| D14 | nested userns remount | PASS / blocked on recorded host |
| D15 | workspace AF_UNIX host channel | PASS / preflight blocked |
| D16 | external hard-link escape | PASS / preflight blocked |

Positive control proves the actor can still write inside its workspace.

## 7. Regression and environment

Final recorded evidence:
```text
pytest:       47 passed in 10.49s
compileall:   PASS
required:     12/12 PASS
defense:      4/4 PASS
attestation:  filesystem=true, network=true, environment=true
source:       runtime_probe
```

Recorded environment: Linux 6.18.35 x86_64, Python 3.13.5, util-linux 2.41 primitives (`unshare`, `mount`, `setpriv`) available.

Evidence files:
- `evidence/stage2_rc2_attack_probe.json`
- `evidence/stage2_rc2_environment.json`
- `evidence/stage2_rc2_pytest.txt`
- `evidence/stage2_rc2_compileall.txt`
- `evidence/stage2_rc2_validation_summary.json`

## 8. Gate review

Truth Integrity remains intact: Actor state is detached and trusted-state commit remains kernel-owned. Execution Integrity passes for the verified Linux namespace backend. Oracle Integrity passes for the sealed command oracle with a separate read-only oracle backend. Persistence/Resume is not claimed complete; it is Stage 03. Reproducibility is sufficient for this Stage 02 security experiment but full run provenance/replay semantics remain Stage 03 work.

## 9. Exit criteria

All Stage 02 blocker criteria have direct Level-A runtime evidence in this environment. The original rc1 reason for PARTIAL is therefore removed.

**Final verdict: Stage 02 PASS / EXITED.**

## 10. Next allowed task

**Stage 03 — Persistence / Resume / Reproducibility.** Do not add RAG, skills, planners, subagent swarms, or unrelated feature breadth before Stage 03 exits.
