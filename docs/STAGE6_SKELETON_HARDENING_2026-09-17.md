# ③~⑥ 실행 골격 취약점 보강 및 실사용 검증

## 결과

General·Develop 실행 골격에서 확인된 실행 수명주기, 계약 권한, 전략 고정, 결과 바인딩, CLI 입력 보존 문제를 수정했다. 전체 Harness 353건과 관련 앱·CLI·TUI·Python 검증이 모두 통과했고, 로컬 제어 모델을 사용한 제품 CLI에서 `계약 수락 → 실제 파일 읽기 → 현재 Run 결과 바인딩 → Python Evidence → Ready`를 확인했다.

이번 작업은 내부 Skill·Context 확장과 전용 의미 판정기/Verifier 바인딩을 포함하지 않는다. Python Verifier만 Evidence와 Ready를 생성하는 기존 권한 경계도 유지했다.

## 수정한 경계

| 문제 | 조치 |
| --- | --- |
| 빈 `integrationPaths`인 WorkGraph가 root integration을 건너뜀 | 모든 완료 WorkGraph가 root integration executor를 정확히 한 번 호출한다. executor 미등록 또는 실패는 verifier 호출 전에 terminal `blocked`로 닫는다. 기존 5개 회귀 실패의 실제 원인은 비동기 경쟁이 아니라 이 skip 분기였다. |
| 계약 수락이 도구 위험도·구체 경로 권한으로 이어지지 않음 | 구조화 변경은 low, delegate는 medium, opaque execute는 high, unknown은 critical을 최소 위험도로 요구한다. Host는 현재 Run의 수락 계약에 있는 required criterion 최대 위험도로 검사한다. |
| WorkGraph와 도구가 계약 target을 넓힐 수 있음 | verifier가 수락한 계약의 state-changing Claim target/exclusion을 Workspace authority로 등록한다. WorkUnit `writeSet`, `integrationPaths`, 직접 write/edit/apply_patch와 move 목적지는 그 권한 안에서만 허용한다. root integration write는 `계약 target ∩ reviewed integrationPaths`로 제한한다. |
| 계약 전·IDs-only 등록과 계약 교체가 과거 권한을 남길 수 있음 | 수락된 계약 전체가 없는 managed root와 ID 목록만 있는 등록은 실행 경로 권한으로 인정하지 않고 fail-closed한다. 새 계약 제안 시 이전 권한을 즉시 폐기하고, verifier가 새 계약을 수락한 뒤에만 다시 등록한다. 새 Run도 이전 authority를 상속하지 않는다. |
| shell이 경로 제한을 우회할 수 있음 | opaque shell은 high/critical 계약, workspace-root target, exclusion 없음이 모두 충족될 때만 실행된다. 좁은 파일 계약에서는 구조화 도구를 사용한다. |
| 등록 후 class 전략의 공개 상태가 바뀔 수 있음 | 전략 진입 함수와 식별자를 고정하고, own descriptor·중첩 객체·Map/Set·prototype의 관찰 가능한 상태를 호출 전후 비교한다. 변경 시 실행하지 않고 typed Domain 오류로 닫는다. |
| General 결과가 다른 Run/executor에서 오거나 덮어써질 수 있음 | 현재 Run, accepted direct phase, 고정 adapter/model, read-only 변경 목록, non-empty 결과를 검사한다. 첫 결과만 불변으로 저장하고 stale/terminal 결과는 버리며 상충 중복은 차단한다. |
| General 결과와 required literal 계약이 명백히 충돌해도 Ready로 진행할 수 있음 | `content_contains`/`content_equals`의 명백한 문자열 불일치만 negative admission에서 차단한다. 이 검사는 Evidence를 만들지 않으며, 최종 Ready는 계속 Python Verifier가 결정한다. |
| CLI가 자연어 인자 묶음에 literal 따옴표를 삽입함 | 일반 prompt는 argv 문자열을 그대로 공백 결합한다. shell-style quoting은 명시적 `--command` 경로에만 남겼다. |

## 검증 결과

| 검사 | 결과 |
| --- | --- |
| 전체 Harness | **353 pass / 0 fail**, 52 files, 2,352 assertions |
| 앱 Domain·외부 계약 수명주기 | **9 pass / 0 fail**. General 실제 읽기·무변경, 결과 불일치 차단, 늦은 결과 대기, Develop Candidate 검증·commit, 계획 경계 포함 |
| 실제 도구 권한 | shell/apply_patch **50 pass / 0 fail** |
| 일반 모델 집중 검사 | **1 pass / 0 fail** |
| CLI·HTTP 인터페이스 | **27 pass / 0 fail** |
| TUI | **95 pass / 0 fail** |
| Python Verifier | `tests/test_verified_sidecar.py` **27 pass / 0 fail** |
| 타입 검사 | domain-contracts, domain, kernel, kernel-host, coordinator, workspace, verification, base-harness 모두 통과 |
| 모듈 경계 | `Harness module boundaries are valid.` |

검사군은 서로 겹치므로 위 숫자를 단순 합산하지 않는다.

제품 CLI 실사용 검사는 상용 서비스 대신 loopback 고정 모델 서버를 사용했다. 실제 제품 entry point, 실제 `read` 도구와 Python sidecar를 호출했으며 다음을 모두 확인했다.

- 종료 코드 0, timeout 없음, 모델 요청 4회.
- Goal이 `Read source.txt and report its content`로 따옴표 없이 보존됨.
- General preparation과 수락된 GoalContract가 모델 루프에 전달됨.
- 실제 파일 읽기 결과가 관찰됨.
- 결과의 Run ID가 최종 현재 Run과 일치함.
- Python Evidence 생성 후 `readyEligible=true`와 `outcome=ready` 도달.
- 입력 파일 SHA-256 전후 동일: `f74ca12ec46e2f1dcc74d34d9bae3ec596f03751afdc2fe536bc37af9bc762d0`.

## 남은 의도적 경계

- `exists`, hash, 요약, 추론, 복수 사실의 의미적 정확성은 이번 문자열 negative gate가 증명하지 않는다. 전용 판정·Verifier 바인딩 후속 범위다.
- JavaScript가 노출하지 않는 class private slot과 closure cell은 등록 구현의 불변성 신뢰 경계로 남는다. 동작 변경은 새 전략 ID/revision으로 등록해야 한다.
- 파일 범위 계약에서 opaque shell은 안전하게 제한할 수 없어 거절한다. workspace 전체 실행 권한이 필요하거나 write/edit/apply_patch 같은 구조화 도구를 사용해야 한다.
- 외부 실행기의 root integration 미지원은 계속 명시적 `EXTERNAL_ROOT_INTEGRATION_UNSUPPORTED` 오류다.
- MCP/외부 원격 부작용은 Host 계약·위험도 gate를 통과하지만, 로컬 Workspace path authority의 의미 범위에는 포함되지 않는다.
- 내부 Skill·Context 확장, 저장 계획 형식, 복원 정책은 변경하지 않았다.

## 근거 위치

- 실행 수명주기와 결과 gate: `runtime/packages/coordinator/src/index.ts`
- 계약 위험도와 Host admission: `runtime/packages/kernel/src/index.ts`, `runtime/packages/kernel-host/src/index.ts`
- target/exclusion 및 Candidate 경계: `runtime/packages/workspace/src/orchestration.ts`
- 전략 고정: `runtime/packages/domain/src/execution.ts`
- 제품 도구 연결: `runtime/packages/base-harness/src/tool/shell.ts`, `runtime/packages/base-harness/src/tool/apply_patch.ts`
- CLI 입력 보존: `runtime/packages/base-harness/src/cli/cmd/run.ts`
- 재현 스크립트와 전체 로그: `../base_harness_work_archive/20260917-skeleton-hardening/`
