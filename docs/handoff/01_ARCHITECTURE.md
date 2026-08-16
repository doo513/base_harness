# 01 — Architecture

```text
① GOAL / CONTRACT
② CONTEXT GOVERNOR
③ VERIFIED STATE
④ ACTION RUNTIME
⑤ BUDGET / TERMINATION
⑥ FAILURE ROUTER
⑦ VERIFIER CHAIN (V0 schema → V5 external/sealed oracle)
⑧ COMMIT / CHECKPOINT / EVENT LOG / ARTIFACT
⑨ MEMORY LIFECYCLE
⑩ OPTIONAL EXTENSIONS (Retrieval / Skill / Subagent)
```

Critical invariant:

```text
Unverified Claim != Trusted Fact
Completion Request != Completion
Observation != Truth
Memory != Current State
Subagent Output != Trusted State
```

State uses two independent dimensions: epistemic status (`PROPOSED/SUPPORTED/VERIFIED/REFUTED`) and authority (`USER/MODEL/ENVIRONMENT/TRUSTED_TOOL/UNTRUSTED_TOOL/EXTERNAL_ORACLE`).

Kernel owns mechanics: goal contract, mutation rules, tool boundary, verification protocol, failure routing, persistence, logging, budgets, extension gateway. Domain Profile owns semantics: tools, domain state, failure extensions, verifier implementations, completion oracle, memory policy, domain constraints.
