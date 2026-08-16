# Stage 07 — Evidence Matrix

Status: **PASS candidate**  
Candidate: `757ec837c7a0eb83bdab71c497851fef196f13e8`  
Actions: `31943066462`

| Requirement | Evidence | Result |
|---|---|---|
| Context Projection Contract frozen before semantic expansion | `docs/stages/stage-07-context-governance/CONTRACT.md` | PASS |
| Context Governor is single runtime projection boundary | `RuntimeContextMixin._context()` exists; `RuntimeExecutionMixin._context()` regression-forbidden | PASS |
| goal / acceptance / constraints / pinned constraints retained | Stage 07 base probe | PASS |
| current verified facts separated from untrusted state | context tests + adversarial probe | PASS |
| superseded fact not exposed as current truth | adversarial probe | PASS, exposures=0 |
| untrusted text has no system/instruction authority | built-in LLM system boundary + projection metadata | PASS, promotions=0 |
| hypothesis text cannot self-claim VERIFIED authority | adversarial probe | PASS |
| duplicate observations bounded | base probe: 3 raw observations -> 2 groups, 1 duplicate collapsed | PASS |
| raw artifact references retained | base probe, raw evidence deletions=0 | PASS |
| preview/tool text bounded by ContextPolicy | base/adversarial/compatibility probes | PASS |
| same state + same policy -> same projection | resume probe, equal projection hashes | PASS |
| projection mutates neither fresh nor resumed state | base/resume probes | PASS, mutations=0 |
| context policy drift on resume | resume probe | FAIL CLOSED |
| legacy trusted Controller moved-field value/schema compatibility | compatibility probe | PASS, breakages=0 |
| legacy raw compatibility values absent from model JSON | compatibility probe | PASS, exposures=0 |
| real Stage-07 keys use same Python/JSON governed value | compatibility probe | PASS, split-brain=0 |
| build/runtime package version consistency | `tests/test_version_consistency.py` | PASS |
| Stage 03 persistence/resume regression | direct Stage 03 probe | 4/4 PASS, duplicate=0 |
| Stage 04 semantic regression | semantic matrix | 8/8 PASS, FP=0/FN=0 |
| Stage 05 recovery regression | all Stage 05 probes | PASS |
| Stage 06 progress regression | all Stage 06 probes | PASS |
| full regression | GitHub Actions `31943066462` | 125 passed / 5 skipped |

## Zero-tolerance counters

```text
missing mandatory constraints       0
projection state mutations          0
raw evidence deletions              0
untrusted authority promotions      0
superseded current-truth exposures  0
policy drift acceptances            0
projection resume divergence        0
model-visible legacy raw values     0
legacy moved-schema breakages       0
Python/JSON split-brain keys        0
unresolved Critical/High            0
```

## Evidence limitation

The five skipped tests are live Linux namespace isolation tests unavailable on the hosted runner. They are not counted as Stage 02 production isolation proof and do not weaken the previously established Stage 02 requirement for a successful live runtime attestation.
