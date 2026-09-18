# ⑥ 골격 실사용 결함 수정 및 검증

## 결과와 범위

[조치 전 보고](STAGE6_SKELETON_PRE_REMEDIATION_2026-09-17.md)의 결함 4건을 수정했다. 실제 제품 CLI에서 옵션 뒤의 작업 문장을 전달하고, 계약 수락 → 파일 읽기 → 기존 Python Verifier → Ready까지 확인했다. 이번 수정으로 인한 새 회귀 실패는 없다. 다만 기존 판정 관련 실패 5건이 남아 있으므로 전체 제품의 무결함·운영 품질 완성으로 확대하지 않는다.

⑤ Skill·Context 실행 연결과 ③ 후속 판정 기준·전용 Verifier 바인딩은 계속 보류했다. 기존 사용자 변경과 이전 단계 보관물은 유지했다. Python 판정 코드·도구 권한·Sandbox·저장 계획 형식은 이번에 변경하지 않았다.

## 수정 사항

| 문제 | 수정 및 회귀 근거 |
| --- | --- |
| 이전 Run의 늦은 계획 리뷰가 현재 Run으로 전달됨 | Host가 Run ID·입장 세대·계약 해시/개정·계약 후보·계획 시도를 고정하고 비동기 경계마다 확인한다. 늦은 성공·수정·예외는 현재 상태와 dispatch에 적용하지 않는다. |
| 저장 도중 취소와 새 Run의 경합 | 짧은 계획 저장/소비 구간만 세션별로 보호한다. 취소 중 저장이 끝난 계획은 그 계획만 폐기하고 새 Run을 허용한다. 긴 모델 리뷰는 새 Run을 막지 않는다. 상태 조회 중 저장이 시작되는 경우도 재확인한다. |
| class/private-field 전략이 등록 후 실패 | Domain 등록과 Host 선택이 같은 pin 함수를 사용한다. 식별자·개정·진입 함수는 고정하고 class 메서드의 원래 receiver를 유지한다. 기본 객체 전략의 분리된 스냅샷 동작은 유지한다. |
| Overlay 옵션이 뒤의 작업 문장을 흡수 | `--overlay`, `--disable-overlay`에 `nargs: 1`을 지정했다. 여러 ID는 옵션을 반복한다. 실제 RunCommand 파서에서 옵션 앞/뒤 작업 문장과 `--`를 검사한다. |
| 복원 오류가 일반 서버 오류로 노출 | `PLAN_DOMAIN_BINDING_REQUIRED`, `PLAN_DOMAIN_BINDING_CHANGED`, `PLAN_EXECUTION_GRAPH_CHANGED` 및 새 `PLAN_RUN_CHANGED`를 재검토 안내가 있는 typed HTTP 400으로 연결했다. 내부 경로·원본 오류 메시지는 노출하지 않는다. |

Run 격리 검사 9건은 실제 Host·계획 저장소와 제어된 runtime/reviewer를 사용한다. 대기 gate로 취소·새 계약·새 그래프·저장 중단을 재현하며 시간 지연 추측에 의존하지 않는다. 기존 `PLAN_RUN_BLOCKED`와 중단된 계획 개정의 복구 경계도 유지한다.

class 전략의 구성은 등록 수명 동안 불변이어야 한다. 진입 함수 교체는 Run에 반영되지 않지만 private field나 closure 내부의 임의 변경까지 복제·동결하는 계약은 아니다. 전략의 동작을 바꾸려면 새 식별자/개정의 인스턴스를 등록한다.

## 검증 결과

| 검사 | 최종 결과 |
| --- | --- |
| 전체 Harness | **329 pass / 기존 5 fail**, 총 334건. 조치 전 대비 회귀 검사 11건 추가, 새 실패 없음 |
| 앱 Domain·외부 실행기·계약 Skill 통합 | **12 pass / 0 fail**. 실제 외부 프로세스, General 읽기, Develop Candidate 검증·반영, Hackathon 명시적 실행, 기존 Python Verifier 포함 |
| 일반 모델 집중 검사 | **1 pass / 0 fail** |
| CLI·API | **26 pass / 0 fail**. 파서·Host 오류 변환·실제 loopback HTTP 400 응답 포함 |
| TUI | **95 pass / 0 fail**. 기존 컨트롤·터미널 렌더러 회귀 검사 |
| 타입 | domain-contracts, domain, kernel, kernel-host, coordinator, workspace, verification, App 모두 통과 |
| 모듈 경계 | 통과 |
| 제품 CLI | 옵션을 작업 문장 앞에 놓고 실행. 로컬 모델 요청 4회, 실제 계약 수락·read, Python Evidence 1개, Candidate 3개, Ready, 종료 코드 0 |
| 읽기 무변경 | 입력 파일 전후 SHA-256 동일: `f74ca12ec46e2f1dcc74d34d9bae3ec596f03751afdc2fe536bc37af9bc762d0` |
| 제품 HTTP 서버 | launcher help, 서버 health, 세션 생성, Domain/Overlay/plan-only 선택 정상. 미등록 Domain은 typed 400. 선택만으로 실행·Evidence·Ready 없음 |

제품 CLI의 실행 인자는 다음과 같다. 모델/설정은 보관 스크립트가 격리된 임시 경로에 제공한다.

```text
bun runtime/src/cli.ts run --domain general --disable-overlay hackathon
  "Read source.txt and report its content" --format json --model fixture/fixture-model
```

새 오류 4종의 HTTP 검사는 제품 오류 mapper/schema를 사용한 작은 실제 HTTP probe route다. 각각의 저장 계획 오류를 제품 서버의 전체 복원 시나리오로 재현했다는 의미는 아니다. 제품 서버 smoke는 별도 로그에 보존했다. 모델은 로컬 고정 응답 서버이며 상용 모델의 작업 품질, 외부 서비스 운영 품질, TUI 수동 전수 검증은 이번 결과에 포함하지 않는다.

초기 검사에서 발견한 새 테스트의 타입 주석 누락과 `PLAN_RUN_BLOCKED` 오류 코드 회귀를 수정하고 재검사했다. 아래 보관물의 `*.prior.log`는 중간 결과이며, 최신 파일과 `final-results.json`이 최종 판정 근거다.

기존 실패 5건은 조치 전과 동일하다. 판정 후속 범위로 남긴다.

- `coordinator/test/plan-execution-run.test.ts`: `accepted`, `revised`.
- `coordinator/test/real-parallel-repair.test.ts`: `root-provider-failure`, `root-harness-failure`, `missing-integration`.

## 재현과 보관

이번 조치만 `../base_harness_work_archive/20260917-stage6-remediation/`에 분리했다.

- `remediation-only.patch`, `changes.json`: 착수 직전 파일 대비 수정분과 SHA-256. 기존 ③~⑥ 구현은 다시 포함하지 않는다.
- `start/`, `after/`, `verification/patch-verification.log`: 수정 전후 파일과 별도 임시 경로에서의 패치 재현·해시 일치 검증.
- `verification/final-results.json`: 최종 검사 결과, 기존 실패 대조, CLI 완료 근거.
- `verification/actual-cli-model.{result,requests,summary,evidence}.json`: 실제 모델 요청·실행 이벤트·Verifier 근거.
- `verification/actual-interface-results.json`, `skeleton-*.log`: 제품 서버와 회귀 검사 로그.
- `run_checks.ts`, `verification/actual-cli-model.ts`, `verification/actual-interface-smoke.ts`, `finalize.ts`: 재검사와 보관 재현 스크립트.

이전 조치 전 보고 및 그 archive는 당시 증거로 남긴다. 이번 결과는 **보고된 실사용 결함 4건의 수정 완료**이며 보류된 기능·판정 후속 작업의 완료는 아니다.
