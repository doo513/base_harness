# Stage 07 — Context Governance Implementation Report

Status: **PASS candidate for v0.8.0**  
Branch: `research/verified-state-stage03`  
Final candidate: `757ec837c7a0eb83bdab71c497851fef196f13e8` (`v0.8.0rc5`)

## 1. Objective

Stage 07 replaces broad direct Actor context exposure with a deterministic, kernel-configured projection boundary. The Context Governor may reduce or reorganize what the Actor sees, but it may not rewrite truth authority, completion authority, recovery state, or goal requirements.

Implemented flow:

```text
HarnessState + GoalContract + Tool metadata
  -> ContextPolicy
  -> ContextProjector (pure deterministic projection)
  -> RuntimeContextProjection
  -> built-in Controller / model JSON
```

The model-visible dict contains namespaced governed data only. Compatibility access for trusted in-process Controllers is held outside the serialized dict.

## 2. Main implementation

### 2.1 Namespaced projection

The model-visible context is divided into explicit namespaces including goal contract, trusted state, untrusted material, control state, tools, and projection metadata. Goal, acceptance criteria, ordinary constraints, pinned constraints, current verified facts, critical recovery/progress state, and tool safety metadata are retained as mandatory information.

### 2.2 Trust boundary

Verified current facts are projected separately from hypotheses, refuted hypotheses, observations, failures, and other untrusted material. Untrusted text is explicitly marked as having no instruction authority. The built-in LLM Controller system instruction also states that untrusted fields are data and cannot override system, goal, policy, or oracle requirements.

### 2.3 Freshness and supersession

Facts with `superseded_by` are excluded from current truth and represented separately. Existing `valid_until` metadata is surfaced, but Stage 07 deliberately does not interpret it against wall-clock time because that would make the same persisted state project differently solely because resume occurred later.

### 2.4 Bounded observation projection

Observations remain durably stored in full artifact form. The context projection groups duplicate content by content-address identity, orders deterministically, limits visible groups/previews, and retains artifact references for drill-down. Context reduction therefore does not delete raw evidence.

### 2.5 Context policy provenance

`ContextPolicy` parameters are included in runtime configuration provenance. A resume under a different context policy fails closed rather than silently giving the Actor a different projection from the same checkpoint.

### 2.6 Compatibility boundary

A compatibility defect was found after the initial implementation. Simply aliasing old top-level names to new namespaces preserved key lookup but not the old value schema. For example, old Controller code could expect:

```python
context["hypotheses"]["h"]["value"]
```

while the new model projection intentionally exposes a bounded `value_preview`.

`RuntimeContextProjection` now keeps a detached, non-serialized legacy snapshot only for fields that moved out of the old top-level schema. This preserves trusted in-process Controller reads without leaking raw legacy values into model serialization.

Real Stage-07 top-level keys such as `tools` are not shadowed by hidden legacy values. Python lookup and JSON/model serialization therefore see the same governed tool value, preventing a split-brain context API.

### 2.7 Single projection owner

Final structural review found the pre-Stage-07 raw `_context()` implementation still present in `RuntimeExecutionMixin`. It was not active because MRO selected `RuntimeContextMixin`, but it was a future bypass risk. It was removed, and a regression test now requires `RuntimeContextMixin` to be the only runtime `_context()` implementation.

### 2.8 Version consistency

Final release preparation found `harness.__version__` and `pyproject.toml` could diverge. A version-consistency regression test was added and both candidate sources are now `0.8.0rc5`.

## 3. Candidate history / discovered errors

| Candidate | Result | Finding / correction |
|---|---|---|
| rc1 | PASS candidate | Core deterministic Context Governor implemented. |
| rc2 | PASS | Trusted Controller compatibility aliases added, but review found the tests checked mostly key existence rather than old raw value/schema compatibility. |
| rc3 | FAIL | Stronger compatibility test exposed an over-strong assumption for `tools`; 122 passed / 5 skipped / 1 failed. A hidden legacy value for a real Stage-07 top-level key would create Python/JSON split-brain behavior. |
| rc4 | PASS | Compatibility contract corrected: moved keys preserve raw trusted-controller schema; actual Stage-07 keys keep one governed value. |
| rc5 | PASS | Removed dormant raw `_context()` from execution mixin and made Context Governor the sole projection boundary. |
| pre-release hardening | PASS | Build metadata/runtime version divergence fixed and permanently regression-tested. |

## 4. Methodology

Stage 07 used the same failure-driven workflow as prior stages:

1. Re-review Stage 06 release baseline.
2. Freeze Context Projection Contract before retrieval/memory work.
3. Implement deterministic projection only.
4. Add direct and adversarial trust-boundary probes.
5. Verify projection determinism across resume and fail closed on policy drift.
6. Re-test old trusted Controller access instead of assuming key aliases meant API compatibility.
7. Treat every transition boundary and duplicate implementation as a potential bypass.
8. Re-run all Stage 03–06 gates after each correction.
9. Fix Git/package version consistency before promotion.

No earlier Stage gate was weakened.

## 5. Final candidate evidence

Candidate commit `757ec837c7a0eb83bdab71c497851fef196f13e8`, GitHub Actions `31943066462`:

```text
installed package                   0.8.0rc5
compileall                          PASS
pytest                              125 passed / 5 skipped
Stage 03 resume                     4 / 4 PASS; duplicate external actions 0
Stage 04 semantic                   8 / 8 PASS; FP=0/FN=0
Stage 05 all direct probes          PASS
Stage 06 all direct probes          PASS
Stage 07 base projection            4 / 4 PASS
Stage 07 adversarial trust          6 / 6 PASS
Stage 07 resume/determinism         3 / 3 PASS
Stage 07 compatibility              3 / 3 PASS
missing mandatory constraints       0
projection state mutations          0
untrusted authority promotions      0
superseded current-truth exposures  0
model-visible legacy raw values     0
legacy moved-schema breakages       0
Python/JSON split-brain keys        0
```

Five skipped tests remain hosted-environment live Linux namespace tests. They are not Stage 02 production-isolation evidence.

## 6. Guarantee boundary

Stage 07 guarantees a deterministic governed projection boundary for the built-in model path and runtime Controller context. It does not claim:

- a universal fixed total prompt size when mandatory goal/trusted/control data itself is arbitrarily large;
- semantic relevance ranking of evidence;
- automatic expiration of `valid_until` based on wall-clock time;
- RAG, embeddings, long-term memory, model-generated summarization, skills, subagents, or planner hierarchy;
- that arbitrary custom code bypassing the runtime context API is governed;
- that retrieval/memory content becomes trusted merely because it is selected into context.

Any future retrieval or memory subsystem must enter through the Context Governor and remain untrusted until the existing verification path promotes it.
