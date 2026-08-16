# Stage06 remediation — Activity, Epistemic, and Task/World Progress

Finding ID: `R06-PROGRESS-001`  
Status: **PASS for implemented progress-authority mechanism; profile/domain coverage remains bounded**

## 문제

초기 Stage06는 verified fact change와 novel successful observation content를 모두 progress authority로 사용했다. 하지만 새 bytes가 생겼다는 사실은 goal을 향해 진전했다는 뜻이 아니다. timestamp/nonce/counter처럼 매번 달라지는 output은 task state를 개선하지 않으면서 no-progress horizon을 계속 reset할 수 있었다.

## 1차 remediation — activity와 epistemic progress 분리

새 contract는 다음과 같다.

```text
Activity Novelty
- 새 successful observation content
- artifact integrity verification 필요
- progress credit = 0
- no-progress reset 권한 없음

Epistemic Progress
- verified fact semantic content transition
- progress credit = 1
- no-progress reset 가능
```

구현 과정에서 기존 test/probe가 `first novel observation = progress`를 전제로 하고 있어 두 번 red가 발생했다.

- CI `31950606445`: `147 passed / 5 skipped / 1 failed`
- CI `31950681824`: full pytest는 `148 passed / 5 skipped`, Stage06 strategy direct probe FAIL

production rule을 과거 의미로 되돌리지 않고 stale test/probe oracle을 activity/epistemic contract에 맞춰 migration했다. 최종 CI `31950847647`에서 green이 됐다.

## 2차 remediation — explicit task/world progress authority

후속 전체 구조 재검토에서 verified fact 증가도 goal과 무관할 수 있다는 한계가 남아 있음을 확인했다. 이를 해결하기 위해 `DomainProfile.task_progress_snapshot()`이라는 명시적 profile-owned extension point를 추가했다.

기본 profile은 `None`을 반환하며 **task/world progress authority를 전혀 갖지 않는다.** Opt-in profile만 다음 deterministic schema를 제공할 수 있다.

```text
{
  "milestones": [unique stable strings...],
  "score": finite non-negative number
}
```

Kernel은 다음 조건에서만 TASK progress credit 1을 부여한다.

- 기존 milestone이 제거되지 않은 상태에서 새 milestone이 추가됨;
- 기존 score가 감소하지 않은 상태에서 score가 증가함.

다음은 progress가 아니다.

- milestone 제거;
- score 감소;
- arbitrary snapshot churn;
- Actor prose;
- retrieval content;
- default profile의 state 변화.

또한 hook은 durable `HarnessState`에 대해 pure해야 한다. 호출 전후 state hash가 달라지면 `IntegrityError`로 fail closed한다. snapshot schema는 deterministic JSON이어야 하고 milestone 수/길이와 전체 serialized byte 크기를 제한한다.

## 구조 재검토에서 발견한 추가 오류와 수정

첫 task/world 구현 candidate는 deterministic snapshot의 **hash가 달라지기만 하면 progress**로 판단했다. 이 candidate는 CI가 green이었지만, 재검토에서 다음 구조 오류를 발견했다.

```text
milestone A -> milestone 없음
score 10 -> 2
```

도 단순 hash change이므로 progress로 오인될 수 있었다.

Green CI를 완료 근거로 사용하지 않고 contract를 monotonic milestone/score advancement로 좁혔다. regression은 `progress.task_regression`으로 기록하되 credit 0으로 처리한다. 한 transition 중 task-progress authority가 `None <-> object`로 토글되는 경우도 fail closed한다.

## Evidence

새 unit tests는 다음을 검증한다.

- profile-explicit monotonic advance만 task progress;
- default profile에는 task authority 없음;
- milestone regression은 progress가 아님;
- score 감소는 progress가 아님;
- snapshot hook의 durable-state mutation 차단;
- unsupported schema 차단;
- milestone bound;
- authority availability toggle 차단.

Direct probe: `scripts/stage6_task_world_progress_probe.py` (`task-world-progress-v2`).

최종 검증 HEAD `d72f7e9b468702fb2a787870278e4008919acabb`, CI `31957540019`에서:

```text
Full pytest: 205 passed / 5 skipped
Stage06 base/adversarial/resume/boundary/strategy: PASS
Stage06 task-world progress probe: PASS
implicit_task_authority = 0
regressions_credited = 0
snapshot_state_mutations_accepted = 0
```

## 현재 주장 가능한 범위

- novel activity는 progress authority가 아니다.
- verified fact semantic transition은 epistemic progress로 구분된다.
- profile이 명시적으로 제공한 deterministic monotonic milestone/score advance만 task/world progress authority를 갖는다.
- task regression/churn은 no-progress horizon을 reset하지 않는다.
- arbitrary LLM semantic judge는 progress authority가 아니다.

## 잔여 한계

이 mechanism은 **goal-distance를 자동 추론하지 않는다.** built-in profile마다 실제 어떤 milestone/score가 domain상 올바른지는 별도 profile contract와 benchmark가 필요하다. 즉 mechanism은 닫혔지만 software/CTF/hackathon별 task-progress semantics의 empirical coverage까지 증명한 것은 아니다.
