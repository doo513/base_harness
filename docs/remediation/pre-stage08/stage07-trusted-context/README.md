# Stage07 remediation — Bounded Trusted Context and Mandatory Goal Inputs

Finding ID: `R07-CONTEXT-001`  
Status: **PASS for trusted-fact projection and current in-memory mandatory GoalContract bounds**

## 문제 1 — verified trusted state growth

기존 Context Governor는 hypotheses, observations, failures, tool descriptions 등은 bounded했지만 current verified facts를 거의 전체 dump하여 다음 경로가 존재했다.

```text
verified state growth
→ model-visible trusted payload growth
→ prompt/context expansion
```

해결 과정에서 durable verified truth 자체를 삭제하거나 임의 요약해서는 안 되므로 **truth storage와 model projection을 분리**했다.

## 조치 1 — trusted-fact projection bound

ContextPolicy에 다음 bound를 추가했다.

- maximum visible verified fact count;
- per verified value character bound;
- total verified value character bound;
- verified key character bound;
- superseded key list bound.

큰 value는 bounded preview + stable content hash + evidence metadata로 표현하며 durable `HarnessState.facts`는 context 절감을 위해 삭제하거나 변형하지 않는다. 선택 순서도 deterministic하게 유지한다.

기존 Stage07 base/adversarial/resume/compat probe와 trusted-context growth/cost probe를 함께 유지한다.

## 문제 2 — mandatory goal/control 자체의 무제한 growth

후속 재검토에서 trusted facts만 bound해도 `goal`, `acceptance`, `constraints`, `pinned_constraints` 자체가 비정상적으로 크면 model-visible mandatory control payload가 무제한 증가할 수 있음을 확인했다.

이 필드는 의미를 조용히 truncate하면 계약 자체가 바뀌므로 projection에서 자르지 않고 **GoalContract 생성 시 fail closed** 하도록 했다.

## 조치 2 — entry-time GoalContract limits

현재 `GoalContract`는 `__post_init__()`에서 즉시 검증하며 다음 limits를 가진다.

```text
max goal chars                  = 16,000
max criteria items / field      = 64
max chars / criterion           = 4,000
max total mandatory chars       = 64,000
max task_id chars               = 256
overflow mode                   = fail_closed_before_run_creation
schema                          = goal-contract-limits-v1
```

검증 대상은:

- goal;
- acceptance;
- constraints;
- pinned_constraints;
- task_id.

Oversized value를 잘라서 실행하지 않고 contract construction 자체를 거부한다. 따라서 Actor/model은 일부만 보존된 goal을 정상 contract로 오인하지 않는다.

## Evidence

기존 trusted-context evidence:

- trusted-context growth probe;
- trusted-context cost probe;
- base/adversarial/resume/compat probes.

새 evidence:

- `tests/test_stage7_goal_contract_bounds.py`;
- `scripts/stage7_goal_contract_bounds_probe.py` (`mandatory-goal-bounds-v1`).

최종 검증 HEAD `d72f7e9b468702fb2a787870278e4008919acabb`, CI `31957540019`에서:

```text
Full pytest: 205 passed / 5 skipped
Stage07 base/adversarial/resume/compat: PASS
trusted-context growth/cost: PASS
mandatory goal bounds: PASS
scenario_count = 5
silent_truncations = 0
```

같은 CI에서 trusted-context cost probe는 200개의 durable fact를 대상으로 raw verified-fact serialized chars `1,037,090` 대비 bounded full context `7,660` chars를 기록했다. 이 값은 token count가 아니라 serialized-character proxy다.

## 현재 주장 가능한 범위

- durable verified truth를 삭제하지 않고 model-visible trusted-fact projection을 bound한다.
- mandatory GoalContract text는 entry-time limit을 넘으면 fail closed한다.
- oversized mandatory semantics를 silent truncation하지 않는다.
- existing Stage07 compatibility와 resume determinism을 유지한다.

## 잔여 한계

현재 정책은 지나치게 큰 장문 goal을 **지원하지 않고 거부**한다. Content-addressed external representation을 통해 매우 긴 task contract를 안전하게 참조하는 기능은 아직 없다.

또한 `metadata` 전체를 mandatory prompt-control text로 취급하는 것은 아니므로 이번 GoalContract text bound의 직접 대상이 아니다. 향후 metadata가 model-visible control authority를 갖게 된다면 별도 schema/bound가 필요하다.
