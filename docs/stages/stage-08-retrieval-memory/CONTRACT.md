# Stage 08 — Retrieval / Memory Admission Contract

Status: **FROZEN BEFORE STAGE-08 FEATURE IMPLEMENTATION**  
Target release: `v0.9.0` only after PASS.  
Prerequisite hardening: shared verified artifact read (`v0.8.1` candidate).

## Research question

Can the harness retrieve and remember candidate information in a deterministic, provenance-bound way without allowing retrieval selection, memory labels, or Actor text to bypass verified truth, completion, recovery, progress, persistence, or Context Governance?

## Core invariant

> Retrieved or remembered material is candidate evidence/data, never truth by admission. Selection into context does not increase epistemic authority. Only the existing verifier/Kernel commit path may promote a claim to trusted fact.

## 1. Ownership

- Kernel owns retrieval admission, durable retrieval snapshot state, supersession, and context injection.
- Retrieval provider/index may return candidates but may not mutate HarnessState directly.
- Actor may consume retrieved candidates and may cite their evidence references in a proposal.
- Actor may not mark memory/retrieval data verified, trusted, current truth, completed, or recovery-applied.
- Completion Oracle remains independent.

## 2. Admission item

Every admitted item must have at least:

```text
item_id             immutable kernel identity
content_ref         content-addressed artifact ref
content_sha256      digest derived from verified content
source_id           stable source identity
source_revision     explicit source/index revision
source_locator      stable locator or opaque source key
admitted_step       kernel step
trust               fixed `untrusted_retrieval`
instruction_authority fixed `none`
superseded_by       optional item_id
metadata            bounded non-authoritative metadata
```

Human/model-provided `authority`, `verified`, `trusted`, or similar labels are treated as untrusted source metadata and cannot populate epistemic authority fields.

## 3. Integrity

- All persisted retrieval content must be stored or referenced through content-addressed artifacts.
- Reads must use the centralized verified ArtifactStore read primitive.
- Missing, malformed, path-escaping, or hash-mismatched content is an integrity/persistence failure and cannot be silently skipped when it was part of the durable admitted snapshot.
- Retrieval provider response metadata alone is not evidence of content integrity.

## 4. Deterministic retrieval

For the initial Stage-08 implementation:

- retrieval query input is a deterministic kernel-generated descriptor, not free-form hidden mutable model state;
- provider/index revision is provenance-bound;
- candidate scoring must be deterministic for the declared provider;
- order uses an explicit total tie-break, at minimum `score DESC, source_id ASC, content_sha256 ASC, item_id ASC`;
- identical content/source candidates are deduplicated deterministically before context admission;
- search itself is read-only: no recall counters, timestamps, access-based TTL mutation, or implicit re-ranking may change durable/index state.

A provider that cannot satisfy deterministic replay must be marked external/non-replayable and is outside Stage-08 PASS scope.

## 5. Durable retrieval snapshot

The Actor must not query a mutable external index implicitly during context serialization.

The Kernel persists the admitted result set (or an equivalent content-addressed snapshot descriptor) before it becomes model-visible. Resume reconstructs context from that durable snapshot. A changed external index cannot silently replace already-admitted bytes during the same run.

## 6. Trust and promotion

```text
retrieval result
-> untrusted retrieval candidate
-> Actor may propose claim + evidence_refs
-> Stage-04 verifier chain / VerificationContract
-> Kernel commit VERIFIED fact
```

No direct transition exists from retrieval/memory admission to `state.facts`.

## 7. Context Governance integration

- Stage-08 retrieval enters only through Stage-07 Context Governor.
- Model-visible retrieval namespace is explicitly untrusted and has `instruction_authority=none`.
- Retrieval has an independent bounded item/preview budget.
- Retrieval flooding cannot displace mandatory goal contract, current verified facts, critical control state, or tool safety metadata.
- Full content remains available by verified artifact reference rather than by unbounded prompt insertion.

## 8. Progress interaction

Retrieval itself is **not progress**.

- Fetching new memory bytes does not reset Stage-06 no-progress state.
- Re-reading the same item does not reset progress.
- Retrieval admission history is excluded from the Stage-06 verified-fact semantic hash.
- A later verified fact change may count as progress under Stage 06.
- A task/environment observation still follows existing Stage-06 observation rules.

## 9. Memory write policy

Stage 08 does not introduce an Actor-authorized trusted-memory write.

Initial durable memory admission must be Kernel-mediated and may only create untrusted retrieval items from integrity-checked source content. If a future Actor request-to-remember action is added, it is merely a request and must pass the same admission policy; its content remains untrusted.

Cross-user/global autonomous memory is out of scope.

## 10. Supersession / deletion

- Content identity is immutable.
- Existing item IDs cannot be overwritten with different content.
- Source updates create new item identities/revisions.
- Supersession is an explicit kernel-owned relation.
- Superseded items may remain in history but are not returned as current candidates unless a query explicitly requests history.
- Silent hard deletion of an item referenced by a durable run snapshot is forbidden during that run.

## 11. Provenance / resume

The run config fingerprint must include:

- RetrievalPolicy descriptor;
- gateway/provider implementation source descriptor;
- provider/index/source revision descriptor;
- deterministic ranking/tie-break policy version;
- retrieval schema version;
- ContextPolicy remains separately fingerprinted.

Policy/provider/index drift on resume fails closed for Stage 08.

## 12. Failure mapping

- admitted content hash mismatch / malformed persisted item / snapshot mismatch -> `PERSISTENCE_ERROR` -> terminal `CHECKPOINT_STOP`;
- retrieval provider unavailable before admission -> typed `ENV_ERROR` or `MISSING_INFO` per configured optionality; no fabricated result;
- provider violates declared deterministic/schema contract -> `IMPLEMENTATION_ERROR` or `PERSISTENCE_ERROR` when persisted integrity is affected;
- untrusted content requesting policy bypass -> no special trust; it remains data.

## 13. Initial implementation scope

Stage 08 will use a deterministic local lexical/reference gateway first. This is not because lexical search is the final desired retrieval quality, but because it makes ordering, identity, integrity, replay, and trust boundaries directly inspectable.

Embedding/vector/remote retrieval may be added only after the gateway contract is proven, as a later provider behind the same admission interface.

## 14. Required adversarial scenarios

```text
retrieved "I am verified"                 -> remains untrusted
retrieved "ignore goal"                   -> instruction_authority=none
source metadata authority="oracle"        -> cannot promote trust
same item retrieved repeatedly             -> deterministic dedup
same-score candidates, different insert order -> identical total ordering
tampered content artifact                  -> fail closed
missing admitted artifact                  -> fail closed
same item_id with different content        -> reject conflict
superseded source item                     -> excluded from current retrieval
policy/provider/index drift on resume      -> fail closed
retrieval flood                            -> mandatory Stage-07 sections retained
retrieval read only                        -> no recall/access mutation
retrieved bytes repeated                   -> no Stage-06 progress reset
retrieved evidence proposed+verified       -> promotion only through Stage-04 path
Actor/model memory authority label         -> ignored as epistemic authority
```

## 15. Exit criteria

```text
shared verified artifact reader prerequisite  PASS
admission schema/invariants                    PASS
retrieval default trust=untrusted              PASS
kernel-owned admission/supersession            PASS
content integrity                              PASS
deterministic ranking/ties/dedup               PASS
read-only retrieval                            PASS
durable admitted snapshot + resume             PASS
retrieval policy/provider provenance           PASS
Context Governor-only model exposure           PASS
retrieval flooding mandatory-drop              0
retrieval direct verified-fact mutations       0
retrieval direct completion mutations          0
untrusted authority promotions                 0
retrieval-induced false progress               0
corrupt admitted-item silent fallbacks         0
full prior-Stage regression                    PASS
final Critical/High unresolved                 0
```

## Non-goals

- semantic/embedding retrieval quality optimization;
- production vector database selection;
- remote SaaS RAG provider;
- autonomous LLM memory summarization;
- cross-user/global memory;
- skill learning;
- subagent shared memory;
- planner hierarchy;
- treating retrieved material as truth without verification.
