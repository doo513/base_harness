# ③ General·Develop 실행 구조 구현 기록

## 결과

General·Develop의 준비 전략과 실행 제안 전략을 별도 실행 모듈로 등록하고, Host가 선택한 모듈·정책·실행기를 Coordinator Run에 고정하도록 연결했다. 일반 모델과 외부 실행기는 같은 Domain 실행 계약을 사용한다. General 결과는 읽기 전용 후보 데이터로 수집되고, Develop 변경은 기존 WorkGraph·Candidate·Python Verifier 경로를 통과한다.

이번 단계는 기존 `goal-contract-v2`, 질문·리뷰 정책, 계획 저장 형식, Python 판정 기준을 바꾸지 않는다. Domain 준비·제안·모델 출력에는 Evidence 또는 Ready 권한이 없다.

```text
앱 구성
  DomainRegistry (메타데이터 조회)
  DomainExecutionRegistry (General / Develop 실행 모듈)
  고정 Domain dispatcher (Run 바인딩으로 실행기 선택)
                     │
                     ▼
Host: 준비 → 제안 staging → GoalContract 수락 → 현재 계약으로 재검사
                     │
                     ▼
Coordinator: Run ID 검사 → 직접 실행 또는 기존 WorkGraph/Candidate 경로
                     │
                     ▼
기존 Python Verifier: Evidence와 Ready의 유일한 판정 경로
```

## 구현 내용

### 공통 포트와 등록

- `domain-contracts`에 준비 입력·결과, 직접 실행/WorkGraph 제안, 전략, 실행 모듈, Run 바인딩, dispatcher/result 타입을 추가했다.
- `WorkUnit`·`WorkGraph`의 소유 위치를 공통 계약 패키지로 옮겼고, 기존 workspace 공개 위치에서는 다시 내보내 호환성을 유지했다.
- 기존 `DomainRegistry.resolve()`는 정책·메타데이터의 순수 조회로 남겼다. 실행 모듈은 별도 `DomainExecutionRegistry`에 명시 등록하며, 미등록 Domain은 `DOMAIN_EXECUTION_MODULE_UNREGISTERED`로 실패한다.
- 앱 구성은 내장 General·Develop 실행 모듈과 하나의 고정 dispatcher를 한 번 등록한다. 세션별 콜백 교체는 허용하지 않는다.

### Host와 Run 바인딩

- Host는 Run을 열기 전에 Domain/Overlay 정책 스냅샷, 모듈·준비 전략·제안 전략의 ID와 개정, 실행기 선택을 준비한다.
- Coordinator가 발급한 Run ID를 바인딩에 결합하며 준비 결과와 함께 Run 상태에 보관한다.
- 실행 제안은 계약보다 먼저 staging할 수 있지만 질문 대기, 수정 대기, Runtime 거절, plan-only 직접 실행 상태에서는 dispatch하지 않는다.
- 계약이 수정·수락되면 보관한 제안을 현재 계약과 현재 Run 바인딩으로 다시 정상화한 뒤 전달한다.
- 저장 계획 실행은 기존 새 실행 Run handoff를 사용하며 동일한 전략·정책·실행기 선택을 새 Run ID에 다시 바인딩한다. 저장 형식과 복원 정책은 바꾸지 않았다.

### Coordinator 수명주기

- 직접 제안은 고정 dispatcher에 `sessionID`, `runId`, 취소 신호, 바인딩, 준비 결과를 전달한다.
- WorkGraph 제안은 기존 worker, Candidate materialization, 검증, commit, root 검증 경로를 그대로 사용한다.
- worker와 root integration 요청에도 Coordinator Run ID를 포함했다. 앱의 외부 worker/meta-review 호출은 이 ID를 실행기 요청에 전달한다.
- 취소되거나 새 Run으로 교체된 뒤 도착한 직접 실행 결과와 attached-model 결과는 현재 Run에 적용하지 않는다.
- Domain 결과는 후보 출력으로만 상태에 노출한다. 그 결과 자체는 `candidateRefs`, `evidenceRefs`, `readyEligible`을 변경하지 않는다.

### General과 Develop

| Domain | 준비/제안 동작 | 실행 경로 |
|---|---|---|
| General | 읽기·검색·조사 지침, mutation 금지, 직접 결과만 허용 | attached 모델 또는 읽기 전용 외부 dispatcher; WorkGraph와 `writeSet` 불필요 |
| Develop | 계약 범위의 직접 실행 또는 검증된 WorkGraph 정상화 | attached 모델의 기존 도구 경로, 또는 기존 worker·Candidate·commit 경로 |

외부 Develop의 직접 mutation은 Candidate 경계가 없으므로 명시적으로 거절한다. 파일 변경은 WorkGraph로 보내야 한다. 기존 외부 root integration 미지원도 `EXTERNAL_ROOT_INTEGRATION_UNSUPPORTED`로 유지했다.

### 앱 실행 어댑터

- 세션 모델 경로는 준비 지침을 실제 모델 요청에 포함하고, 최종 assistant 텍스트를 현재 Run의 후보 결과로 기록한다.
- 외부 경로는 먼저 읽기 전용 계약 작성 호출을 실행하고 제안을 staging한 뒤 계약을 제출한다.
- General 외부 응답은 계약만 요구한다. WorkGraph나 비어 있지 않은 `writeSet`을 요구하지 않으며, 계약 수락 후 별도 읽기 전용 실행 호출을 한다.
- Develop 외부 응답은 기존 제약을 만족하는 WorkGraph를 요구하고 기존 worker 실행기로 전달한다.
- 모든 외부 계획·직접 실행·worker·meta-review 호출에 가능한 Run ID를 전달한다.

## 검증 결과

| 검사 | 결과 |
|---|---|
| Domain/Host/Coordinator 신규 단위 검사 | 전략 교체, 계약 대기·거절, plan-only, 동시 세션, 고정 dispatcher, 취소 후 지연 결과 격리 통과 |
| 실제 앱 통합 3건 | 제어된 외부 프로세스, General 읽기/무변경, Develop Candidate 검증·commit 모두 통과 |
| 외부 계약·Skill 관련 검사 | 11 pass / 0 fail |
| 로컬 모델 서버 General 실행 | 1 pass / 0 fail; 준비 지침 전달, 계약 수락, 후보 결과 기록 확인 |
| 외부 meta-review Run ID | 1 pass / 0 fail |
| 최종 `test:harness` | **302 pass / 5 fail**, 총 307건; 착수 기준선과 같은 5건만 실패 |
| CLI·TUI 회귀 | **52 pass / 0 fail** |
| 타입 검사 | domain-contracts, domain, kernel, kernel-host, verification, coordinator, workspace, tui 통과 |
| App 타입 검사 | 착수 시점과 동일한 CLI 오류 3건만 유지 |
| 모듈 경계·frozen lockfile | 통과 |

실제 통합 검사는 `python3 -m harness.verified_sidecar`를 사용했다. General은 기존 파일을 읽은 뒤 검증 전 `evidenceCount=0`, `readyEligible=false`임을 확인하고, 명시적 Python 검증이 실제 파일을 관찰한 뒤에만 Ready가 되는 것을 확인했다. Develop은 격리된 Candidate에 `result.txt`를 작성하고 scope 검증·attestation·commit·root 검증을 거쳐 Ready가 되며, 읽기 입력 파일은 바뀌지 않았다.

제어된 외부 실행기 검사는 별도 Bun 프로세스를 실제 작업 디렉터리에서 실행했다. Run ID와 `research` phase 전달, 결과 수집, 원본 파일 SHA-256 불변을 확인했다. 상용 모델이나 외부 서비스의 작업 품질을 검증한 결과는 아니다.

기존 실패 5건은 다음과 같으며 이번 변경 전 기준선과 동일하다.

- `coordinator/test/plan-execution-run.test.ts`: `accepted`, `revised` 2건.
- `coordinator/test/real-parallel-repair.test.ts`: `root-provider-failure`, `root-harness-failure`, `missing-integration` 3건.

기존 App 타입 오류 3건도 그대로다. `src/cli/cmd/run.ts` 316행의 `planId` 2건과 930행의 `executionBackend` 1건이다.

## 변경 위치

- 공통 계약: `runtime/packages/domain-contracts/src/{domain,execution,goal-contract,index}.ts`
- Domain 실행 전략: `runtime/packages/domain/src/execution.ts`
- 공통 WorkGraph 재수출: `runtime/packages/workspace/src/orchestration.ts`
- Host/Coordinator: `runtime/packages/kernel-host/src/index.ts`, `runtime/packages/coordinator/src/{contracts,index}.ts`
- 앱 어댑터: `runtime/packages/base-harness/src/harness/{coordinator-service,domain-execution,external-execution}.ts`
- 모델·worker 연결: `runtime/packages/base-harness/src/session/prompt.ts`, `runtime/packages/base-harness/src/tool/task.ts`
- 신규 검증: 각 패키지의 `domain-execution.test.ts`와 앱 `domain-execution-integration.test.ts`

③ 전용 변경 목록, 패치, 최종 파일, 검사 로그와 호출 연결 증거는 `../base_harness_work_archive/20260917-stage3-domain-execution/`에 보관한다.

## 후속 범위

- Domain별 판정 기준 보정과 전용 Verifier 등록·바인딩은 후속 단계다.
- Hackathon 전용 실행 조합, 범용 Skill·Context 확장, 저장 계획 형식·재시작 복원 정책 변경은 시작하지 않았다.
- 기존 root integration 실패 5건은 별도 결함으로 남긴다.
