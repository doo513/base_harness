# Stage 08 Evidence Matrix

Release commit: `a5645fc9d059afd12088ee1c4751c0250c8a5206`  
Release CI: `31954492789`  
Result: **PASS / EXITED (`v0.9.0`)**

| Contract / risk | Evidence | Release result | Interpretation |
|---|---|---:|---|
| Retrieval is not trusted truth | `stage8_retrieval_probe.py` — `untrusted_authority_boundary` | PASS | direct fact mutations `0`, completion mutations `0`, observation injections `0` |
| Retrieval has no instruction authority | governed context projection + base/adversarial tests | PASS | projected trust fixed to `untrusted_retrieval`; authority `none` |
| Retrieval is not Stage06 progress | `stage8_retrieval_probe.py` — `retrieval_not_progress` | PASS | progress events `0`; no-progress streak advances |
| Deterministic ordering | base probe — `deterministic_total_order` | PASS | result count `3`; stable total order |
| Bounded model projection | base probe — `bounded_projection` | PASS | selected `2`, omitted `3`, preview chars `60`, metadata chars `30` |
| Provider search mutation blocked | adversarial probe — `provider_mutation_blocked` | PASS | admitted items `0` after descriptor mutation |
| Oversized result fails before authoritative admission | adversarial probe — `oversized_content_atomic_block` | PASS | admitted items `0`, authoritative artifact refs `0` |
| Mid-batch candidate failure is state-atomic | adversarial probe — `mid_batch_failure_state_atomic` + transaction unit test | PASS | live items `0`, snapshots `0`, artifact refs `0` |
| Forged durable request identity rejected | adversarial probe — `forged_request_identity_blocked` | PASS | Kernel re-derives request identity |
| Supersession is explicit | adversarial probe — `explicit_supersession_only` | PASS | old item does not re-enter current set |
| Durable history/item bounds fail closed | adversarial probe — `history_capacity_fail_closed` + unit tests | PASS | prior durable item set retained; no silent eviction |
| Same snapshot resumes exactly | resume probe — `exact_snapshot_and_projection_resume` | PASS | item count `1`; state/projection exact |
| Missing retrieval artifact fails resume | resume probe | PASS | missing artifact acceptance `0` |
| Tampered retrieval artifact fails resume | resume probe | PASS | tamper acceptance `0` |
| Provider/index drift fails resume | resume probe | PASS | drift acceptance `0` |
| Artifact verified-read single-buffer prerequisite | `stage8_artifact_integrity_probe.py` | 6/6 PASS | unverified return buffers `0` |
| Artifact path/ref/tamper/swap attacks | same artifact probe | PASS | malformed/missing/path-escape/swap/tamper all blocked |
| Storage write failure mapped as persistence | `test_storage_write_oserror_becomes_persistence_failure_and_leaves_state_clean` | PASS | public retrieval decision records `persistence_error` |
| Retrieval policy/provider config is resume-significant | config descriptor + resume drift probe | PASS | retrieval policy/provider/index in runtime config fingerprint |
| Stage07 compatibility preserved | Stage07 compatibility/context probes | PASS | no Python/JSON split-brain; old mixin boundary preserved |
| Stage06 semantic-progress boundary preserved | Stage06 release regression probes | PASS | activity novelty false progress `0` |
| Stage03 resume semantics preserved | Stage03 resume probe | 4/4 PASS | duplicate external actions `0` |
| Stage04 semantic gate preserved | Stage04 semantic probe | 8/8 PASS | FP `0`, FN `0` |
| Stage05 recovery semantics preserved | Stage05 base/adversarial/terminal/crash/strategy probes | PASS | unsafe retry/recovery divergence metrics remain `0` |
| Stage02 nested submount defense preserved | nested-submount remediation probe | PASS | unsafe raw semantics reproduced; Harness defense blocks it |
| Stage02 backend binding preserved | tool-backend remediation probe | PASS | unsafe handler calls `0`, private canary unchanged |

## Full regression

```text
182 passed, 5 skipped in 14.54s
```

The five skips are hosted-environment cases and are not counted as live production-isolation evidence.

## Release environment

- GitHub hosted runner: Ubuntu `24.04.4`;
- runner image: `ubuntu-24.04`, version `20260810.271.1`;
- CPython `3.11.15`;
- Git `2.54.0`;
- locked pytest `9.1.1`;
- built/installed package: `verified-state-harness 0.9.0`.

## Evidence quality boundary

This matrix proves the shipped local lexical retrieval path and Kernel integration under the recorded release environment. It does not prove hidden internal honesty of arbitrary remote providers, independent clean-host Stage02 production isolation, or semantic task-level usefulness of retrieved evidence.
