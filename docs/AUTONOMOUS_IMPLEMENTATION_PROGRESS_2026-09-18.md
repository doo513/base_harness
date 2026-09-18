# Autonomous M1–M3 구현·검증 기록

작성일: 2026-09-18

범위: [핵심 설계](AUTONOMOUS_DOMAIN_CORE_DESIGN_2026-09-18.md)의 M1 공통 계약·admission, M2 관측 프로토콜, M3 Domain/LLM 판단·종료 연결.

## 결론

**M1–M3는 명시적 `autonomous-v1` 경로로 구현했고 실제 로컬 모델, 제어 가능한 외부 실행기, ToolRegistry/Sandbox, Python 측정기, 질문·취소·동시 Run 및 전체 Harness 회귀를 통과했다.** 기본 실행 의미는 계속 legacy다. M4의 mutation·재귀 Task·Candidate 반영과 M5의 제품 기본값·전용 UI·복원 정책은 시작하지 않았다.

이 경로에서 `satisfied`는 Domain/LLM의 판단일 뿐 Evidence·Ready가 아니다. v5 Python 측정기는 관측 사실만 만들고 repair나 다음 행동을 지시하지 않는다. 기존 v4 Python Verifier와 `readyEligible` 권한은 legacy 경로에 그대로 남아 있다.

## 구현 결과

| 묶음 | 완료한 구조 | 강제 경계 |
| --- | --- | --- |
| M1 계약·admission | Intent, WorkingInterpretation, AuthorityGrant, DecisionBasis/Proposal, CheckSpec, ObservationReport, CompletionRecord, Run snapshot/port를 공통 패키지에 배치 | strict JSON allowlist, Run/Task/revision/subject/check/effect 바인딩, 권한 scope·제외, 명시적 gate, 원자적 누적 예산·중복 요청 검사 |
| M2 관측 | 별도 Python `measurement_v5`/sidecar와 인증된 TypeScript client, 실제 snapshot 파일 및 앱이 실행한 command capture 측정 | v4 fallback 없음, Ready/repair 필드 거절, request/run/task/subject/check/environment/producer/executor 일치, symlink·hardlink·경로 탈출·변경 바이트 차단, 응답 손상 시 runtime fault |
| M3 판단·종료 | General/Develop의 교체 가능한 Prepare/normalize 전략, Host artifact/provenance, Coordinator lifecycle, 기존 모델 loop와 외부 backend protocol, 질문 서비스, 실제 native tool adapter | Prepare 대기 중 실행 금지, 모델/외부 응답은 제안, strategy 입력 불변·분리, Run별 backend/basis 고정, late result 격리, deadline/budget/cancel/drain/cleanup/persistence fault 기록 |

### 실제 호출 연결

```text
SessionPrompt
  ├─ explicit autonomous-v1 → KernelHost.openAutonomousRun
  │    ├─ registered Domain.prepare → basis-bound preparation.context
  │    ├─ app Permission → Host-issued AuthorityGrant
  │    └─ Coordinator-owned AutonomousRun/Budget
  ├─ local provider turn ─┐
  └─ external backend ────┴─ DecisionProposal
                               ↓
                         Kernel admission
                               ↓
                  ToolRegistry + Sandbox / Python v5
                               ↓
                   observation or execution feedback
                               ↓
                     same Domain/LLM loop or finish
```

- 새 agent loop, 전역 세션 원장, 별도 권한 저장소를 만들지 않았다.
- Domain `prepare().context`를 현재 basis와 함께 snapshot에 저장해 실제 모델·외부 요청에 전달한다.
- 로컬 모델에는 현재 권한으로 실제 실행 가능한 `read/glob/grep/bash`만 광고한다. native tool→operation 표는 private code-owned map이며 외부에서 mutation 도구를 추가할 수 없다. `bash`는 앱 정책과 Permission이 execute를 허용한 Run에만 보인다.
- 내부 Skill과 legacy GoalContract authoring/review Skill은 autonomous loop에서 주입하지 않는다. 사용할 수 없는 MCP 지침도 넣지 않는다.
- 외부 backend는 `autonomous-decision-v1`과 `reported-v1`을 명시해야 한다. 등록 ID를 다른 객체로 교체할 수 없고 등록 객체·선택 옵션은 고정한다. 기존 backend들은 이 capability를 선언하지 않으므로 자동 fallback하지 않는다.
- plain text에 `ready`, `verified`, `success` 같은 단어가 있어도 `not_assessed`로 저장한다. 제어는 문자열 탐지가 아니라 스키마와 admission으로 결정한다.
- command 검사는 Python이 임의 subprocess를 띄우지 않는다. 앱의 기존 bash/Sandbox가 실행한 capture를 Python이 request와 대조해 관측한다.
- 응답 schema/binding 손상은 측정 client를 latch하고 Run을 `runtime_fault`로 닫는다. 측정 프로세스 일시 종료·서비스 부재는 관측 가능한 실행 실패 피드백으로 남겨 partial 종료나 다른 조사 선택을 막지 않는다.
- 닫힌 Run, 교체된 Run, 오래된 basis, 취소 뒤 도착한 모델·도구·질문 결과는 현재 결과에 적용하지 않는다. 불완전 provider 정산은 별도로 표시한다.

## 최종 검증

아래 수치는 최종 소스 기준이다. 실제 sidecar/프로세스가 필요한 검사는 로컬 통제 프로세스를 사용했고 상용 모델 품질 평가는 포함하지 않았다.

| 검사 | 결과 |
| --- | --- |
| 설계 타입 예시 | strict/noEmit 통과 |
| 관련 패키지 타입 검사 | domain-contracts, kernel, domain, coordinator, verification, kernel-host, base-harness, tui 통과 |
| 모듈 경계 | `Harness module boundaries are valid.` |
| 전체 Harness | 441 pass, 0 fail, 2675 assertions, 59 files |
| 앱 M3 통합 | 23 pass, 0 fail, 106 assertions — 로컬 모델, 외부 backend, 실제 tool/Sandbox, 질문, facade, execution context |
| Python legacy + v5 | 43 pass |
| CLI 관련 회귀 | 11 pass, 0 fail, 62 assertions |
| TUI 관련 회귀 | 95 pass, 0 fail, 392 assertions |

세부 명령과 최종 test/assertion 수는 [검증 로그](../evidence/autonomous-m1-m3-final-20260918.txt), 범위별 파일은 [변경 목록](../evidence/autonomous-m1-m3-change-manifest-20260918.txt)에 보관한다.

검증 환경을 잘못 선택한 시도는 통과로 계수하지 않았다. Coordinator 검사는 `XDG_STATE_HOME`이 읽기 전용 기본 경로를 가리키면 EROFS가 발생하므로 격리된 `/tmp` 상태 경로로 재실행했다. TUI TSX 검사는 monorepo root가 아니라 패키지 cwd에서 JSX runtime을 해석하며 그 명령으로 통과했다. 기존 전체 config 검사에서 확인된 프로젝트 `$schema` 자동 삽입 기대 불일치와 sandbox 내부 local-listen 제약은 이 범위의 코드로 숨기거나 수정하지 않았다.

## 변경 영역

- `runtime/packages/domain-contracts`: autonomous wire/runtime 계약
- `runtime/packages/kernel`: strict schema, admission, authority·gate 검사
- `runtime/packages/domain`: General/Develop 기본 전략과 pinning
- `runtime/packages/coordinator`: Run budget/lifecycle/measurement ownership, v2 persistence
- `runtime/packages/verification`, `src/harness`: v5 observation client·Python engine/sidecar
- `runtime/packages/kernel-host`: source/report/check provenance, strategy와 basis 고정, 질문/사용자 revision
- `runtime/packages/base-harness`: 앱 구성, local/external turn, native tool/Sandbox, config opt-in, CLI settlement
- 관련 단위·통합·회귀 테스트와 이 문서/검증 로그

기존 사용자 변경과 legacy GoalContract/Verifier 경로는 되돌리거나 정리하지 않았다.

## 의도적으로 남긴 범위

### M4

- Develop의 workspace mutation, direct/worker 공통 Overlay/Candidate 생성과 apply
- recursive Task/delegate, WorkGraph 개정, 전체 Run 예산을 공유하는 child scheduler
- Candidate integrity receipt, apply gate, publication/rollback/recovery 연결
- 실행 중 사용자 권한 축소·확대를 위한 grant revision/permit 재발급

현재 autonomous 경로의 `mutate`, `publish`, `delegate`, nested task/compaction은 명시적 unsupported다. bash가 허용되어도 Sandbox 밖 workspace를 변경하지 못한다.

### M5

- autonomous 상태를 model assessment/observations/runtime termination으로 나누는 전용 CLI/HTTP/TUI 표현
- headless autonomous 종료의 제품 exit-code 정책. 현재는 legacy Ready가 없으므로 보수적으로 nonzero다.
- 기본값 전환, 저장 호환성·재시작 표시 정책, AGENTS.md 권한 문구 전환
- 기본 외부 backend의 autonomous capability 구현과 상용 모델 품질 평가

### 후속 Verifier 설계

도메인별 판정 기준, 전용 Verifier 등록·바인딩, 관측의 충분성을 평가하는 제품 정책은 이번 범위에서 고치지 않았다. 이것은 M1–M3의 facts-only v5 경로 위에서 별도로 설계한다.
