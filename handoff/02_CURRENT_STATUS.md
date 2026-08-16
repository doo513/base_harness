# 02 — Current Status

## Stage 00 — Research Contract
COMPLETE.

## Stage 01 — Truth / Execution Hardening
COMPLETE for scoped P0 defects.

## Stage 02 — Capability Isolation + Sealed Oracle

Historical entry state at rc2 start:

```text
PARTIAL / NOT EXITED
```

Blockers were real local filesystem escape, loopback reachability, no productive OS sandbox, hidden-oracle confidentiality not demonstrated, and untrusted verifier process confinement not demonstrated.

rc2 added: `LinuxNamespaceSandboxBackend`; user/mount/PID/network namespaces; chroot read-only root/runtime mounts; capability drop/no-new-privs; sanitized environment; live production attestation; separate Actor/Oracle backends; read-only verifier/oracle candidate workspace; read-only sealed root; `/vsh-tmp`; AF_UNIX/special-file and external-hard-link preflight; 12 required + 4 defense-in-depth probes; profile integration.

Final evidence:

```text
pytest                47 passed
required attacks      12 / 12 PASS
defense-in-depth       4 / 4 PASS
runtime attestation   PASS / source=runtime_probe
compileall             PASS
```

Current verdict: **Stage 02 = PASS / EXITED** for Linux namespace backend when live probe succeeds. Unsupported hosts fail closed.

Next unresolved architectural work: Stage 03. Existing checkpoint-save code is not proof of resume semantics.
