# COST_REPORT — Stage08 Retrieval Ownership Remediation

Release CI: `31954492789`

## Deterministic costs added by remediation

- current retrieval artifacts are verified once each before model-visible projection;
- result count/content/metadata/history have hard policy bounds;
- provider descriptor is inspected before and after search for mutation detection;
- failed batch preparation can write content-addressed files but does not add authoritative state/ref entries.

## Release probe

- 5 admitted items / 500035 artifact bytes;
- model-visible retrieval preview 3000 chars;
- model-visible metadata 2000 chars;
- retrieval JSON 8052 chars;
- full context 12149 chars;
- per projection: 5 verified artifact reads / 500035 bytes;
- median release-runner projection verification time: ~0.001759s over 20 rounds.

## Shared integrity primitive effect

For a 4 MiB artifact, verified-read hardening reduced deterministic reads from 2 to 1 and bytes read from 8 MiB to 4 MiB while keeping one SHA-256 operation.

## Residual

Unreferenced artifact files from failed preparation can consume disk. This is an operational GC cost and not an authority bypass.
