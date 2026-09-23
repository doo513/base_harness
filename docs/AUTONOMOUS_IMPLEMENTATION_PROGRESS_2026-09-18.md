# Autonomous M1–M5 구현·검증 기록

작성일: 2026-09-22

범위: `docs/AUTONOMOUS_DOMAIN_CORE_DESIGN_2026-09-18.md`의 M1–M5 및 수용 시나리오 A01–A33.

## 결론

`autonomous-v1`은 General·Develop의 새 일반 Run 기본값으로 제품 경로에 연결되었다. 직접 작업과 재귀 Task의 파일 변경은 동일한 Overlay·Candidate·apply 경계를 사용한다. CLI·HTTP·TUI에는 모델 판단, 실제 관측, gate, 런타임 종료 사유와 Candidate 상태를 분리한 `autonomous-product-result-v1`이 전달된다. `kernel.executionSemantics: "legacy"`는 기존 GoalContract·Python v4 Evidence/Ready 의미와 저장 기록을 유지한다.

모델의 `satisfied`는 모델 판단이며 Ready가 아니다. Python v5 측정은 사실만 반환한다. 새 기본 경로는 자동 repair나 두 번째 agent loop를 만들지 않는다.

## M4-A — 변경 격리와 반영

- `write`, `edit`, `apply_patch`, shell `mutation: "capture"`는 Workspace Overlay에 기록되고 sealed Candidate를 생성한다.
- update·move·delete를 포함한 Candidate는 원본 workspace를 적용 전까지 바꾸지 않는다.
- apply는 현재 AuthorityGrant revision, 정확한 Candidate/receipt, materialized bytes, baseline, 경로 scope와 명시적 gate를 재확인한다.
- 권한 축소는 Host가 기존 Permission ruleset을 다시 읽어 grant revision을 갱신하고 오래된 apply basis와 receipt를 무효화한다.
- 충돌은 사용자의 최신 바이트를 보존한다. publication/rollback 실패는 journal과 backup을 남기고 `recovery_required`·`runtime_fault`로 종료한다.
- Verifier는 검사 전 `tests/__init__.py`를 만들지 않는다. legacy Candidate 삭제의 null afterHash도 독립적으로 검사한다.

## M4-B — 재귀 Task와 공유 자원

- `delegate`와 `amend_tasks(add|replace_pending|cancel)`가 Coordinator의 현재 AutonomousRun에서 실행된다.
- 자식은 부모 이하의 capability/scope만 사용하고 같은 budgetId, deadline, maxActions를 공유한다.
- maxParallelTasks, maxTaskDepth, maxTotalTasks와 DAG 조건 `settled|artifact_produced|applied`를 적용한다.
- 기존 앱 WorkerExecutor와 TaskTool을 재사용한다. 자식·손자 모델 호출은 각각 task basis/session에 고정되며 변경은 M4-A Candidate 경로로 들어간다.
- 취소, graph revision 충돌, 중복 decision, 늦은 결과, finish drain 중 Candidate 상태 변경을 격리한다.

## M5-A — 제품 결과와 복원

- 공통 `autonomous-product-result-v1`은 lifecycle, runtimeReason, assessment, observations, gates, candidates, unresolvedEffects를 별도 필드로 제공한다.
- CLI는 요청된 satisfied를 0, 요청된 partial·unsolved·not_assessed를 2, runtime failure·cancel·interrupt를 1로 반환한다.
- HTTP Harness 5개 라우트에 coverage/auth/effect 시나리오가 추가되었고 Host status를 그대로 전달한다.
- TUI는 autonomous lifecycle, 모델 assessment, uncertainty, observation 수, gate, Candidate disposition과 unresolved effect를 표시한다.
- Host history는 legacy Ready의 원래 phase를 보존하고 autonomous history에는 별도 의미를 저장한다.
- 재시작 시 실행 중 Run은 interrupted history로만 표시하며 process, worker, permit, 외부 효과를 재실행하지 않는다.

## M5-B — 실행기와 기본값

- 로컬 model loop와 제어 가능한 외부 process가 같은 DecisionProposal/Host admission 경로를 사용한다.
- Codex app-server는 실제 model capability, autonomous-decision-v1 envelope 및 token usage를 보고한다.
- Antigravity built-in adapter는 제어 process 검사에서 capability와 token usage를 보고했다. 현재 로컬 AGY 설치는 인증/model discovery가 없어 실제 상용 호출은 `AGY_AUTH_REQUIRED`로 명시적으로 거절된다.
- 지원 capability가 없거나 revision이 오래된 외부 backend는 legacy로 fallback하지 않는다.
- 새 일반 Run 기본값은 autonomous-v1이다. plan-only·reviewed-plan 실행과 명시적 legacy 설정은 기존 경로를 유지한다.

## A01–A33 요구사항 추적

| ID | 상태 | 현재 증거 |
| --- | --- | --- |
| A01–A05 | 완료 | Prepare 자율성, strict schema/authority 주입 거절, 실패 관측 후 read 또는 partial finish 단위·통합 검사 |
| A06–A09 | 완료 | completed/fail·error·not_run 구분, model-authored check provenance, subject revision/gate, General source/report 분리 검사 |
| A10 | 완료 | 실제 로컬 자식→손자 model delegation과 손자 Candidate apply |
| A11–A12 | 완료 | 병렬 slot 경합과 전체 Run shared budget/maxTotalTasks 검사 |
| A13–A15 | 완료 | running replace 거절, decision replay/conflict, cancel/late/replacement Run 격리 |
| A16–A19 | 완료 | finish gate, ungated finish, plain not_assessed, child drain/cancel 검사 |
| A20 | 완료 | 실패 관측이 암묵 apply gate가 되지 않고 apply 가능 |
| A21 | 완료 | 명시적 failed apply gate는 적용 거절, Candidate retained, partial finish 허용 |
| A22 | 완료 | direct edit/write/apply_patch/shell과 child/grandchild가 동일 Candidate 경계 사용 |
| A23–A24 | 완료 | baseline/materialized tamper·사용자 충돌·measurement sandbox 범위 차단 |
| A25 | 완료 | legacy history Ready 의미와 autonomous history를 별도 보존 |
| A26 | 완료 | active v2 Run을 interrupted history로 복원하며 실행 재개 없음 |
| A27–A28 | 완료 | measurement service error 전달, cleanup 미확인 unresolvedEffects 기록 |
| A29 | 완료 | edit permission 축소 직후 stale apply와 current forbidden apply 모두 거절 |
| A30 | 완료 | 미지원 hard cap/backend capability를 명시 오류로 반환 |
| A31 | 완료 | apply 진행 중 finish drain은 Candidate state 변화 후 FINISH_BASIS_CHANGED |
| A32 | 완료 | cleanup timeout에서 applying Candidate를 recovery_required/runtime_fault로 기록 |
| A33 | 완료 | transaction rollback 실패 backup/journal 보존과 autonomous recovery_required 검사 |

## 최종 검증

| 검사 | 결과 |
| --- | --- |
| 설계 TypeScript | strict/noEmit 통과 |
| 관련 package typecheck | domain-contracts, domain, kernel, kernel-host, coordinator, workspace, verification, security, base-harness, tui 통과 |
| 모듈 경계 | `Harness module boundaries are valid.` |
| 전체 Harness | 465 pass, 0 fail, 2,799 assertions |
| 앱 Harness 통합 | 69 pass, 0 fail, 305 assertions — direct/child/grandchild, shell, external, Python measurement 포함 |
| Python legacy + v5 | 45 pass |
| Coordinator M4/M5 집중 | 45 pass |
| CLI 집중 | 7 pass |
| TUI 전체 | 297 pass, 1 skip, 0 fail |
| HTTP | coverage 213/213, auth 213/213; Harness effect 5/5 |
| 실제 Codex 제품 실행 | headless CLI → app-server → autonomous closed/not_assessed, token usage 18,681, exit 2 |
| Antigravity built-in 제어 process | capability/usage 1 pass |

전체 monorepo typecheck에는 기존 Core 2건(`ReadableStream` async iterator lib, `Headers.entries` lib) 오류가 남아 있다. 전체 HTTP Effect 213개 중 기존 비-Harness 시나리오 3건(auth file fixture 2, PTY expected status 1)이 실패한다. 이번 M4·M5 관련 package, Harness route, auth와 product 경로에서는 새 실패가 없다.

세부 명령과 결과는 `evidence/autonomous-m4-m5-final-20260922.txt`, 변경 범위는 `evidence/autonomous-m4-m5-change-manifest-20260922.txt`에 기록한다.
