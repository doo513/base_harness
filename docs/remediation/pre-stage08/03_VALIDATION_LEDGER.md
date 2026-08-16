# 03 — Validation Ledger

이 ledger는 **어떤 evidence까지 확보되어 현재 어떤 수준의 주장을 할 수 있는가**를 기록한다. Mechanism PASS와 external-validity/reproducibility gap을 구분한다.

## 1. Current validated code head

문서 정정 직전 마지막 code-only validated head:

- branch: `research/verified-state-stage03`
- code/test head: `d72f7e9b468702fb2a787870278e4008919acabb`
- workflow: `31957540019`
- package: `verified-state-harness 0.9.0`
- result: **SUCCESS**
- full pytest: **205 passed / 5 skipped**

동일 workflow에서 성공한 주요 gate:

- Stage03 resume probe;
- Stage04 semantic probe;
- Stage04 repository-style semantic benchmark;
- Stage05 recovery / adversarial / terminal / crash-window / strategy probes;
- Stage05 Recovery effectiveness A/B benchmark;
- Stage06 base / adversarial / resume / boundary / strategy probes;
- Stage06 task-world progress probe;
- Stage07 base / adversarial / resume / compatibility probes;
- Stage07 trusted-context growth / cost probes;
- Stage07 mandatory goal bounds probe;
- Stage08 retrieval base / adversarial / resume / cost probes;
- Stage08 single-buffer artifact integrity probe;
- verified-read cost probe;
- Stage02 nested read-only submount / cost probes;
- Stage02 backend-execution binding / cost probes.

## 2. Current remediation ledger

| ID | 검증 범위 | Evidence | 현재 판정 |
|---|---|---|---|
| R08-INTEGRITY-001 | verified artifact single-buffer integrity | race/tamper/missing/path escape + cost + regression | **PASS** |
| R02-ISOLATION-001 | nested mount fail-closed policy | live writable-descendant repro + defense + cost | **PASS on validated host; independent clean-host gap remains** |
| R02-EXEC-002 | ToolSpec/backend execution binding | unsafe mismatch blocked before handler; safe path attestation=execution | **PASS** |
| R03-PROV-001 | semantic runtime/build provenance | lock/build/source/toolchain config/resume binding + manifest | **PASS for current semantic provenance scope; immutable environment breadth PARTIAL** |
| R04-VERIFY-001 | claim-class verification | registry fail-closed + 8-case mechanism matrix | **PASS for registered classes** |
| R04-REALWORLD-002 | repository-style execution semantics | 17 cases, TP=5/TN=12/FP=0/FN=0 | **PASS for frozen software corpus; broader classes PARTIAL** |
| R05-EFFECT-001 | controlled Recovery causal utility | matched A/B recoverable 3/3 vs 0/3, safety regressions 0 | **PASS for controlled benchmark; broad effectiveness PARTIAL** |
| R06-PROGRESS-001 | activity/epistemic split | novelty credit 0, fact transition credit 1, resume/strategy probes | **PASS** |
| R06-TASK-002 | explicit task/world progress | monotonic profile milestones/score, regression credit 0, pure bounded hook | **PASS for mechanism; domain milestone coverage PARTIAL** |
| R07-CONTEXT-001 | bounded trusted-fact projection | growth/cost + prior Stage07 probes | **PASS** |
| R07-GOAL-002 | mandatory GoalContract bounds | 5 direct cases, silent truncation 0 | **PASS for current in-memory contract** |
| R08-RETRIEVAL-002 | typed retrieval authority/integrity | base/adversarial/resume/cost + batch atomic state admission | **PASS / v0.9.0 scope** |

## 3. Quantitative evidence snapshots

### Stage04 repository semantic corpus

```text
cases           17
true positives   5
true negatives  12
false positives  0
false negatives  0
```

Positive claim classes:

- `software.build_result`
- `software.test_result`
- `software.behavioral_acceptance`

Unknown `software.security_property` remains rejected rather than silently generalized.

### Stage05 Recovery A/B

```text
recoverable scenarios                    3
Recovery completion rate               1.0
No-recovery completion rate            0.0
completion-rate delta                  +1.0
safety regressions                       0
additional persisted steps / success   +2.3333
additional tool calls / success        +1.3333
```

### Stage06 task/world authority

```text
implicit task authority                    0
regressions credited                       0
snapshot state mutations accepted          0
explicit monotonic task progress events    1
```

### Stage07 context/goal bounds

Trusted-context cost probe:

```text
raw full verified-fact serialized chars   1,037,090
bounded full context chars                    7,660
reduction ratio                              0.992614
```

Measurement is serialized-character proxy, not token count.

Goal contract probe:

```text
scenarios           5
all passed       true
silent truncation   0
```

### Stage08 retrieval

Adversarial probe confirms:

```text
partial admission failures   0
implicit supersessions       0
mid-batch failed live items  0
mid-batch live snapshots     0
mid-batch live artifact refs 0
```

Cost probe on 5 × ~100 kB candidates:

```text
raw/artifact bytes                  500,035
model-visible retrieval JSON chars    8,052
preview chars                         3,000
metadata chars                        2,000
verified logical reads / projection       5
```

Wall time is environment-specific and not correctness evidence.

## 4. Meaningful failed validations retained as evidence

### F-ARTIFACT-001 — ArtifactStore reconstruction regression

- result: `129 passed / 5 skipped / 2 failed`.
- cause: manual restoration이 Stage03 manifest/checkpoint envelope를 잘못 재구성.
- response: exact baseline storage semantics 복원 후 targeted hardening만 재적용.

### F-PROV-001 — Runtime run-loop truncation

- result: `49 failed / 91 passed / 5 skipped`.
- cause: provenance refactor 중 `HarnessRuntime.run()`/budget terminalization 유실.
- response: 즉시 hardening 중단, `970a365...`에서 runtime 복원, full green 후 재개.

### F-PROGRESS-001 — stale unit-test contract

- CI `31950606445`: `147 passed / 5 skipped / 1 failed`.
- 원인: legacy `novel observation = progress` expectation.
- production rollback 대신 test oracle migration.

### F-PROGRESS-002 — stale direct-probe contract

- CI `31950681824`: pytest `148 passed / 5 skipped`, strategy direct probe FAIL.
- 원인: direct probe도 legacy novelty assumption 보유.
- probe contract migration 후 green.

### F-STAGE08-001 — bound-test fixture inconsistency

- Stage08 hardening candidate에서 `5 failed / 173 passed / 5 skipped`.
- 원인: `max_admitted_per_request`를 1~2로 낮추면서 `max_context_items` 기본값 5를 그대로 둔 invalid policy fixture.
- production bound를 완화하지 않고 fixture를 정책 일관성에 맞게 수정.

### F-STAGE08-002 — adversarial fixture stale copy

- 다음 candidate는 full pytest와 prior Stage probes가 green이었지만 Stage08 adversarial probe가 같은 fixture inconsistency로 FAIL.
- adversarial fixture도 수정하고 이후 전체 gate 재검증.

### F-PROGRESS-003 — green candidate에서 발견한 regression-as-progress 설계 결함

- 첫 task/world progress implementation은 deterministic snapshot hash change에 credit을 부여했다.
- CI가 green이었지만 re-review에서 score 감소/milestone 제거도 hash change이므로 progress로 오인될 수 있음을 발견.
- monotonic milestone/score contract로 교체하고 regression credit=0 probe를 추가했다.
- 이 사례는 **green test가 semantic correctness의 충분조건이 아님**을 보여주는 evidence로 유지한다.

## 5. Reproducibility environment of latest validation

Latest validated GitHub Actions environment:

```text
Ubuntu 24.04.4 LTS
runner image: ubuntu-24.04 / 20260810.271.1
Python 3.11.15
git 2.54.0
package 0.9.0
```

Stage02 live nested-mount probe는 uid 0에서 실제 실행됐다. 그러나 independent clean-host reproduction은 별도 open item이다.

## 6. Overall decision

```text
Integrity/security P0                 PASS
Stage03 provenance mechanism          PASS (environment breadth PARTIAL)
Stage04 registered semantics          PASS (broader domain coverage PARTIAL)
Stage05 controlled Recovery utility   PASS (broad real-world effectiveness PARTIAL)
Stage06 progress mechanism            PASS (domain milestone definitions PARTIAL)
Stage07 context + entry bounds        PASS (long-contract support not implemented)
Stage08 retrieval v0.9.0 scope        PASS
Current code blocker                  NONE IDENTIFIED by validated suite/re-review
```

따라서 현재 구현된 remediation mechanism set은 **green integration 상태**다. 남은 항목은 `04_OPEN_ITEMS.md`의 external reproducibility, broader empirical coverage, future-provider/operational 범위이며 이를 현재 code PASS와 혼동하지 않는다.
