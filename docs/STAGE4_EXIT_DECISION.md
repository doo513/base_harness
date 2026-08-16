# Stage 04 Exit Decision

## Decision

**PASS / EXITED**

Release promoted: `v0.5.0`.

## Gate evaluation

| Gate | Result | Evidence |
|---|---|---|
| verification contract frozen before final promotion | PASS | `docs/stages/stage-04-semantic-verification/CONTRACT.md` |
| verifier level self-inflation blocked | PASS | unit + semantic probe |
| result coverage spoof blocked | PASS | unit test |
| evidence required for semantic coverage | PASS | contract tests |
| artifact content tamper blocked | PASS | unit + semantic probe |
| generic semantic-key masquerade blocked | PASS | unit + semantic probe |
| free-form generic semantic promotion blocked | PASS | unit + semantic probe |
| contract/verifier provenance fingerprinted | PASS | manifest test |
| cross-version resume drift blocked | PASS | version provenance regression test |
| full regression | PASS | 69 passed, 5 environment-dependent skips |
| Stage 03 direct resume probe | PASS | 4/4; duplicate external action 0 |
| compile | PASS | GitHub Actions |
| unexplained earlier-Stage regression | NONE | rc1 regression was explained, repaired, and re-tested |

## Promotion evidence

Promotion candidate:

```text
version      v0.5.0-rc3
commit       11e707cf04ea76f20a9b810d159a58fe1c1e2430
CI run       31934328945
pytest       69 passed / 5 skipped
```

Final release snapshot:

```text
version      v0.5.0
commit       d659124cae444cc2a1193d97eb86f97325a22156
CI run       31934469736
pytest       69 passed / 5 skipped
Stage 03     4/4 direct resume probes PASS
duplicates   0 external duplicate actions
Stage 04     semantic probe PASS; FP=0; FN=0
```

Stage 04 direct semantic evidence:

```text
matrix cases                 8
false positives              0
false negatives              0
level inflation blocked      true
artifact tamper blocked      true
semantic-key masquerade      true
all matrix cases pass        true
```

## Important interpretation

`PASS` means the declared semantic-authority contract is enforced for the implemented structured verification mechanism. It does not mean that generic natural-language semantics are solved.

Domain-specific semantic facts still require a Domain Profile verifier whose configured coverage and strength satisfy that Domain Profile's contract.

## Next allowed stage

**Stage 05 — Failure Recovery**.

Stage 05 must not begin by adding planners or loop detectors. Its first task is to freeze a kernel-owned recovery-transition contract around the existing `FailureRouter`, which currently recommends recovery actions but does not itself execute a durable recovery transition.
