# Core Freeze Snapshot — 0.9.1

## Purpose

`0.9.1` is a post-Stage08 Core Freeze patch marker. It does **not** introduce Stage09 or a new architecture layer.

It separates the Stage08 `0.9.0` exit state from the subsequent Core Freeze corrections discovered by a source-first post-Stage08 audit.

## Hardening included

Implementation commit: `abed36ae430d0aa11711da267750847f792d61b6`

- evidence novelty for refuted-hypothesis reopen is based on integrity-verified content digest + stable source provenance rather than ref-string novelty;
- successful same-key verified commit clears the current stale refuted marker while event history remains durable;
- large structured tool output remains exact in content-addressed artifact storage while durable Observation preview/error are bounded;
- new Core Freeze direct probe is a permanent CI gate.

## Validation

Implementation CI: `31959676893` — SUCCESS.

- pytest: `209 passed, 5 skipped`;
- Core Freeze scenarios: 4/4 PASS;
- Stage02~08 prior regression/probe gates: PASS.

Measured Core Freeze cost proxy:

```text
large structured output canonical chars: 40073
durable Observation preview chars:       2861
serialized preview reduction:            92.8605%
```

This is serialized-character storage/checkpoint proxy, not token count.

## Version-freeze migration evidence

The first `0.9.1` metadata candidate (`690bfeb...`, CI `31960001871`) intentionally remained red and is retained as evidence:

```text
1 failed, 208 passed, 5 skipped
```

Cause: `pyproject.toml` had moved to `0.9.1` while runtime `harness.__version__` still declared `0.9.0`; `tests/test_version_consistency.py` correctly blocked the inconsistent freeze candidate. The fix is to update both build and runtime version identity before accepting the freeze head.

## Freeze boundary

The following are **not** blockers for the 0.9.1 Core Freeze and remain Track work:

- independent clean-host reproduction;
- official benchmark/release immutable execution profile;
- broader Software security / CTF semantic verifier coverage;
- real stochastic LLM/repository/CTF evaluation;
- domain-specific task milestones;
- full harness ablation;
- >64K ContractArtifact support;
- safe global orphan GC;
- remote-provider provenance/replay proof.

The last three are conditional/deferred unless workload or roadmap evidence establishes need.

## Claim boundary

`0.9.1` means the reviewed Core mechanisms and regression gates are frozen at this patch line. It does not claim that end-to-end task success, cost efficiency, or cross-host reproducibility is already proven. Those are benchmark/external-validation claims and must remain separate.
