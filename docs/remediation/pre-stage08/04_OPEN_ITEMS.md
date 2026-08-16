# 04 — Open Items

이 문서는 remediation이 현재 해결했다고 주장하지 않는 항목을 유지한다. Green CI가 존재한다는 이유로 research/validation gap을 닫지 않는다.

## Stage08 closed entry blockers

### O08-001 — Retrieval query ownership runtime

상태: **CLOSED for Stage08 frozen scope — v0.9.0**

Actor-controlled field는 explicit `query` text이고, Kernel은 normalization, scope, top-k, provider/index identity, ranking policy, candidate admission, durable request identity, result/content/history bounds와 context authority를 소유/검증한다. Release evidence: `a5645fc9d059afd12088ee1c4751c0250c8a5206`, CI `31954492789`.

Residual: semantic query planning은 Stage08 범위가 아니다.

### O08-002 — Retrieval artifact admission

상태: **CLOSED for Stage08 authority/integrity scope — v0.9.0**

Content-addressed storage, single-buffer verified read, provider/source/content binding, batch state-side atomicity, tamper/missing resume fail-closed, storage I/O persistence routing이 구현됐다.

Residual: failed preparation의 unreferenced physical artifact는 operational GC 대상이다.

## Stage00 / Stage01 documentation

### O00-001 — Stage00 retrospective canonical reconstruction

상태: **CLOSED — documentation/genealogy only**

`docs/stages/stage-00-research-contracts/`에 surviving Git/archive SHA 기반 retrospective provenance를 복원했다. 존재하지 않았던 historical contract/content는 만들지 않았다.

### O01-001 — Stage01 retrospective canonical reconstruction

상태: **CLOSED — documentation/genealogy only**

`docs/stages/stage-01-truth-execution-integrity/`에 v0.1/v0.2/Stage02 transition lineage를 복원했고 historical Stage02 PARTIAL handoff를 later PASS로 소급 재작성하지 않았다.

## Stage02 coverage

### O02-001 — independent clean-host reproduction

상태: **OPEN / coverage gap**

새 host/VM에서 dependency provisioning → release checkout → namespace/mount/backend attack probe를 독립 재현하고 host provenance를 저장해야 한다.

### O02-002 — hosted namespace skip interpretation

상태: **OPEN limitation**

Hosted runner의 privilege/mount namespace skip은 production isolation PASS evidence로 계산하지 않는다.

## Stage03 provenance

### O03-001 — immutable environment provenance breadth

상태: **PARTIAL / coverage gap**

Exact CI dependency lock, build backend pin, source/lock/toolchain semantic identity와 manifest audit는 강화됐지만 모든 배포 환경의 immutable base image/container/VM recipe까지 end-to-end로 고정했다는 주장은 하지 않는다.

향후 후보: exact OS/base image digest, container/VM recipe hash, sandbox/mount 관련 system package versions, immutable runner identity.

## Stage04 semantic verification

### O04-001 — real-world claim-class library

상태: **OPEN / coverage gap**

ClaimContractRegistry mechanism은 있지만 실제 software/CTF/hackathon semantic claim type coverage는 부족하다.

확장 후보:

- `software.build_result`;
- `software.test_result`;
- `software.behavioral_acceptance`;
- `software.security_property`;
- CTF exploit primitive / remote acceptance classes.

각 class는 허용 evidence와 authority를 별도 contract로 가져야 한다.

### O04-002 — real-world verifier benchmark

상태: **OPEN**

현재 Stage04 synthetic semantic matrix 8/8 FP=0/FN=0는 mechanism probe다. 실제 실행/파일 artifact를 생성하는 repository-style corpus에서 false positive/false negative를 측정해야 한다.

## Stage05 Recovery effectiveness

### O05-001 — Recovery A/B effectiveness

상태: **PARTIAL — controlled deterministic benchmark PASS; broad real-world effectiveness OPEN**

동결된 matched A/B benchmark에서 production Recovery는 recoverable scenario 3/3을 완료했고 conservative no-automatic-recovery baseline은 0/3을 완료했다. Completion-rate delta `+1.0`, terminal safety regressions `0`, unsafe retries `0`이었다. 추가 비용은 recovered success당 평균 `+2.3333` persisted steps, `+1.3333` task tool calls였다.

Evidence: commit `1b8496c120f52496d53de90ef7aae013cc926962`, CI `31955531150`, full regression `182 passed / 5 skipped`.

남은 검증:

- 실제 repository/CTF/hackathon task corpus;
- 실제 LLM/controller variability;
- stochastic seeds와 통계적 효과;
- model-token/latency 비용.

따라서 “controlled benchmark에서 positive causal utility”만 닫고 general effectiveness는 닫지 않는다.

## Stage06 semantic progress

### O06-001 — task/world progress authority

상태: **OPEN / deliberate non-goal of current hardening**

현재 deterministic progress authority는 verified fact transition 중심이다. Verified fact 증가도 goal과 무관할 수 있으므로 profile/oracle이 명시하는 acceptance coverage, goal-bound claim coverage, external state transition, oracle milestone advancement 같은 task/world progress contract가 필요하다. LLM 서술만으로 semantic progress를 authority로 쓰지 않는다.

## Stage07 context governance

### O07-001 — oversized mandatory goal/control inputs

상태: **OPEN**

Verified trusted-fact projection은 bounded지만 goal contract/mandatory control 자체가 비정상적으로 큰 경우의 entry-time hard limit은 별도다. Mandatory semantics를 조용히 삭제하지 말고 task-entry validation에서 fail-closed하거나 content-addressed external representation을 사용해야 한다.

## Stage08 residual operations / future provider scope

### O08-003 — unreferenced retrieval artifact GC

상태: **OPEN / operational, non-authoritative**

실패한 batch preparation이 만든 unreferenced content-addressed files는 truth/context authority는 없지만 disk를 차지할 수 있다. Conservative orphan inventory/GC가 향후 개선점이다.

### O08-004 — remote provider proof contract

상태: **OPEN / future-provider requirement**

v0.9.0은 shipped local lexical provider를 검증한다. Future remote provider는 stable descriptor 선언만으로 hidden mutation/honesty를 증명했다고 간주하지 말고 provider-specific provenance/replay proof가 필요하다.

## Remediation documentation

### ODOC-001 — future fixes must use this directory

상태: **ONGOING RULE**

앞으로 기존 Stage 보장을 수정하는 모든 작업은 `docs/remediation/` 아래에 finding/evidence/action/validation/residual record를 남긴다. Canonical Stage 문서는 그 결과를 참조할 수 있지만 과거 결과를 조용히 덮어쓰지 않는다.
