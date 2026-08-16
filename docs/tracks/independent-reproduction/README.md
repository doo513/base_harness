# Track B — Independent Reproduction

Status: **REQUIRED BEFORE OFFICIAL BENCHMARK / RELEASE CLAIMS**

This is external validation, not a new Stage and not a feature expansion.

## B1. Stage02 clean-host reproduction

Current status: **GAP**.

The existing project CI has reproduced the raw nested-mount hazard and the harness fail-closed defense on its hosted environment. That is useful internal evidence, but it does not equal an independent fresh-host reproduction.

Required protocol:

1. provision a fresh privileged Linux VM or self-hosted Linux host;
2. record host identity before repository checkout;
3. fresh clone the exact freeze commit;
4. install dependencies from the locked CI dependency set;
5. do not reuse cached attestation/evidence directories;
6. run namespace/isolation tests and direct attack probes;
7. run nested-mount attack reproduction and backend-attestation mismatch probe;
8. save machine-readable outputs together with host provenance;
9. compare evidence hashes/results with the internal baseline.

Minimum provenance record:

- OS distribution/version
- kernel release
- architecture
- mount/unshare binary versions
- Python version/executable
- git commit/tree
- dependency lock hash
- relevant sandbox/runtime configuration

### Exit criterion

`SUPPORTED` becomes stronger independent evidence only after the same security claims reproduce on at least one separately provisioned host. A skip due missing privilege is not PASS evidence.

## B2. Official benchmark/release execution profile

Current Stage03 provenance captures source semantic identity, lockfile identity, Python/platform/toolchain and CI/container information when available. Do not make every local development environment immutable.

Create a distinct **official benchmark/release profile** with mandatory identity:

- exact git commit/tree
- clean/dirty status policy
- dependency lock hash
- build backend identity
- OS/base image identity
- container image digest or VM image/recipe hash
- kernel/toolchain identity relevant to sandbox behavior
- harness runtime/config fingerprint

Local Development may continue with incomplete-provenance warnings when the missing identity does not invalidate a security claim. Official benchmark/release runs should fail closed when the required identity cannot be established.

## Priority

- B1 clean-host Stage02: **REQUIRED BEFORE BENCHMARK**
- B2 benchmark/release immutable profile: **REQUIRED BEFORE BENCHMARK**
- immutable identity for every ad-hoc local deployment: **NOT NEEDED**

## Cost

This Track mainly adds environment provisioning and evidence storage. It should add essentially no model-token cost. Provenance should remain run-start scoped rather than being recomputed every turn.
