# ⑥까지의 시스템 골격 — 실사용 검증 및 조치 전 보고

## 현재 판정

General·Develop·Hackathon의 기본 실행, 계획 저장·복원, CLI·API·TUI 선택 인터페이스를 연결했다. 실제 제품 CLI에서 계약 수락 → 파일 읽기 → Python 검증 → Ready까지 완료했다. 다만 Run 격리 문제 1건과 이번 ⑥ 변경의 문제 3건을 확인했으므로 **전체 구조에 이상이 없다는 판정은 보류**한다. 아래 발견 사항은 사용자 요청대로 수정하지 않았다.

⑤ Skill·Context 실행 연결과 ③ 후속 판정 기준·전용 Verifier 바인딩은 보류했다. ⑤에서 작성 중이던 앱 주입 코드와 로더는 복구 가능한 보관본으로 분리하고, 타입·참조 메타데이터만 유지했다. 기존 GoalContract 작성·리뷰 Skill 연결은 유지한다.

## 구현된 골격

```text
CLI / API / TUI
    → Host: 등록된 Domain·Overlay 선택, 계약·계획 gate
    → Run별 준비·제안 전략 및 실행 어댑터 바인딩
    → Coordinator: General 직접 결과 / Develop·Hackathon WorkGraph
    → 실제 도구·Candidate·기존 Python Verifier
    → 검증된 Evidence·Ready

저장 계획 조회 → 수동 복원 표시 → 명시적 execute
    → Domain·정책·전략 개정 일치 검사 → 새 실행 Run
```

- `DomainRegistry.resolve()`는 메타데이터 조회를 담당하고 실행 모듈은 별도로 등록한다.
- Hackathon은 Develop에 조합되는 Overlay이며, 계획 작성만으로 worker나 파일 변경을 시작하지 않는다.
- 저장 계획에는 `plan-domain-binding-v1` 검토 근거를 추가했다. Domain·정책·전략·Overlay·Skill 참조를 보존하며, 새 필드에 실행기 옵션·자격 증명·실행 콜백·Ready를 저장하지 않는다.
- 복원 시 실행 바인딩은 비워 두고, 명시적 실행 때 현재 등록과 저장된 근거를 비교한다. 정책·전략 개정이 다르면 계획을 소비하거나 Run을 열기 전에 거절한다.
- 실행 전 제안 재검사가 검토된 WorkGraph를 바꾸면 `PLAN_EXECUTION_GRAPH_CHANGED`로 거절한다. 새 Run handoff 후에도 같은 그래프를 다시 확인한다.
- 기존 저장 형식 `reviewed-plan-v1`은 유지한다. 바인딩 근거가 없는 예전 계획은 조회·폐기는 가능하지만 실행에는 새 검토가 필요하다.
- CLI `--domain`, `--overlay`, `--disable-overlay`, 기존 `--hackathon`과 TUI `/domain`, `/overlay`를 연결했다. API·SDK는 문자열 ID를 받고 Host가 실제 등록을 확인한다.
- TUI의 대기 중 선택은 새 세션에만 적용된다. API 거절 시 초기화를 중단하고 재시도할 선택을 보존한다.

## 실제 사용과 검사 결과

| 검사 | 확인된 결과 |
| --- | --- |
| 제품 CLI + 로컬 모델 서버 | 실제 `runtime/src/cli.ts run` 실행, 모델 요청 4회, 계약 수락, 실제 `read`, Python 검증, 종료 코드 0 |
| CLI 완료 근거 | `readyEligible=true`, Evidence 1개, Candidate 3개. Evidence는 `verifier_observed`, `verified=true`, `file/content_contains` |
| 읽기 무변경 | 입력 파일 SHA-256 전후 동일: `f74ca12ec46e2f1dcc74d34d9bae3ec596f03751afdc2fe536bc37af9bc762d0` |
| 실제 HTTP 서버 | 세션 생성·Domain/Overlay 선택·plan-only 설정 200, 미등록 Domain은 typed 400. 선택만으로 Run·Evidence·Ready 생성 없음 |
| 앱 실행 통합 | 12 pass / 0 fail. 제어된 외부 프로세스, General 읽기, Develop Candidate commit, Hackathon 명시적 실행과 실제 Python Verifier 포함 |
| 일반 모델 루프 집중 검사 | 1 pass / 0 fail. 계약 수락 뒤 후보 데이터만으로 Evidence가 생성되지 않음 |
| 전체 Harness | **318 pass / 기존 5 fail**, 총 323건. 기존 테스트 묶음에 새 실패 없음 |
| CLI·API / TUI | 각각 **15 pass / 95 pass**, 실패 없음. TUI는 컨트롤·실제 터미널 렌더러 검사이며 수동 UI 전수 검사는 아님 |
| 타입 검사 | domain-contracts, domain, kernel, kernel-host, coordinator, workspace, verification, App, TUI, SDK 통과 |
| 모듈 경계 | 통과 |

실사용은 상용 모델 없이 로컬 고정 응답 서버, 격리된 임시 작업 디렉터리, 실제 파일 도구와 Python Verifier로 수행했다. 모델의 작업 품질이나 외부 서비스 운영 품질을 검증했다는 의미는 아니다. Develop/Hackathon worker는 제어된 앱 통합 fixture를 사용했다.

초기 샌드박스 검사는 기본 상태 디렉터리 쓰기 및 loopback listen 제한으로 실패했다. 해당 로그를 보존한 뒤 임시 상태 디렉터리와 허용된 로컬 통신으로 재검사했다. 최종 표에는 재검사 결과를 사용했다. CLI의 첫 55초 제한 실행은 모델 호출 전에 종료되었고, 상세 추적 재실행은 프로세스 시작 후 약 65.6초에 provider 초기화, 67.4초에 정상 종료했다. 이 콜드 스타트 시간은 별도 성능 관찰값이며 원인을 단정하거나 최적화하지 않았다.

기존 실패 5건은 다음과 같다. 판정 정책 후속 범위이므로 이번에 수정하지 않았다.

- `coordinator/test/plan-execution-run.test.ts`: `accepted`, `revised`.
- `coordinator/test/real-parallel-repair.test.ts`: `root-provider-failure`, `root-harness-failure`, `missing-integration`.

## 발견 사항 — 조치하지 않음

### 1. P1: 취소된 Run의 계획 검토 결과가 새 Run에 전달됨 — 기존 문제

`kernel-host/src/index.ts`의 `acceptNormalizedWorkGraph()`는 검토를 기다리는 동안 세션 레코드를 공유하고, 반환 뒤 현재 `record.runId`로 그래프를 전달한다. `review()`도 반환 결과를 적용할 때 시작 Run을 다시 확인하지 않는다.

재현: run-1의 계획 리뷰 대기 → 취소 → 같은 세션에서 run-2 및 계약 수락 → run-1 리뷰 반환. 결과는 `runId: run-2`에 `OLD RUN INSTRUCTION`이 전달되는 것이었다. 현재 코드와 ⑥ 착수 전 Host 양쪽에서 재현했다. 실제 Host·계획 저장소와 제어된 Coordinator/reviewer로 확인했으며, 실사용 CLI에서 재현한 것으로 확대하지 않는다.

조치 방향: 검토 시작 시 Run·계약·계획 식별자를 고정하고 비동기 경계마다 유효성을 검사하여 과거 결과를 버려야 한다. 복구·저장·dispatch 경계 전체에 같은 검사를 적용해야 한다.

### 2. P2: class 형태의 교체형 전략이 깨짐 — ⑥ 신규 문제

`domain/src/execution.ts`의 등록 스냅샷은 메서드의 `this`를 새 객체로 바꾼다. private field를 읽는 정상 전략은 `Cannot access invalid private field`로 실패한다. Host `selectedExecution()`의 객체 spread는 class prototype의 `prepare()`·`normalize()`를 복사하지 않아 메서드가 사라질 수도 있다.

등록 전에는 동작하는 전략이 현재 등록·Host 경로에서 실패하고, ⑥ 이전 구현에서는 같은 두 예제가 통과하는 것을 확인했다. 기본 객체 전략은 통과하지만 “전략 교체 가능” 조건에는 결함이 남는다.

조치 방향: 호출 참조 고정과 전략의 receiver 보존을 함께 만족하는 등록 계약을 정하고 class/private-field 회귀 검사를 추가해야 한다.

### 3. P2: CLI Overlay 옵션이 작업 문장을 흡수함 — ⑥ 신규 문제

`base-harness/src/cli/cmd/run.ts`의 배열 옵션에 한 번당 값 개수가 지정되지 않았다. 실제 `RunCommand` 파서로 `run --overlay hackathon "Build the demo"`를 해석하면 `overlay=["hackathon", "Build the demo"]`, `message=[]`가 된다. `--disable-overlay`도 같다.

작업 문장을 먼저 두거나 `--`로 구분하면 의도가 보존된다. 후속 조치에서는 반복 가능한 옵션의 각 값 개수를 고정하고 실제 argv 파싱을 검사해야 한다.

### 4. P2: 새 복원 오류의 API 매핑 누락 — ⑥ 신규 문제

`base-harness/src/server/routes/instance/httpapi/handlers/session-errors.ts`에 `PLAN_DOMAIN_BINDING_REQUIRED`, `PLAN_DOMAIN_BINDING_CHANGED`, `PLAN_EXECUTION_GRAPH_CHANGED`가 없다. 실제 오류 변환기에 세 코드를 넣으면 typed rejection이 만들어지지 않고, 기존 `PLAN_STALE`은 정상 변환된다.

서버의 일반 오류 경로로 넘어가 HTTP 500 및 불충분한 안내가 될 수 있다는 결론은 오류 경계 코드에 근거한다. 저장 계획을 통한 실제 HTTP 500 재현까지 했다는 의미는 아니다. 후속으로 public 오류 매핑과 재검토 안내를 연결해야 한다.

## 보관과 다음 판단

⑥ 전용 패치·변경 목록·착수 전/후 파일·실행 로그·재현 스크립트는 `../base_harness_work_archive/20260917-stage6-restoration-interfaces/`에 있다. `verification/actual-cli-model.summary.json`과 `actual-cli-model.evidence.json`이 실제 CLI 완료의 핵심 근거다. `review-*.log`, `actual-cli-parser-probe.json`, `expected-error-probe.json`에는 위 결함의 재현 근거가 있다.

⑤ 보류 코드는 `../base_harness_work_archive/20260917-stage5-skills-context/deferred-work/`에 보존했다. 앱에서 제거한 신규 로더 파일 2개도 해시와 함께 복구 가능하다. 남겨 둔 scaffold는 별도 11파일 패치로 재현 검증했다. ④ 보관물은 기존 전용 archive를 유지한다.

이번 인계는 **골격 구현 + 실사용 검증 + 조치 전 결함 보고**다. 다음 조치는 P1 Run 격리, P2 전략 호환, CLI 파싱, API 오류 매핑 순서가 적절하다. 현재 보고 단계에서 해당 수정은 적용하지 않았다.
