# Stage06 remediation — Activity Novelty vs Semantic Progress

Finding ID: `R06-PROGRESS-001`  
Status: **PASS for activity / epistemic boundary**

## 문제

기존 Stage06는 다음 두 신호를 progress authority로 사용했다.

- verified fact content change
- novel integrity-checked successful observation content

두 번째는 replay/duplicate loop를 줄이는 데 유용하지만 **새롭다는 사실과 goal을 향해 진전했다는 사실은 다르다.**

예를 들어 tool이 매 호출마다 timestamp/nonce/counter를 다르게 반환하면 모든 output bytes는 새롭지만 task state는 전혀 개선되지 않을 수 있다. 기존 rule에서는 이런 activity가 no-progress streak를 reset할 수 있었다.

## 새 contract

```text
Activity Novelty
- new successful observation bytes/content
- integrity verification 필요
- 기록/진단에는 사용
- progress credit = 0
- no-progress reset 권한 없음

Epistemic Progress
- verified fact semantic content transition
- progress credit = 1
- no-progress reset 가능

Task / World Progress
- 향후 profile/oracle가 evidence-backed milestone로 선언
- 현재 remediation에서는 임의 LLM semantic judge를 추가하지 않음
```

## 구현

main semantic split: `f6bfc6e...`

- observation artifact fingerprinting과 tamper detection은 유지.
- novel fingerprints는 `activity_reasons`로 기록.
- `made_progress`는 credit-bearing reason에서만 true.
- verified fact hash는 evidence-ref metadata churn을 제외하고 value/status/authority semantic content를 기준으로 유지.
- recovery transition, speculative churn, failed observation은 계속 progress가 아님.

## Contract migration 과정

이번 변경은 production code만 바꾸면 기존 test oracle이 green일 수 없는 **의도적 semantic contract 변경**이었다.

### Candidate 1 — CI `31950606445`

```text
147 passed / 5 skipped / 1 failed
```

실패한 unit test는 `첫 novel successful observation = progress`를 기대했다. 새 보장을 되돌리지 않고 test의 의미를 다음처럼 교정했다.

```text
first novel observation = activity only
same evidence after strategy switch = activity only
verified fact transition = actual epistemic progress
```

commit: `7350770...`.

### Candidate 2 — CI `31950681824`

full pytest:

```text
148 passed / 5 skipped
```

그러나 별도 Stage06 strategy direct probe가 같은 legacy assumption을 보유해 FAIL했다. direct probe도 test와 동일하게 **oracle 자체를 새 contract로 migration**했다.

commit: `8aaf70a...`.

### Final — CI `31950847647`

전체 workflow SUCCESS.

Stage07 후속 변경이 올라간 최종 integration CI `31950971636`에서도 Stage06 base/adversarial/resume/boundary/strategy probes가 모두 SUCCESS였다.

## Direct evidence

semantic progress probe에서:

```text
novel volatile outputs:
  activity_events = 3
  progress_events = 0
  no_progress_failures = 1

verified fact delta:
  epistemic_events = 1
  max_credit = 1.0
```

따라서 “새 output을 계속 만들면 no-progress를 무기한 회피”하는 기존 조건은 제거되었다.

## 잔여 한계

verified fact 증가도 goal과 무관할 수 있다. 따라서 현재 Stage06가 **완전한 semantic task progress**를 해결했다고 주장하지 않는다.

향후에는 profile/oracle이 acceptance coverage, verified goal claim, external task state transition 같은 evidence-backed task/world milestone을 제공하는 방향이 필요하다. `../04_OPEN_ITEMS.md` 참조.
