# Pre-Stage08 Remediation — COST REPORT

Scope: **P0-1 verified-read single-buffer hardening**

## Cost principle

Critical integrity validation is not removed to save cost. The optimization is to stop reading artifact content twice when one verified buffer can be consumed directly.

## Deterministic I/O model

Let artifact size be `N` bytes.

### Flawed double-read candidate

```text
read N bytes for digest validation
+ read N bytes again for caller consumption
= 2N artifact bytes read
```

SHA-256 operations: 1 over N bytes.

### Hardened single-buffer read

```text
open once
read N bytes
hash the same N-byte buffer
return the same buffer
= N artifact bytes read
```

SHA-256 operations: 1 over N bytes.

Therefore:

```text
content read bytes:     2N -> N   (-50%)
logical content reads:    2 -> 1   (-50%)
hash operations:          1 -> 1   (no reduction in integrity work)
```

## Executable benchmark

`scripts/remediation_artifact_cost_probe.py` executes both algorithms over a 4 MiB artifact for 7 rounds.

It records:

- logical content reads per call;
- artifact bytes read per call;
- SHA-256 operations;
- median wall time.

Wall time is explicitly treated as a noisy runtime proxy. The deterministic byte/read-count delta is the load-bearing cost result.

## Memory

The hardened implementation accumulates the verified artifact into one bytes buffer before returning it. This is necessary for the current API guarantee that the exact hashed bytes are the bytes consumed.

Peak content-buffer memory is approximately `N` plus chunk/list overhead. The flawed double-read path also materialized full-file buffers, so this does not introduce a new asymptotic memory class.

For very large artifacts a future streaming consumer API may avoid materializing the whole file, but that API must bind verification and consumption within the same stream/FD and cannot reintroduce `verify path -> reopen path` semantics.

## CPU

SHA-256 work remains one full pass over artifact content. Additional `open/fstat` syscall overhead is constant per logical read and is negligible relative to large-content hashing; it is retained because it strengthens object identity and final-component file type checks.

## Token / context cost

P0-1 changes only artifact read semantics. It adds no model-visible context and therefore has no direct prompt-token increase.

## Tool calls / checkpoints / ledger growth

No runtime Actor tool call, checkpoint schema, or event schema was added by P0-1. Test/CI execution time increases slightly because the remediation adds targeted tests and one cost probe, but production run ledger growth is unchanged.

## Cost judgment

The integrity improvement and I/O reduction point in the same direction: the correction is both safer and cheaper in artifact content reads. No integrity check is traded away for performance.
