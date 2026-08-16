# 04 — Open Items

이 문서는 remediation이 현재 해결했다고 주장하지 않는 항목을 유지한다. Green CI가 존재한다는 이유로 research/validation gap을 닫지 않는다.

## Stage08 closed entry blockers

### O08-001 — Retrieval query ownership runtime

상태: **CLOSED for Stage08 frozen scope — v0.9.0**

확인된 경계:

- Actor-controlled field: explicit `query` text.
- Kernel-owned/validated: normalization, scope, top-k, provider/index identity, ranking policy, candidate admission, durable request identity, result/content/history bounds and context authority.
- provider/config/index identity is runtime-fingerprinted.
- query/search does not mutate the shipped local lexical store.
- admitted retrieval is only `untrusted_retrieval`, `instruction_authority=none`.
- retrieval is separate from facts/completion/recovery/progress and retrieval-only progress credit is 0.
- resume reproduces the durable snapshot and fails closed on provider/index drift.

Release evidence: commit `a5645fc9d059afd12088ee1c4751c0250c8a5206`, CI `31954492789`, Stage08 base 4/4, adversarial 6/6, resume 4/4.

Residual: semantic query planning from goal/unknown/failure state is not implemented and is not claimed by Stage08.

### O08-002 — Retrieval artifact admission

상태: **CLOSED for Stage08 authority/integrity scope — v0.9.0**

Implemented:

- content-addressed artifact storage;
- single-buffer verified read before admission and before current model-visible projection;
- candidate/source/provider/content identity binding;
- complete-batch preparation before live HarnessState-side retrieval/ref/metric commit;
- missing/tampered artifact resume fail-closed;
- storage `OSError` -> typed persistence failure.

Residual: a failed preparation may leave unreferenced physical content-addressed files. They have no HarnessState/truth/context authority, but later conservative orphan GC is an operational improvement.

## Stage00 / Stage01 documentation

### O00-001 — Stage00 retrospective canonical reconstruction

상태: **CLOSED — documentation/genealogy only**

조치:

- `docs/stages/stage-00-research-contracts/` canonical retrospective package 생성;
- initial Git commit, first explicit Stage02 research commit, archive artifact filename/SHA-256를 연결;
- 원본 archive bytes가 repo에 없다는 사실과 confidence boundary를 명시;
- 존재하지 않았던 historical `CONTRACT.md`나 내부 내용을 소급 생성하지 않음.

이 closure는 Stage00 mechanism을 새로 검증했다는 의미가 아니다.

### O01-001 — Stage01 retrospective canonical reconstruction

상태: **CLOSED — documentation/genealogy only**

조치:

- `docs/stages/stage-01-truth-execution-integrity/` canonical retrospective package 생성;
- `v0.1`, `v0.2 hardening`, Stage02 transition artifact의 보존 SHA를 lineage로 연결;
- Stage00/01의 독립 Git commit이 surviving history에 없음을 명시;
- historical Stage02 partial handoff를 later PASS로 소급 재작성하지 않음.

이 closure 역시 truth/execution-integrity mechanism의 신규 validation을 뜻하지 않는다.

## Stage02 coverage

### O02-001 — independent clean-host reproduction

상태: **OPEN / coverage gap**

현재 live host와 hosted CI의 namespace 조건은 충분한 독립 clean-host release reproduction과 동일하지 않다. 최소 한 번은 새 host/VM에서 dependency provisioning → release checkout → namespace/mount/backend attack probe를 독립 재현하고 host provenance를 저장해야 한다.

### O02-002 — hosted namespace skip interpretation

상태: **OPEN limitation**

hosted runner에서 privilege/mount namespace 제한으로 skip되는 live isolation case는 PASS evidence로 계산하지 않는다. unit/mocked result로 실제 kernel isolation evidence를 대체하지 않는다.

## Stage03 provenance

### O03-001 — immutable environment provenance breadth

상태: **PARTIAL / coverage gap**

현재 exact CI dependency lock, build backend pin, source/lock/toolchain semantic identity와 manifest audit는 강화되었다. 그러나 모든 배포 환경에서 immutable base image/container digest 또는 clean-host recipe digest까지 end-to-end로 고정했다는 주장은 하지 않는다.

향후 release-grade reproduction에서는 다음을 고려한다.

- exact OS/base image digest;
- container/VM recipe hash;
- system package versions relevant to sandbox/mount behavior;
- runner image identity의 immutable representation.

## Stage04 semantic verification

### O04-001 — real-world claim-class library

상태: **OPEN / coverage gap**

ClaimContractRegistry mechanism은 생겼지만 실제 software/CTF/hackathon task에서 필요한 다양한 semantic claim type이 충분히 구현·benchmark되었다는 의미는 아니다.

확장 후보:

- `software.build_result`;
- `software.test_result`;
- `software.behavioral_acceptance`;
- security property classes;
- CTF exploit primitive / remote acceptance classes.

각 class는 “어떤 evidence가 어떤 authority까지 허용하는가”를 별도 contract로 가져야 한다.

### O04-002 — real-world verifier benchmark

상태: **OPEN**

현재 synthetic semantic matrix 8/8 FP=0/FN=0는 mechanism probe다. 실제 repository/task corpus에서 false positive/false negative를 측정하는 benchmark가 필요하다.

## Stage05 Recovery effectiveness

### O05-001 — Recovery A/B benchmark

상태: **OPEN**

현재 증명된 것:

- recovery transition durability;
- resume ordering;
- unsafe retry block;
- terminal escalation semantics.

현재 증명되지 않은 것:

- Recovery enabled가 disabled 대비 실제 task success rate를 올리는가;
- latency/tool cost를 감안해도 효과가 있는가.

동일 task/model/budget seed군에서 recovery ON/OFF 비교가 필요하다.

## Stage06 semantic progress

### O06-001 — task/world progress authority

상태: **OPEN / deliberate non-goal of current hardening**

현재 credit이 있는 deterministic progress는 verified fact transition 중심이다. 하지만 verified fact 증가도 goal과 무관할 수 있다.

향후에는 profile/oracle이 명시적으로 정의하는 milestone을 고려해야 한다.

- acceptance requirement coverage 증가;
- verifier-backed goal claim coverage 증가;
- external task state transition;
- oracle milestone advancement.

LLM 서술만으로 semantic progress를 판정하는 방식은 현재 evidence-first 설계와 맞지 않으므로 기본 authority로 사용하지 않는다.

## Stage07 context governance

### O07-001 — oversized mandatory goal/control inputs

상태: **OPEN**

현재 hardening은 verified trusted facts의 model projection 팽창을 직접 제한했다. goal contract와 일부 mandatory control 구조 자체가 비정상적으로 거대할 때의 entry-time hard limit은 별도 문제다.

권장 방향:

- mandatory semantic content를 projection에서 임의 삭제하지 않음;
- task entry/contract validation에서 비정상 크기를 fail-closed하거나 content-addressed external representation을 사용.

## Stage08 residual operations / future provider scope

### O08-003 — unreferenced retrieval artifact GC

상태: **OPEN / operational, non-authoritative**

실패한 batch preparation이 만든 content-addressed 파일은 authoritative state/ref commit 전에 실패하면 unreferenced 상태로 남을 수 있다. truth/context authority는 없지만 디스크 공간을 차지하므로 conservative orphan inventory/GC가 향후 개선점이다.

### O08-004 — remote provider proof contract

상태: **OPEN / future-provider requirement**

v0.9.0은 shipped local lexical provider의 deterministic/read-only contract를 직접 검증한다. 향후 remote provider를 추가할 경우 stable descriptor 선언만으로 hidden mutation/honesty를 증명했다고 간주하지 말고 provider-specific provenance/replay proof를 추가해야 한다.

## Remediation documentation

### ODOC-001 — future fixes must use this directory

상태: **ONGOING RULE**

앞으로 기존 Stage의 보장을 수정하는 모든 작업은 `docs/remediation/` 아래에 finding/evidence/action/validation/residual record를 남긴다. canonical Stage 문서는 그 결과를 참조할 수 있지만 과거 결과를 조용히 덮어쓰지 않는다.
