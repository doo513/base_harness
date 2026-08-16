# 04 — Open Items

이 문서는 remediation이 현재 해결했다고 주장하지 않는 항목을 유지한다. Green CI가 존재한다는 이유로 research/validation gap을 닫지 않는다.

## P0 / Stage08 entry blockers

### O08-001 — Retrieval query ownership runtime

상태: **OPEN / required before Stage08 exit**

필요 조건:

- Actor가 제안할 수 있는 retrieval request와 Kernel이 소유하는 admitted query를 구분.
- query normalization, scope, top-k, per-step/request budget을 Kernel이 결정하거나 검증.
- provider/source/index revision을 config fingerprint에 포함.
- duplicate ID collision, source tamper, supersession, deterministic tie를 fail-closed 또는 명시적 policy로 처리.
- search/query 자체가 durable store를 mutation하지 않도록 pure retrieval semantics 확보.
- admitted candidate를 `untrusted_retrieval`, `instruction_authority=none`으로만 model context에 노출.
- retrieval output이 `facts`, completion, recovery, progress를 직접 바꾸지 못하게 구조적으로 분리.
- retrieval-only sequence가 Stage06 no-progress를 reset하지 않는 direct probe.
- checkpoint/resume 후 같은 state/query/config에서 동일 result를 재현.

### O08-002 — Retrieval artifact admission

상태: **OPEN**

Stage08 candidate가 artifact-backed content를 사용한다면 모든 content 소비는 current single-buffer verified-read primitive를 통과해야 한다. path verification을 admission authority로 재사용하지 않는다.

## Stage00 / Stage01 documentation

### O00-001 — Stage00 retrospective canonical reconstruction

상태: **OPEN**

과거 artifact index, commit, report를 근거로 canonical `docs/stages/stage-00-*` package를 복원해야 한다. 존재하지 않았던 contract/evidence를 소급해 만들어내면 안 된다. 당시 근거로 확인 가능한 내용과 retrospective 해석을 구분한다.

### O01-001 — Stage01 retrospective canonical reconstruction

상태: **OPEN**

초기 hardening 기록을 Stage01 canonical lineage로 정리하되 원본 SHA/commit provenance를 유지한다.

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

- exact OS/base image digest
- container/VM recipe hash
- system package versions relevant to sandbox/mount behavior
- runner image identity의 immutable representation

## Stage04 semantic verification

### O04-001 — real-world claim-class library

상태: **OPEN / coverage gap**

ClaimContractRegistry mechanism은 생겼지만 실제 software/CTF/hackathon task에서 필요한 다양한 semantic claim type이 충분히 구현·benchmark되었다는 의미는 아니다.

예상 확장 후보:

- software.build_result
- software.test_result
- software.behavioral_acceptance
- security property classes
- CTF exploit primitive / remote acceptance classes

각 class는 “어떤 evidence가 어떤 authority까지 허용하는가”를 별도 contract로 가져야 한다.

### O04-002 — real-world verifier benchmark

상태: **OPEN**

현재 synthetic semantic matrix 8/8 FP=0/FN=0는 mechanism probe다. 실제 repository/task corpus에서 false positive/false negative를 측정하는 benchmark가 필요하다.

## Stage05 Recovery effectiveness

### O05-001 — Recovery A/B benchmark

상태: **OPEN**

현재 증명된 것:

- recovery transition durability
- resume ordering
- unsafe retry block
- terminal escalation semantics

현재 증명되지 않은 것:

- Recovery enabled가 disabled 대비 실제 task success rate를 올리는가.
- latency/tool cost를 감안해도 효과가 있는가.

동일 task/model/budget seed군에서 recovery ON/OFF 비교가 필요하다.

## Stage06 semantic progress

### O06-001 — task/world progress authority

상태: **OPEN / deliberate non-goal of current hardening**

현재 credit이 있는 deterministic progress는 verified fact transition 중심이다. 하지만 verified fact 증가도 goal과 무관할 수 있다.

향후에는 profile/oracle이 명시적으로 정의하는 milestone을 고려해야 한다.

- acceptance requirement coverage 증가
- verifier-backed goal claim coverage 증가
- external task state transition
- oracle milestone advancement

LLM 서술만으로 semantic progress를 판정하는 방식은 현재 evidence-first 설계와 맞지 않으므로 기본 authority로 사용하지 않는다.

## Stage07 context governance

### O07-001 — oversized mandatory goal/control inputs

상태: **OPEN**

이번 hardening은 verified trusted facts의 model projection 팽창을 직접 제한했다. goal contract와 일부 mandatory control 구조 자체가 비정상적으로 거대할 때의 entry-time hard limit은 별도 문제다.

권장 방향:

- mandatory semantic content를 projection에서 임의 삭제하지 않음.
- task entry/contract validation에서 비정상 크기를 fail-closed하거나 content-addressed external representation을 사용.

## Remediation documentation

### ODOC-001 — future fixes must use this directory

상태: **ONGOING RULE**

앞으로 기존 Stage의 보장을 수정하는 모든 작업은 `docs/remediation/` 아래에 finding/evidence/action/validation/residual record를 남긴다. canonical Stage 문서는 그 결과를 참조할 수 있지만 과거 결과를 조용히 덮어쓰지 않는다.
