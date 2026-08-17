# Closed-Loop Meta Layer

This document describes the P0-P3 meta implementation added before connecting a real LLM provider or unrestricted executor.

## Scope

The meta layer introduces four contracts:

1. **Benchmark contract (P0)** — comparable baseline/harness records.
2. **Closed-loop contract (P1)** — `Context -> Reason -> Act -> Observe -> Verify`.
3. **Verification contract (P2)** — explicit success criteria and typed, verified evidence.
4. **Execution observation contract (P3)** — normalize tool outputs before feeding them back into the loop.

## Modules

- `harness/core/contracts.py`
- `harness/core/benchmark.py`
- `harness/core/verification.py`
- `harness/core/execution.py`
- `harness/core/orchestrator.py`

## Safety Boundary

The orchestrator does not select a model and does not execute commands by itself. Callers must inject a `reasoner` and an `executor`. This prevents the meta layer from turning the existing bounded intake workflow into an implicit arbitrary-command loop.

## Completion Semantics

A loop is complete only when required success criteria have verified evidence. Evidence presence by itself is insufficient. With no success criteria, verification does not implicitly pass.

## Intended Next Step

After benchmark fixtures establish a baseline, connect one real provider/runner behind the injected interfaces and measure the resulting delta. Adaptive retry and information-gain routing remain later stages rather than being mixed into this foundation.
