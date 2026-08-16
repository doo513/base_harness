# Stage 08 Cost Report

Release commit: `a5645fc9d059afd12088ee1c4751c0250c8a5206`  
Release CI: `31954492789`

## Measurement rule

Stage08 cost probes intentionally report deterministic byte/read/count bounds and serialized-character proxies. They do **not** claim exact model token counts. Wall-clock timing is environment-dependent and is not a correctness gate.

## Retrieval projection cost

Release probe: `retrieval-cost-rc1`

### Source / durable state

- candidate count: `5`;
- raw source bytes: `500035`;
- admitted items: `5`;
- artifact bytes: `500035`;
- configured maximum bytes per current request: `1048576`.

### Model-visible projection

- full serialized context characters: `12149`;
- retrieval JSON characters: `8052`;
- visible preview characters: `3000`;
- visible metadata characters: `2000`.

The full 500035 bytes are not copied into the prompt. Model visibility is governed by explicit preview and metadata bounds.

### Integrity verification per projection

- logical retrieval-artifact reads: `5`;
- verified artifact bytes: `500035`;
- rounds measured: `20`;
- median wall time on release runner: approximately `0.001758734s`.

The deterministic cost is one verified read of each currently selected retrieval artifact. This is deliberate: model-visible projection is not allowed to trust a stale persisted preview if the backing content-addressed artifact was later corrupted.

## Shared verified-read prerequisite cost

The Stage08 prerequisite remediation compared the unsafe double-read baseline with the hardened single-buffer read using a 4 MiB artifact.

### Baseline

- logical content reads: `2`;
- bytes read: `8388608`;
- SHA-256 operations: `1`.

### Hardened

- logical content reads: `1`;
- bytes read: `4194304`;
- SHA-256 operations: `1`.

### Deterministic delta

- bytes read per call: `-4194304`;
- content-read reduction: `50%`;
- hash-operation change: `0`.

The correctness hardening therefore removed the TOCTOU double-read while also reducing deterministic I/O for verified content consumption.

## State-growth controls

Stage08 policy caps:

- query length;
- source identity/revision/locator length;
- provider descriptor field length;
- content bytes per item and per request;
- admitted result count;
- metadata key/value/item/total size;
- model-visible item count and preview characters;
- total durable retrieval items;
- durable request snapshots.

Capacity exhaustion fails closed rather than silently evicting history and changing replay semantics.

## Residual operational cost

A failed multi-item preparation may create content-addressed artifact files before a later candidate fails. Because the authoritative state/ref batch is not committed, those files remain unreferenced and cannot influence facts/context/resume. They can still consume disk space. A later content-addressed orphan-GC mechanism would reduce this operational cost without changing the Stage08 truth boundary.

## Result

**PASS.** The release probe stayed within all configured deterministic bounds and no cost optimization weakened integrity verification, provenance, resume validation or context trust separation.
