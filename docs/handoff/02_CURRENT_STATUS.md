# 02 — Current Status

## Stage status

```text
Stage 00  COMPLETE
Stage 01  COMPLETE
Stage 02  PASS / EXITED
Stage 03  PASS / EXITED   v0.4.0
Stage 04  PASS / EXITED   v0.5.0
Stage 05  PASS / EXITED   v0.6.0
Stage 06  PASS / EXITED   v0.7.0
Stage 07  PASS / EXITED   v0.8.0
Stage 08  PASS / EXITED   v0.9.0
package   0.9.1 hardening line
```

## Existing guarantee boundaries

- Stage 02 production isolation requires a successful live `runtime_probe`; hosted namespace skips are not proof.
- Stage 03 non-idempotent execution is at-most-once automatic execution, not universal exactly-once semantics.
- Stage 04 generic structured verification does not solve arbitrary natural-language truth.
- Stage 05 proves durable recovery-control state, not guaranteed LLM semantic repair or arbitrary external rollback.
- Stage 06 proves deterministic/syntactic progress control, not semantic usefulness or goal relevance.
- Stage 07 proves deterministic context governance, not semantic relevance ranking or universal total prompt bounds.
- Stage 08 proves bounded retrieval admission as untrusted evidence, not autonomous trusted memory, semantic remote retrieval, or automatic cross-run learning.

## Current post-Stage08 baseline

The active branch is `develop`. `preprocessing` is the frozen pre-integration snapshot. Stage 00-08 are frozen except for confirmed defects. New practical integration work is managed as Tracks, not Stage 09+.

Current integration order:

```text
workspace
-> config/secrets
-> model gateway
-> agent control
-> structured tool contracts
-> MCP/plugin gateway
-> context relevance
-> cross-run memory
-> Software/Hackathon domain completion
-> progress/recovery alignment
-> real E2E/benchmark
-> TUI
```

## Mandatory invariant for integration

Provider, model, tool, MCP/plugin, retrieval, memory, and domain extensions may produce proposals/evidence/actions, but they may not directly promote trusted facts, mark completion, weaken capability/isolation checks, or bypass recovery/context/replay rules.

See `docs/tracks/integration-runtime/README.md` for the active implementation track.
