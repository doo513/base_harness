# Verified-State Harness v0.4.0 — Stage 03

> Current status: **Stage 03 PASS / EXITED.**
>
> Stage 02 production isolation remains PASS on `LinuxNamespaceSandboxBackend` when its live `runtime_probe` succeeds.

Core invariant:

> **Actor output may propose and act; only harness-side verification/oracles may promote truth or success. Persisted state must also prove that it belongs to the same run/configuration before it can be trusted after restart.**

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
        ↓
Hashed Event Snapshot
        ↓
Atomic Checkpoint

Completion request
        ↓
Sealed Completion Oracle
        ↓
Kernel accepts / rejects

+ Domain Profile
  tools() · state_schema() · failure_taxonomy()
  memory_policy() · verification_contract() · completion_oracle()
```

## Stage 03 persistence model

Every run now has:

```text
run_manifest.json      run/config/provenance identity
checkpoint.json        atomic state + event anchor
events.jsonl           sequence + hash-chained event ledger
receipts/*.json        durable non-idempotent action receipts
tool_calls.jsonl       tool-call audit log
artifacts/              opaque evidence artifacts
```

### Resume contract

`HarnessRuntime.resume(...)` and CLI `--resume` require:

1. valid manifest envelope,
2. valid event hash chain,
3. valid checkpoint envelope/state hash,
4. checkpoint → event anchor match,
5. same run id and manifest hash,
6. current configuration fingerprint match,
7. reconstructable canonical state.

If a valid `state.snapshot` event is newer than the checkpoint because the process died between event fsync and checkpoint replacement, resume recovers that newer event state and rewrites the checkpoint.

## Non-idempotent side effects

For `ToolSpec.idempotent=False`:

```text
PREPARED receipt
    ↓
execute tool
    ↓
COMMITTED receipt
    ↓
state transition persistence
```

Resume rules:

- `COMMITTED` → return the persisted ToolResult; do **not** execute again.
- `PREPARED` only → halt/fail closed because the external effect is ambiguous.

This is an **at-most-once automatic execution** guarantee. The harness does not claim arbitrary exactly-once transactions for external systems.

## Reproducibility manifest

The run manifest records and fingerprints:

- task/model revision,
- goal/acceptance/constraints,
- profile and verifier identities/source hashes,
- controller/model-adapter identity and command hash,
- tool policy/provenance/handler source hash,
- security and budget configuration,
- oracle identity/seal/backend,
- harness/Python/platform revision.

Missing provenance is recorded as a warning. `--require-complete-provenance` converts the warning into a fail-closed construction error.

## Current direct evidence

```text
Stage 03 targeted tests:       12 passed
full pytest suite:             59 passed
Stage 03 direct probe:          4 / 4 PASS
duplicate external actions:     0
compileall:                     PASS
Stage 02 required attacks:     12 / 12 PASS
Stage 02 defense probes:        4 / 4 PASS
```

See:

- `docs/STAGE3_PREFLIGHT_REREVIEW.md`
- `docs/STAGE3_IMPLEMENTATION_REPORT.md`
- `docs/STAGE3_EVIDENCE_MATRIX.md`
- `docs/STAGE3_FINAL_REREVIEW.md`
- `docs/STAGE3_EXIT_DECISION.md`
- `evidence/stage3_resume_probe.json`

## CLI examples

New run:

```bash
PYTHONPATH=src python -m harness.cli \
  --profile demo \
  --workspace /path/to/workspace \
  --run-dir /private/path/run \
  --task-revision task-v1
```

Resume the same run:

```bash
PYTHONPATH=src python -m harness.cli \
  --profile demo \
  --workspace /path/to/workspace \
  --run-dir /private/path/run \
  --task-revision task-v1 \
  --resume
```

Production software example keeps the Stage 02 isolation boundary:

```bash
PYTHONPATH=src python -m harness.cli \
  --profile software \
  --workspace /path/to/actor-workspace \
  --run-dir /operator/private/run \
  --execution-backend linux-namespace \
  --network-policy deny \
  --strict-tool-isolation \
  --strict-layout \
  --accept-command 'pytest -q {workspace}' \
  --sealed-oracle-root /operator/private/acceptance \
  --require-sealed-oracle \
  --require-oracle-isolation \
  --task-revision git:abc123 \
  --model-revision provider:model-revision \
  --require-complete-provenance
```

## Scope / non-claims

Stage 03 does **not** claim:

- multi-writer run-directory safety,
- distributed transactions or arbitrary exactly-once side effects,
- authenticated persistence if an attacker can write the private run directory,
- automatic migration from v0.3 unhashed event logs,
- deterministic behavior from a stochastic external model,
- cross-platform Stage 02 sandbox parity.

The Stage 03 integrity model depends on the Stage 02 rule that `run_dir` is outside Actor write access in production.

## Next allowed stage

Stage 04 — **Semantic Verification** (`v0.5.0`).
