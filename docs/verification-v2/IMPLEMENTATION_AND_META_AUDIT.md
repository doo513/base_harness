# Verification Protocol V2 구현 및 메타 감사

작성일: 2026-08-26

## 1. 변경 목적

기존 실행 경로는 사용자 요구를 구체적인 Claim으로 계약화하지 않은 채 `아무 Tool Action이 존재함`과 `발견된 Check가 모두 성공함`을 결합해 Ready를 만들 수 있었다. 이 구조에서는 성공한 Check가 실제 사용자 요구를 검증하는지, 여러 Evidence가 독립적인지, 과거 Evidence가 현재 환경에 적용 가능한지 판정할 수 없었다.

이번 변경은 다음 세 구간을 서로 다른 권한과 산출물로 분리한다.

1. 1구간은 사용자 요구를 검증 가능한 Criterion과 Claim으로 계약화한다.
2. 2구간은 Host가 관찰한 Action과 Verifier가 만든 Evidence를 Claim에 결합한다.
3. 3구간은 Evidence의 계보, 독립성, 중복, 적용조건, 반례와 Verifier 생명주기를 계산한다.

현재 Run의 Ready와 장기 Evidence 신뢰 단계는 별도 상태다. Ready는 Root GoalContract의 전체 Criterion이 충족됐다는 Run 단위 Attestation이고, `candidate`, `supported`, `reproduced`, `established`는 이후 검증 후보로 재사용하기 위한 Evidence Case의 파생 상태다.

## 2. 공통 권한 경계

### 원인

- TypeScript Host와 Python Sidecar가 서로 다른 축약된 상태를 가졌고 Python Sidecar가 구체적인 Claim 없이 Ready를 발행했다.
- Actor가 제공한 Tool output과 metadata가 Failure 분류 및 Evidence 후보에 직접 영향을 줬다.
- Protocol V1에는 Criterion ID, Claim ID, Action ID, Execution ID, Verifier Attestation이 없었다.

### 수정

- NDJSON Envelope를 Protocol V2로 단절 전환했다.
- TS Host는 Run, Scope, Action, Execution ID와 실제 Tool 상태를 전달하고 Ready 권한을 갖지 않는다.
- Python V2 Domain이 계약 승인, Claim Coverage, Evidence Trust와 Ready 발행을 독점한다.
- V1 `action.observe`를 제거하고 `action.open`과 `action.close`를 분리했다.
- Workspace 밖 상태 경로에 Artifact CAS와 해시 체인 Event Log를 저장한다.
- LLM이 전달한 `critical_failure`, `severity`, `trust`는 판정 입력으로 사용하지 않는다.

## 3. 1구간 구현과 인과 기록

### 기존 원인

- TUI는 Session title과 고정 문장 `Requested workspace behavior is independently verified`를 GoalContract로 사용했다.
- Headless 경로도 실제 Acceptance Criteria 대신 고정된 독립 Check 문장을 사용했다.
- Acceptance 문자열과 Verifier 사이에 기계적으로 확인 가능한 연결이 없었다.
- Claim의 대상, 제외 범위와 환경 조건이 Claim 식별자에 포함되지 않았다.

### 구현 조치

- `GoalContractV2`, `CriterionContract`, `ClaimContract`, `Applicability`, `VerifierPolicy`를 공개 타입으로 추가했다.
- 모든 Criterion은 기록된 User Source의 SHA-256과 연결된다.
- Criterion과 Claim은 양방향 ID 연결을 가져야 하며 한쪽만 연결된 계약은 거부된다.
- Claim은 단일 typed Predicate, 대상, 기능, 제외 범위와 Applicability를 가져야 한다.
- Claim 종류와 Verifier strength/capability가 맞지 않거나 Verifier가 폐기됐으면 계약을 거부한다.
- 내부 `harness_contract` Tool을 추가하고 변경 Tool보다 먼저 구조화 계약을 제출하도록 Tool Registry 경계를 추가했다.
- 읽기, 검색, 질문 Tool은 계약 전 허용하고 Shell, Write, Edit, Patch, Task와 사용자 Plugin Tool은 계약 전 차단한다.
- 계약이 없는 `action.open`은 Artifact를 만들지 않고 `goal_contract_missing` Repair를 반환한다.
- 계약 변경은 Revision 증가가 필요하고 Action 이후에는 기존 Claim을 제거할 수 없다.

### 1구간 메타 점검

| 점검 질문 | 판정 근거 |
|---|---|
| Claim이 실제 요구에서 파생됐는가 | User Source ID와 원문 Hash가 일치해야 계약 승인 |
| 완료조건과 Claim이 연결됐는가 | Criterion-Claim 양방향 ID 검사 |
| Claim이 지나치게 큰가 | Claim당 typed Predicate 하나만 허용 |
| Scope가 비어 있는가 | targets와 capabilities의 비어 있지 않은 배열 요구 |
| 환경 조건이 누락됐는가 | 8개 Applicability 차원을 필수 검사 |
| Verifier가 Claim을 검증 가능한가 | Claim kind와 최소 strength를 Registry에서 교차 검사 |
| 계약 전 변경이 가능한가 | Tool Registry와 Sidecar 양쪽에서 차단 |

### 남는 한계와 대응

원문 Hash는 Claim의 출처를 증명하지만 자연어 해석 자체가 유일하게 옳다는 것은 증명하지 않는다. 이를 Evidence로 오인하지 않으며, 고위험 Criterion은 2구간의 독립 검증 강도로 보완한다. TUI의 최초 Source는 현재 Session title이므로 계약 Tool에서 실제 요구를 다시 구체화해야 하며, 제목만으로 Ready를 발행하지 않도록 변경 Tool 앞에 계약 제출을 강제했다.

## 4. 2구간 구현과 인과 기록

### 기존 원인

- 같은 Run 안에서 Action과 Check가 서로 관련이 없어도 Ready가 가능했다.
- Tool output이 Actor와 동일한 실행 경계에서 만들어졌는데도 Evidence처럼 보일 수 있었다.
- Check가 어떤 Claim을 검증했는지, 어떤 Verifier capability를 사용했는지 기록하지 않았다.
- Coverage를 전체와 부분으로 구분하지 않았다.

### 구현 조치

- `action.open`에서 Action, Execution, Claim ID와 Input Hash를 고정한다.
- `action.close`는 반드시 같은 Action ID와 Scope에 연결돼야 한다.
- Tool output은 항상 `untrusted_execution_observation` Candidate로만 저장한다.
- Claim Evidence는 계약에서 허용한 Verifier를 Python Sidecar가 직접 실행했을 때만 생성한다.
- Verifier ID, Method ID, Revision, Source Hash, Policy Hash와 지원 Claim 종류를 Attestation에 포함한다.
- Verifier가 반환한 결과가 아니라 Registry capability와 typed Predicate로 Coverage를 계산한다.
- `full`, `partial`, `none`을 분리하고 Partial은 Criterion을 만족시키지 않는다.
- Root Criterion의 필수 Claim이 모두 Full Coverage일 때만 ReadyAttestation을 만든다.
- Child Scope는 Evidence를 제공할 수 있지만 Root Ready를 발행할 수 없다.
- 반려 결과는 실패 Criterion, Claim별 부족 Evidence, 수리 범위와 Fingerprint만 반환한다.

### 2구간 메타 점검

| 점검 질문 | 판정 근거 |
|---|---|
| Action이 Claim을 검증하기 위한 것인가 | action.open의 claimIds가 승인 계약 안에 있어야 함 |
| Evidence가 실제 Action에서 만들어졌는가 | matching action.open/action.close와 executionId 요구 |
| Actor output이 Ready를 위조할 수 있는가 | Actor output은 Candidate trust로 고정 |
| 성공 Check가 Claim을 직접 다루는가 | allowedVerifierIds와 Claim kind/strength 검사 |
| 일부 성공을 전체 성공으로 계산하는가 | Partial Coverage는 Criterion 실패 |
| 실패 후 무한 재계획하는가 | 동일 Fingerprint 2회 Repair 후 Blocked |

### 위험 적응형 정책

- Low는 Claim 종류에 맞는 직접 Family 하나를 요구한다.
- Medium은 현재 Run의 Execution 이상 직접 Family 하나를 요구한다.
- High는 서로 다른 Method Family 두 개를 요구하며 결정적 Oracle은 하나로 대체할 수 있다.
- Critical은 현재 Run의 독립 Method Family 두 개와 External Oracle 하나를 반드시 요구한다.

## 5. 3구간 구현과 인과 기록

### 기존 원인

- Evidence Family가 내용 Hash 중심이어서 같은 실행의 파생 자료를 독립 Evidence로 셀 수 있었다.
- 다른 Run이라는 이유만으로 독립 증거처럼 취급할 수 있었다.
- 표현이나 Duration만 다른 결과가 신뢰도를 반복해서 올릴 수 있었다.
- 환경이 다른 과거 Evidence를 현재 검증에 적용할 수 있었다.
- Verifier가 폐기돼도 해당 Verifier의 과거 승인 결과를 일괄 무효화하지 않았다.
- 반례가 같은 Claim Case에 연결되지 않거나 LLM의 `critical_failure` 표기를 신뢰할 수 있었다.

### 구현 조치

- Family ID는 Run, Method, Command, CWD와 Applicability를 결합한다.
- 같은 Run과 Method의 의미상 동일 결과는 한 Support Event로만 계산한다.
- 서로 다른 Run의 같은 Method는 `reproduced`까지만 허용한다.
- 서로 다른 Run과 Method가 모두 확인돼야 `established`가 된다.
- Case ID는 Claim statement, kind, Scope, Applicability와 Predicate를 결합한다.
- Applicability Hash가 다른 Evidence는 고위험 독립 Family 보강에 사용하지 않는다.
- Soft Contradiction Family 두 개는 계산된 Tier를 한 단계 낮춘다.
- Hard Contradiction은 Case를 즉시 Quarantine하고 Retrieval Projection에서 제거한다.
- Revoked Verifier의 Support는 Tier 계산과 과거 독립 Family 계산에서 제외한다.
- Evidence 원본은 불변으로 두고 Tier와 Status만 Event에서 재계산한다.
- Retrieval 문서는 제목과 Situation, Reason, Action, Result, Evidence만 가진 20줄 이하 Projection으로 생성한다.
- Retrieval Projection은 검증 후보이며 Claim, Evidence, Ready를 직접 생성할 권한이 없다.

### 3구간 메타 점검

| 점검 질문 | 판정 근거 |
|---|---|
| 같은 Evidence가 여러 번 계산되는가 | Run, Method, Semantic Fingerprint 중복 제거 |
| 재현과 독립성이 구분되는가 | Run 다양성과 Method 다양성을 별도 계산 |
| 다른 환경 Evidence가 섞이는가 | Applicability Hash가 다르면 과거 보강에서 제외 |
| 반례가 신뢰 상태에 영향을 주는가 | Soft 강등과 Hard Quarantine 상태 전이 |
| 잘못된 Verifier 결과가 남는가 | revokedVerifiers 기반 재계산 |
| RAG가 사실 권한을 얻는가 | Retrieval Projection은 별도 비권위 저장물 |

## 6. 전체 메타 점검

### 권한 교차 점검

- LLM은 Contract 후보와 Claim 연결을 제안할 수 있지만 Source Hash, Action 상태, Evidence Trust, Failure severity, Ready를 확정할 수 없다.
- TS Host는 Action을 관찰하지만 Claim Coverage와 Ready를 판정하지 않는다.
- Python Verifier는 저장된 Source, 계약, Host Action과 자체 실행 Evidence만 사용한다.
- Memory는 과거 검증 방법을 제안하지만 현재 Run의 필수 직접 Evidence를 대체하지 않는다.

### 실패 경계 점검

- Protocol Version, 손상된 NDJSON, Sidecar Crash와 무결성 오류는 Fail-closed다.
- Provider, Model Protocol, Tool, Implementation, Harness, Integrity, Persistence 오류는 별도 FailureKind를 사용한다.
- 문자열 분류는 구조화 FailureKind가 없을 때의 보조 수단이며 Critical 판정에는 사용하지 않는다.

### 완료 불변식

Ready는 다음 조건을 모두 만족해야 한다.

1. Root Scope에 승인·고정된 GoalContract가 존재한다.
2. Pending Action과 Blocking Runtime Failure가 없다.
3. Host가 관찰한 완료 Action이 하나 이상 존재한다.
4. 모든 필수 Criterion의 Claim이 Full Coverage다.
5. 위험도별 독립 Family 정책을 만족한다.
6. 사용한 Verifier가 등록돼 있고 폐기되지 않았다.
7. Ready Artifact가 Workspace 밖 Verifier 저장소에 생성됐다.

## 7. 검증 명령과 요구 증거

| 구간 | 명령 | 증명 대상 |
|---|---|---|
| 1구간 | `python -m pytest -q tests/test_verified_sidecar.py -k contract` | Source, Criterion, Claim, Scope, 사전 계약 경계 |
| 2구간 | `python -m pytest -q tests/test_verified_sidecar.py -k ready` | Action-Evidence Binding, Coverage, Root Ready |
| 3구간 | `python -m pytest -q tests/test_verified_sidecar.py -k memory` | 중복 제거, 재현, 독립 Method 승격 |
| TS Protocol | `bun test packages/verification/test/client.test.ts` | Protocol V2, 두 단계 Action, Fail-closed |
| 전체 회귀 | `python -m pytest -q` 및 Runtime Typecheck | 기존 Verified Core와 실행 코어 회귀 |

이 문서의 완료 판정은 위 검증이 실제로 통과하고 변경 파일의 최종 Diff가 본 권한 경계를 유지할 때만 유효하다.

## 8. 전체 회귀에서 발견한 기존 결함과 조치

### 원인

전 구간 구현 후 전체 Python 회귀를 Windows와 Linux에서 실행했다. Windows에서는 Unix 전용 Shell, AF_UNIX, killpg, symlink permission을 플랫폼 Skip 없이 사용한 기존 테스트가 실패했다. Linux에서는 이 플랫폼 실패가 제거됐지만 Actor System Contract가 830 추정 Token으로 증가해 4K Local Model의 정적 예산 상한 800을 넘는 실제 기존 회귀가 확인됐다.

### 수정

- Authority 규칙에서 동일 의미를 반복하던 untrusted, retrieval, memory, tool output 문장을 하나의 권한 규칙으로 합쳤다.
- Context Compilation 설명과 Memory Candidate 게시 규칙을 의미를 유지한 짧은 문장으로 바꿨다.
- GoalContract, Kernel control, untrusted instruction 금지, Evidence promotion, 완료 권한은 제거하지 않았다.

### 인과 판정

System Contract 증가가 Context Budget을 선점했고, 그 결과 선택적 Context 접기 단계가 Mandatory Context조차 2816 Token 입력 예산에 넣지 못했다. 정적 계약 중복을 줄이면 모델 입력에 사용할 수 있는 예산이 복구되고, 검증 구조가 추가한 Claim·Evidence 상태가 작은 Local Model에서도 작업 Context를 밀어내지 않는다.

## 9. 실행된 검증 결과

| 검증 | 결과 |
|---|---|
| Protocol V2 Python 전용 Suite | 14 passed |
| TS NDJSON Client와 Fail-closed | 5 passed |
| Contract·MCP 사전 Gate | 2 passed |
| Verification Package Typecheck | passed |
| Base Runtime Typecheck | passed |
| TUI Typecheck | passed |
| Context Budget·Untrusted 권한 호환 | 7 passed |

### 전체 Python 회귀 해석

- Windows 전체 실행은 Context 수정 전 최종 측정에서 345 passed, 9 skipped, 19 failed였다.
- 이 중 1개는 System Contract 고정 문구 변경으로 생긴 회귀였으며 고정 문구를 복원한 후 Context·권한 테스트 7개가 통과했다.
- 나머지 18개는 Windows에서 Unix 명령 `true`, `printf`, `test`, AF_UNIX, killpg, select(pipe), POSIX symlink와 permission 동작을 요구하는 기존 플랫폼 비호환이다.
- Ubuntu WSL 전체 실행은 368 passed, 5 failed였고, 3개는 기존 Context Budget 초과, 2개는 임시 Venv의 PATH와 PYTHONPATH 누락이었다.
- Context 수정과 올바른 Linux 실행환경을 적용해 실패한 5개 전체와 연관 회귀를 대상으로 8개 테스트를 재실행했고 모두 통과했다.

따라서 V2 변경 범위의 직접 테스트, TypeScript 정적 계약과 Linux에서 확인된 논리 회귀는 닫혔다. Windows의 18개 플랫폼 비호환은 이번 V2 Claim·Evidence 구현과 파일 범위가 겹치지 않으며 별도의 Cross-platform Sandbox 작업으로 남긴다.
