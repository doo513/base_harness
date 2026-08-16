# 04 — Open Items

이 문서는 remediation이 현재 해결했다고 주장하지 않는 항목을 유지한다. Green CI가 존재한다는 이유로 external-validity/reproducibility/future-provider gap까지 닫지 않는다.

## Stage08 closed entry blockers

### O08-001 — Retrieval query ownership runtime

상태: **CLOSED for Stage08 frozen scope — v0.9.0**

Actor-controlled field는 explicit `query` text이고, Kernel은 normalization, scope, top-k, provider/index identity, ranking policy, candidate admission, durable request identity, result/content/history bounds와 context authority를 소유/검증한다.

Residual: semantic query planning 자체는 Stage08 범위가 아니다.

### O08-002 — Retrieval artifact admission

상태: **CLOSED for Stage08 authority/integrity scope — v0.9.0**

Content-addressed storage, single-buffer verified read, provider/source/content binding, batch state-side atomicity, tamper/missing resume fail-closed, storage I/O persistence routing이 구현됐다.

Residual: failed preparation 중 생긴 unreferenced physical artifact는 아래 O08-003 operational GC 범위다.

## Stage00 / Stage01 documentation

### O00-001 — Stage00 retrospective canonical reconstruction

상태: **CLOSED — documentation/genealogy only**

`docs/stages/stage-00-research-contracts/`에 surviving Git/archive SHA 기반 retrospective provenance를 복원했다. 존재하지 않았던 historical contract/content는 만들지 않았다.

### O01-001 — Stage01 retrospective canonical reconstruction

상태: **CLOSED — documentation/genealogy only**

`docs/stages/stage-01-truth-execution-integrity/`에 v0.1/v0.2/Stage02 transition lineage를 복원했고 historical Stage02 PARTIAL handoff를 later PASS로 소급 재작성하지 않았다.

## Stage02 coverage

### O02-001 — independent clean-host reproduction

상태: **OPEN / external reproducibility gap**

현재 GitHub hosted Ubuntu 24.04.4 runner에서는 live nested-mount probe가 실제 uid 0으로 실행되어 다음을 확인했다.

- raw top-level rbind/remount-ro 아래 writable descendant가 존재함;
- descendant write로 source canary 변경 가능;
- Harness preflight는 nested read-only source를 실행 전에 차단함.

최신 통합 CI `31957540019`에서도 이 probe는 skip되지 않고 PASS했다. 그러나 이것은 **한 hosted runner 계열에서의 재현**이며, 별도의 clean VM/self-hosted runner에서 dependency provisioning부터 다시 수행한 independent reproduction을 대체하지 않는다.

### O02-002 — hosted namespace skip interpretation

상태: **OPEN limitation / current run did not skip**

향후 hosted environment가 privilege/mount namespace를 제공하지 않아 probe가 skip될 경우 그 skip을 production isolation PASS evidence로 계산하지 않는다. 최신 validated run에서는 실제 live probe가 수행됐다.

## Stage03 provenance

### O03-001 — immutable environment provenance breadth

상태: **PARTIAL / external environment coverage gap**

Exact CI dependency lock, build backend pin, source/lock/toolchain semantic identity, runner OS/image metadata와 manifest audit는 강화됐다. 그러나 모든 배포 환경의 immutable base image/container/VM recipe까지 end-to-end 고정했다고 주장하지 않는다.

향후 후보:

- exact OS/base image digest;
- container/VM recipe hash;
- sandbox/mount 관련 system package versions;
- independently provisioned runner provenance.

## Stage04 semantic verification

### O04-001 — real-world claim-class library

상태: **PARTIAL**

현재 frozen software semantic scope에는 다음 세 class가 구현/검증됐다.

- `software.build_result`;
- `software.test_result`;
- `software.behavioral_acceptance`.

최신 repository-style execution corpus에서도 이 세 class를 실제 subprocess/pytest/CLI artifact로 검증했다.

아직 별도 contract가 필요한 범위:

- `software.security_property`;
- CTF exploit primitive / service behavior / remote acceptance;
- broader hackathon domain semantics.

새 class는 기존 verifier에 이름만 추가하지 않고 evidence form, verifier, authority, negative cases를 별도로 freeze해야 한다.

### O04-002 — repository-style verifier benchmark

상태: **CLOSED for frozen 17-case corpus / broad generalization OPEN**

`stage4-repository-execution-semantics-v1`에서 17 cases를 실행했다.

```text
true positives  = 5
true negatives  = 12
false positives = 0
false negatives = 0
```

Positive classes는 build/test/behavioral acceptance 세 종류다. Tampered evidence, unregistered evidence, free-form semantic masquerade, unknown security-property class 등 negative cases도 포함된다.

이 결과는 frozen corpus에서 mechanism을 검증한 것이며 arbitrary repository/security/CTF semantics에 대한 universal FP/FN=0 주장은 아니다.

## Stage05 Recovery effectiveness

### O05-001 — Recovery A/B effectiveness

상태: **PARTIAL — controlled deterministic benchmark PASS; broad real-world effectiveness OPEN**

동결된 matched A/B benchmark에서 production Recovery는 recoverable scenario 3/3을 완료했고 conservative no-automatic-recovery baseline은 0/3을 완료했다. Completion-rate delta `+1.0`, terminal safety regressions `0`, unsafe retries `0`이었다. 추가 비용은 recovered success당 평균 `+2.3333` persisted steps, `+1.3333` task tool calls였다.

남은 검증:

- 실제 repository/CTF/hackathon task corpus;
- 실제 LLM/controller variability;
- stochastic seeds와 통계적 효과;
- model-token/latency 비용.

따라서 “controlled benchmark에서 positive causal utility”만 닫고 general effectiveness는 닫지 않는다.

## Stage06 semantic progress

### O06-001 — task/world progress authority

상태: **CLOSED for mechanism / domain-specific milestone coverage OPEN**

`DomainProfile.task_progress_snapshot()`을 추가했다. Default profile은 `None`으로 authority가 없으며, opt-in profile만 deterministic `milestones + score` schema를 제공한다.

Kernel은 monotonic milestone addition / score increase만 TASK progress credit으로 인정한다. Milestone removal, score decrease, arbitrary churn, snapshot hook의 durable-state mutation, authority availability toggle은 progress로 인정하지 않거나 fail closed한다.

최신 direct probe `task-world-progress-v2`에서:

```text
implicit_task_authority = 0
regressions_credited = 0
snapshot_state_mutations_accepted = 0
```

Residual: software/CTF/hackathon profile이 어떤 milestone/score를 domain truth로 선언할지는 별도 empirical contract/benchmark가 필요하다.

## Stage07 context governance

### O07-001 — oversized mandatory goal/control inputs

상태: **CLOSED for current in-memory GoalContract / long-contract externalization unsupported**

GoalContract 생성 시 다음 limit을 초과하면 fail closed한다.

- goal 16,000 chars;
- acceptance/constraints/pinned 각각 최대 64 items;
- criterion당 4,000 chars;
- mandatory text aggregate 64,000 chars;
- task_id 256 chars.

Projection에서 silent truncation하지 않는다. Direct probe `mandatory-goal-bounds-v1`에서 5/5 cases PASS, silent truncations 0.

Residual: 이 limit을 넘는 매우 긴 task contract를 content-addressed external representation으로 안전하게 지원하는 기능은 아직 없다.

## Stage08 residual operations / future provider scope

### O08-003 — unreferenced retrieval artifact GC

상태: **OPEN / operational, non-authoritative**

Stage08 batch는 HarnessState 측에서 atomic하다. 중간 preparation 실패 시 state/retrieval/artifact-reference/evidence-reference는 부분 commit되지 않는다. 다만 content-addressed physical file이 이미 생성된 뒤 후속 preparation이 실패하면 unreferenced file이 disk에 남을 수 있다.

이 file은 state가 참조하지 않아 truth/context authority는 없지만 disk를 차지할 수 있다. 단순 rollback delete는 동일 content-addressed file이 다른 live state에서 공유될 가능성 때문에 안전하지 않다. Global live-reference inventory를 가진 conservative orphan GC가 향후 운영 개선점이다.

### O08-004 — remote provider proof contract

상태: **OPEN / future-provider requirement**

v0.9.0은 shipped local lexical provider를 검증한다. Future remote provider는 stable descriptor 선언만으로 hidden mutation/honesty를 증명했다고 간주하지 말고 provider-specific provenance/replay proof가 필요하다.

## Remediation documentation

### ODOC-001 — future fixes must use this directory

상태: **ONGOING RULE**

앞으로 기존 Stage 보장을 수정하는 모든 작업은 `docs/remediation/` 아래에 finding/evidence/action/validation/residual record를 남긴다. Canonical Stage 문서는 그 결과를 참조할 수 있지만 과거 결과를 조용히 덮어쓰지 않는다.
