# ④ Hackathon Overlay 구현 기록

## 결과

Hackathon을 별도 Domain으로 복제하지 않고 Develop 실행 모듈에 조합되는 실행 Overlay로 연결했다. Overlay 메타데이터, 준비 전략, 제안 전략의 식별자와 개정은 Run 바인딩에 고정되며, 미등록 실행 Overlay는 Run을 열기 전에 실패한다.

이번 구간은 기존 Python Verifier의 판정 기준이나 전용 Verifier 등록을 바꾸지 않는다. Hackathon 지침과 WorkGraph 우선순위는 실행 후보를 구성할 뿐 Evidence 또는 Ready를 만들 수 없다.

```text
Hackathon metadata (overlay-spec-v1)
             │ explicit registration
             ▼
HackathonExecutionOverlay
  preparation: reviewed WorkGraph + demo-first context
  proposal: direct proposal rejected, dependency-free demo root first
             │
             ▼
Host: Develop strategy → Hackathon strategy → reviewed-plan gate
             │ explicit /execute
             ▼
Coordinator: existing WorkGraph → Candidate → Python Verifier
```

## 구현 내용

- 공통 실행 계약에 Overlay 모듈, 준비/제안 전략, Run별 Overlay 바인딩을 추가했다.
- `DomainExecutionRegistry`는 Domain 모듈과 실행 Overlay를 별도로 명시 등록한다. 메타데이터만 있고 실행 Overlay가 없으면 `DOMAIN_EXECUTION_OVERLAY_UNREGISTERED`로 실패한다.
- Hackathon 리소스를 실제 `overlay-spec-v1` 메타데이터로 전환했다. 기존 `getSkillSpec()`와 `domainCatalog.skills()`는 호환 뷰를 유지한다.
- Host는 선택 순서대로 Overlay를 준비 전략과 제안 전략에 조합하고 ID·개정·전략 식별자를 현재 Run에 고정한다.
- 계약 질문·수정 대기 중에는 제안을 실행하지 않으며, 계약 수락 후 보관한 제안을 현재 계약으로 다시 검사한다.
- Hackathon 제안 전략은 직접 실행을 거절하고 WorkGraph만 허용한다. 첫 dependency-free 단위를 demo root로 앞에 배치한다.
- Host의 기존 `skills.includes("hackathon")` 분기를 제거했다. 계획 우선순위는 조합된 정책의 `demoFirst`만 사용한다.
- Coordinator는 선택한 Overlay, 정책 개정, 전략 식별자와 준비 결과의 Overlay 표식을 정확히 대조한다.
- 계획 작성만 요청한 경우 작업 파일과 worker 실행은 발생하지 않는다. 명시적 실행은 새 Run으로 handoff한 뒤 기존 Develop Candidate·검증 경로를 사용한다.

## 검증 결과

| 검사 | 결과 |
|---|---|
| Overlay/Host/Coordinator 단위 검사 | 조합, 직접 제안 거절, 미등록 실패, 바인딩 불일치 실패, demo root 재정렬, 계약·계획 gate 통과 |
| 실제 Hackathon 앱 통합 | 계획 중 무변경, 명시적 실행 후 2단계 WorkGraph, Candidate commit, Python Ready 통과 |
| General·Develop·Hackathon 앱 통합 묶음 | 12 pass / 0 fail |
| 최종 `test:harness` | **306 pass / 기존 5 fail**, 총 311건 |
| CLI·TUI 회귀 | **52 pass / 0 fail** |
| 관련 패키지 타입 | domain-contracts, domain, kernel, kernel-host, verification, coordinator, workspace, tui 통과 |
| App 타입 | 기존 CLI 오류 3건만 유지 |
| 모듈 경계·frozen lockfile | 통과 |

실제 통합 검사는 새 실행 Run, 실제 worker Candidate, 작업 디렉터리의 두 파일, `python3 -m harness.verified_sidecar`를 사용했다. 계획 검토 시점에는 두 출력 파일이 모두 없고 worker가 0명임을 확인했다. `/execute` 뒤에는 demo와 polish가 의존 순서대로 실행되고, 각 Claim이 실제 파일 관찰로 검증된 뒤에만 Ready가 되었다.

기존 실패 5건과 App 타입 오류 3건은 ③ 기준선과 동일하다.

- `coordinator/test/plan-execution-run.test.ts`: `accepted`, `revised` 2건.
- `coordinator/test/real-parallel-repair.test.ts`: `root-provider-failure`, `root-harness-failure`, `missing-integration` 3건.
- `src/cli/cmd/run.ts`: 316행 `planId` 2건, 930행 `executionBackend` 1건.

## 변경 위치

- 공통 Overlay 실행 계약: `runtime/packages/domain-contracts/src/execution.ts`
- 메타데이터와 기본 실행 Overlay: `runtime/packages/domain/resources/hackathon/spec.json`, `runtime/packages/domain/src/{index,execution}.ts`
- Run 바인딩과 조합: `runtime/packages/kernel-host/src/index.ts`, `runtime/packages/coordinator/src/index.ts`
- 단위·실제 통합 검사: Domain, Kernel Host, Coordinator, App의 Domain execution 테스트

④ 전용 변경 목록, 패치, 최종 파일과 검사 로그는 `../base_harness_work_archive/20260917-stage4-hackathon-overlay/`에 보관한다.

## 후속 범위

- Domain별 판정 기준 보정과 전용 Verifier 바인딩은 사용자 결정에 따라 뒤로 미뤘다.
- 범용 Skill·Context 로딩과 저장 계획의 실행 바인딩 복원, 동적 CLI·TUI·API 표면은 다음 골격 구간이다.
