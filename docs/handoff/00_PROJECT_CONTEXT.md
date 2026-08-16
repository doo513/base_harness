# 00 — Project Context

## Why this project exists

The working thesis is that LLM agent failures are often caused less by raw reasoning capability and more by weak harness control over what information enters context, what is treated as current truth, what actions are legal, how failures are classified, and who is allowed to declare success.

```text
목적을 정확히 유지하고 → 잘 보고 → 검증된 것만 기억하고
→ 틀리면 원인에 맞게 고치고 → 진짜 성공인지 외부에서 확인한다
```

Engineering form:

```text
Goal Contract → Observation / Context Gate → Trusted Working State
→ Controller / Actor → Tool Runtime → Verification
→ State Commit OR Failure Recovery → repeat
```

Core principles: explicit/persistent goal; filtered observation with raw evidence retained; memory is not current truth; failure-aware recovery; external/deterministic final success where available.

Research positioning: do not call this universal, first, or better than all existing harnesses. Accurate claim: **a research kernel for evidence-gated state transitions and truth authority, designed to test whether false completion and state corruption can be reduced across domains.**

Domains: CTF/Security, Software/App development, Hackathon/product building. Kernel mechanics stay shared; semantics belong in Domain Profiles.
