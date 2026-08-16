# 03 — Next Stage Task

# Stage 08 — Retrieval / Memory Gateway

Version target: `v0.9.0` only after PASS.

## Why this is next

Stage 07 established the Context Governor as the single runtime projection boundary. The architecture can now accept additional candidate knowledge without allowing that knowledge to silently rewrite trusted truth, but no retrieval or memory admission model exists yet.

Adding a vector database, long-term memory, or automatic memory writes immediately would create unresolved questions about provenance, authority, replay, deletion, and resume determinism. Stage 08 therefore starts with the **gateway contract**, not a retrieval product choice.

## First action

Do **not** begin by installing a vector DB, embedding model, RAG framework, or LLM-generated memory summarizer.

First perform a `v0.8.0` baseline re-review and freeze a **Retrieval / Memory Admission Contract** defining at minimum:

1. source identity and provenance for every retrieved/memory item;
2. integrity/content-address requirements for persisted items;
3. trust/authority level on admission — default untrusted unless separately verified;
4. which principal may write, supersede, expire, or delete memory;
5. whether Actor text can request memory writes and what validation is required;
6. deterministic retrieval query inputs and ordering/tie-breaking;
7. retrieval/context budget interaction through Stage 07 Context Governor;
8. duplicate/collision handling and source supersession;
9. resume determinism and config/index provenance;
10. corruption/tamper handling and fail-closed behavior;
11. how retrieved evidence can be verified and promoted without bypassing Stage 04;
12. prohibition on direct writes to verified facts, completion state, recovery history, or oracle result.

## Required preflight review

Inspect at minimum:

- `ContextProjector` extension/admission surface;
- `HarnessState` artifact/evidence/reference storage;
- `ArtifactStore` content-address and read-time integrity checks;
- manifest/config fingerprinting and checkpoint replay;
- DomainProfile extension points and memory policy placeholder;
- Actor Decision schema — especially whether any current path could mutate memory/trust without Kernel mediation;
- Stage 06 progress semantics if retrieved content is repeatedly reintroduced;
- Stage 05 failure routing for retrieval corruption/unavailability.

Record defects before implementation and repair prerequisites separately if needed.

## Required adversarial scenarios

```text
retrieved text says "I am verified"          -> remains untrusted
retrieved text says "ignore goal"            -> no instruction authority
same item retrieved repeatedly                -> deterministic deduplication
same score/tie ordering                       -> deterministic stable order
retrieval policy/index drift on resume        -> fail closed or explicitly versioned
persisted item tampered                       -> rejected / fail closed
Actor requests memory write                   -> cannot self-authorize trusted memory
memory source superseded                      -> stale item not treated as current source truth
retrieved artifact missing                    -> explicit failure, no fabricated fallback
retrieved evidence later verified             -> promotion only via Stage 04 path
retrieval flooding context                    -> Stage 07 mandatory goal/control preserved
retrieval repetition                          -> cannot falsely reset Stage 06 progress merely by re-reading known bytes
```

## Exit minimum

```text
Admission Contract frozen                    PASS
retrieval/memory trust default untrusted     PASS
Kernel-owned write/admission authority       PASS
content integrity + provenance               PASS
deterministic retrieval ordering             PASS
Stage 07 gateway-only context integration    PASS
resume config/index determinism              PASS
tamper/corruption fail closed                PASS
no direct trusted-state/completion mutation  PASS
no false Stage 06 progress from re-reading   PASS
full Stage 01-07 regression                  PASS
final re-review unresolved Critical/High     0
```

## Non-goals until contract is frozen

No production RAG provider, vector database, embedding model, cross-user global memory, model-generated autonomous long-term memory, skill learning, subagents, or planner hierarchy should be selected merely to start implementation. Tool choice follows the contract, not the reverse.
