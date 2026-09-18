# ② GoalContract 처리 구조

2026-09-17. ②-A → ②-B → ②-C → ②-D → ②-E 순서로 구현하고 각 구간을 검사했다. 기존 `goal-contract-v2`, 저장된 계획 형식, Python Verifier의 Evidence·Ready 권한을 유지한다. 이번 변경의 기준은 작업 시작 시점의 작업 트리이며, Git HEAD나 과거 일괄 구현이 아니다.

## 구현

| 구간 | 결과 | 주요 파일 |
|---|---|---|
| ②-A | 계약 본문, 모델 해석, 구조 검사 결과, Host 질문·답변 맥락을 공통 타입으로 분리. 기존 Kernel·Verifier 공개 타입은 재수출 | `domain-contracts/src/goal-contract.ts`, `verification/src/types.ts` |
| ②-B | 복사·호환 변환·정책 스냅샷을 Prepare에 모으고, 명시적 관계 수집과 구조 검사를 Scan·Validate/Dedupe로 분리 | `kernel/src/contract/` |
| ②-C | `ContractReviewPolicy` 포트와 기존 판단을 보존한 기본 정책을 분리하고 Host 생성자로 주입 | `kernel/src/contract/review-policy.ts`, `kernel-host/src/index.ts` |
| ②-D | 질문, 수정, 오류, Runtime 수락을 별개 상태로 관리. 제출 이력 캐시 대신 현재 Host·Run의 계약 상태를 확인 | `kernel-host/src/contract-questions.ts`, `base-harness/src/harness/contract-questions.ts`, `base-harness/src/tool/harness-contract-state.ts` |
| ②-E | 도메인 소유 Markdown 2개를 기존 Skill 서비스·번들·권한 경로로 읽어 실제 작성·리뷰 요청에 전달 | `domain/resources/goal-contract-{authoring,review}/SKILL.md`, `base-harness/src/skill/contract-builtins.ts`, `base-harness/src/harness/contract-skill.ts` |

표의 파일 경로는 `runtime/packages/` 기준이다.

Prepare는 제출 값을 복사하고 기존 evidence-family 별칭, 생략 가능한 exclusions, 도메인의 기본 criterion template을 정규화한다. Scan은 ID·참조·위험도·외부 영향·applicability 등 명시적 사실만 수집한다. Validate/Dedupe는 필수 내용, ID 중복, 양방향 연결, 미등록 대상을 검사한다. 진단을 합칠 때 경로·출처·영향 대상을 보존하며 요구사항 문장의 유사도로 항목을 합치지 않는다. 세 구간에는 모델 호출, 파일 접근, Host 상태 변경, 실행 권한 부여가 없다.

기본 리뷰 정책은 기존 불확실성 분류, 위험도, strict, 외부 영향, applicability, 필수 Claim·Criterion 수에 따른 판단과 우선순위를 유지한다. 정책 결과는 진행·리뷰·질문에 관한 조언이며, 구조 검사 결과도 실행 수락이 아니다. 리뷰 호출 한도는 기존 2회다. Domain Registry 조회에 실행 콜백을 추가하지 않았다.

## 상태와 권한

- `needs_input`은 질문 대기이며, 해결되지 않은 `revise`는 `revision_required`/`contract_building`으로 남는다. 형식 오류·리뷰어 장애·Question 서비스 장애는 실패 경로로 전달한다.
- 리뷰가 수정 후보를 반환하면 전체 후보를 다시 Prepare·Scan·Validate하고 정책을 적용한다. `pass`가 있어도 Runtime의 계약 수락을 거친다. 대기·거절·재검사 상태에서는 mutation을 허용하지 않는다.
- Host가 발급한 질문 묶음 ID를 세션, Run, 후보 개정, 내용 해시, 이슈 ID에 연결한다. 실제 Question 서비스 응답만 내부 기록 함수에 전달한다. 모델 제출 타입에는 답변 신뢰 상태나 수락·실행 권한 필드가 없다.
- 한 묶음은 최대 3개다. 남은 이슈와 부분 답변을 유지한다. 취소·빈 답변·오래된 개정·다른 Run·취소 뒤 늦은 답변은 해결이나 승인으로 기록하지 않는다. 질문의 선택지 문자열은 권한 판단에 사용하지 않는다.
- 답변을 모두 받으면 수정 후보가 필요하다. 이후 리뷰에는 같은 Run에서 Host가 기록한 이전 질문·답변과 개정 연결 정보를 복사하여 제공한다. 이 기록은 새 Run에서 초기화되며 재시작 후 승인 근거로 복원하지 않는다.
- 일반 계약 도구와 외부 계약 작성 경로는 같은 Question 어댑터를 사용한다. 외부 경로의 질문·수정 대기는 수락 실패 예외로 바뀌지 않으며 WorkGraph 실행을 시작하지 않는다.
- 도구의 기존 정책 검사와 실제 도구 진입점의 계약 수락 검사를 구별한다. `hasAcceptedContract`는 현재 Run에 수락된 계약이 있는지를 나타낸다. 종료·취소·작업자·Sandbox 실행 차단은 기존 Coordinator 경로가 집행한다. Kernel의 완료 검사 허용과 Runtime 실행 가능 여부를 혼동하지 않는다.
- 상태 조회는 Host 내부 객체의 복사본을 반환한다. 새 후보 제출 시 이전 preflight 허용을 즉시 철회한다. 저장된 계획을 읽을 때 preflight를 복사하여 재검사가 저장 원본을 변경하지 않게 했다. 저장 형식과 복원 정책은 그대로다.

## Skill 호출 연결

| 요청 | 실제 전달 위치 | 검증 |
|---|---|---|
| 일반 모델 계약 작성 | `SessionPrompt.runLoop`의 `system` | 로컬 테스트 모델 서버가 받은 HTTP 요청에 작성 본문 포함 |
| 외부 실행기 계약 작성 | `requestPlanning`의 JSON `instructions` | `ExecutionBackends.execute` 인자와 재시도 요청에서 본문 확인 |
| 일반 모델 메타리뷰 | Task의 Host 등록 reviewer가 만든 JSON `instructions` | 실제 reviewer 디스패치가 `promptOps.prompt`에 전달한 인자 확인 |
| 외부 실행기 메타리뷰 | 같은 reviewer JSON의 `instructions` | `ExecutionBackends.execute`의 `meta_review` 요청 인자 확인 |

프로젝트 Skill 재정의와 에이전트·세션 권한 규칙을 적용한다. 필수 본문이 없거나 비어 있으면 `CONTRACT_SKILL_UNAVAILABLE`, 권한 거부는 `CONTRACT_SKILL_DENIED`로 실패한다. 숨겨 둔 자연어 대체 지침은 없다. 출력 스키마, 프로토콜, mutation 금지, 상태 전이는 코드에 남는다. 권한을 허용하라는 지침으로 본문을 바꾸어도 출력 스키마·쓰기 차단·Evidence·Ready 상태가 바뀌지 않는 것을 검사했다.

두 Markdown은 Bun의 기존 text import 방식으로 번들에 포함된다. 번들 결과에서 두 본문을 다시 읽고 본문 해시를 기록했다. 호출 검증은 로컬 테스트 서버와 제어된 실행기 응답을 사용했다. 실제 상용 모델의 의미 판단 품질이나 외부 실행기 전체 수행을 검증한 결과는 아니다.

## 검증 결과

| 검사 | 결과 |
|---|---|
| ②-A 완료 시 | 109건 + Verifier 25건 통과, 관련 4개 패키지 타입 통과 |
| ②-B 완료 시 | 121건 통과, Kernel·Host 타입 및 모듈 경계 통과 |
| ②-C 완료 시 | 124건 통과, Kernel·Host 타입 통과 |
| ②-D 완료 시 | 142건 통과, 실제 Question 서비스 2건 및 실제 Python 계약 검사 2건 통과 |
| 최종 `test:harness` | **295 pass / 5 fail**, 총 300건; 실패 집합은 시작 시점과 동일 |
| 계약·Task·질문·외부 계약 검사 | **42 pass / 0 fail** |
| 일반 작성 모델 요청 검사 | **1 pass / 0 fail**, 나머지 59건은 필터됨 |
| 기존 Skill·발견·시스템 컨텍스트 회귀 | **30 pass / 0 fail** |
| CLI·TUI 회귀 | **52 pass / 0 fail** |
| 타입 검사 | domain-contracts, domain, kernel, kernel-host, verification, coordinator, tui 통과 |
| App 타입 검사 | 시작 시점과 동일한 오류 3건 |
| 모듈 경계 | 통과 |
| Skill 형식·번들 본문 | 2개 모두 통과 |

실제 `harness.verified_sidecar` Python 프로세스로 유효 계약 수락과 미등록 verifier 계약 거절을 검사했다. 두 경우 모두 계약 검사만으로 Evidence·Ready가 생성되지 않으며 검증 실행 호출도 발생하지 않는다.

기존 Harness 실패 5건은 다음과 같다.

- `plan-execution-run.test.ts`: 독립 실행 Run 검사 `accepted`, `revised` 2건.
- `real-parallel-repair.test.ts`: `missing-integration`, `root-harness-failure`, `root-provider-failure` 3건.

기존 App 타입 오류는 `src/cli/cmd/run.ts`의 316행 `planId` 2건과 930행 `executionBackend` 1건이다. 이들 때문에 전체 검사를 전부 성공으로 표시하지 않는다.

추가로 실행한 기존 Task 권한 검사 1건은 미등록 `reviewer`를 사용하는 테스트 입력 때문에 작업 시작 시점 원본에서도 실패했다. 보관 원본을 읽는 별도 테스트 실행으로 이를 재현했다. 테스트의 권한 검증을 유지하면서 기존 Domain이 허용하는 `build`를 subagent 모드로 구성하여 검사 전제가 맞도록 수정했다.

## 보관물과 범위

보관 위치: `../base_harness_work_archive/20260917-stage2-goal-contract/` (`base_harness` 저장소 루트 기준).

- `stage2-only.patch`: 시작 시점 파일 대비 이번 ② 변경만 포함.
- `changes.json`, `after/`: 변경 파일 목록과 변경 전후 해시, 최종 파일 사본.
- `checks/`: 단계별·최종 검사 로그, 기준선 대조 결과, Skill 호출 연결 증거와 번들 본문 해시.
- `README.md`: 재현 명령과 로그 안내.

Domain 실행 전체, 범용 Skill·Context 확장, 저장된 계획 복원 정책 변경, 재시작 후 답변의 권한 복원은 구현 범위에 포함하지 않았다. ③ 이후 구간은 시작하지 않았다.
