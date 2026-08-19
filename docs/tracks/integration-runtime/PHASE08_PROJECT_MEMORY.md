# Phase 08 — Cross-Run Project / Episodic Memory

Status: IMPLEMENTED; integrity/isolation/cross-run tests added; automatic trusted learning is intentionally not implemented.

## Problem / evidence

Stage 08 provided bounded retrieval admission and a read-only lexical memory compatibility facade, but there was no safe way to carry useful project/episodic knowledge from one run into a later run. Writing model text directly into trusted facts would violate the verified-state kernel.

## Contract

- cross-run memory is always `untrusted_project_memory` with `instruction_authority=none`;
- the Actor stages a candidate through the existing untrusted hypothesis path using reserved keys `memory_candidate.*`;
- candidate value is bounded and limited to `kind`, `content`, and `tags`;
- candidate publication requires at least one artifact reference already registered in the run state;
- memory candidates are never verified/promoted merely by being remembered;
- publication happens only after the runtime returns, so a resumable run does not observe its own external memory writes;
- each run reads a frozen memory snapshot through the existing Stage-08 retrieval gateway;
- memory storage must not overlap the actor workspace;
- memory records are content/integrity checked and bounded.

## Implementation

- added `MemoryConfig` with explicit opt-in `enabled`, external `root`, and optional `project_id`;
- added `ProjectMemoryStore`, `ProjectMemoryRecord`, and `ProjectMemoryRetrievalGateway`;
- memory records are atomically written as integrity envelopes in a project-specific external store;
- record count/content/tag limits prevent unbounded accumulation;
- store loading fails closed on malformed/tampered envelopes;
- run-start store state is converted into an immutable lexical retrieval snapshot with its own index revision;
- the Actor receives a system-level staging convention and a model-visible `project_memory` capability descriptor;
- CLI passes the frozen project-memory gateway into the existing retrieval runtime and publishes valid candidates after `runtime.run()` returns;
- memory retrieval therefore uses the normal untrusted retrieval/artifact/context path and receives zero progress credit.

## Structural review

- no memory record can directly enter `HarnessState.facts`;
- `memory_candidate.*` remains an untrusted proposal and should not be sent to domain verification;
- remembered text cannot become an instruction through retrieval or active context;
- external memory is outside the workspace so actor file/shell tools cannot modify it under the intended workspace boundary;
- new memory is invisible to the current run, preventing self-written memory from changing the active retrieval index;
- a later run gets a new deterministic index snapshot; external memory drift during resume is therefore detected by existing retrieval configuration/index provenance rather than silently accepted.

## Validation focus

`tests/test_integration_project_memory.py` covers:

- post-run publication and next-snapshot retrieval;
- frozen current-run gateway despite later publication;
- untrusted metadata preservation;
- rejection of candidates without registered evidence;
- workspace/memory-root overlap rejection;
- integrity-envelope tamper rejection;
- explicit config opt-in and disabled default.

## Remaining limitations

- publication currently scans reserved untrusted hypotheses rather than using a dedicated memory Decision type; this intentionally reuses an already-governed untrusted path;
- evidence references are registered run artifacts but the external memory record does not copy the evidence bytes;
- no automatic summarizer decides what to remember; the Actor may propose candidates and the Kernel admission contract only decides whether they are safe to persist;
- no decay/expiry/garbage collection is implemented yet; capacity is bounded and policy can be extended from real workload evidence;
- concurrent project-memory writers are not coordinated beyond atomic individual-file creation and require later hardening if concurrent runs become a real use case.
