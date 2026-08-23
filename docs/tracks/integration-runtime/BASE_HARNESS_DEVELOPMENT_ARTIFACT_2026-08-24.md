# base_harness 개발 산출물 보고서 — 2026-08-24

## 1. 문서 목적

이 문서는 `base_harness`에 지금까지 반영된 구현을 단순 기능 목록이 아니라 **문제 → 원인 → 설계 결정 → 구현 → 검증 → 잔여 위험**의 인과관계로 정리한 개발 산출물이다.

기준 브랜치는 `develop`이며, 이 문서 작성 직전 전체 회귀는 다음 상태였다.

```text
compile                         PASS
CLI/TUI entrypoints             PASS
full pytest                     323 passed, 7 skipped
Stage 02 isolation/binding      PASS
Stage 03 resume                 PASS
Stage 04 semantic verification  PASS
Stage 05 recovery               PASS
Stage 06 progress control       PASS
Stage 07 context governance     PASS
Stage 08 retrieval/integrity    PASS
```

핵심 불변식은 다음과 같다.

> **Actor는 계획·제안·도구 사용을 요청할 수 있지만, 검증된 사실과 완료 여부를 확정하는 권한은 Harness에만 있다.**

---

## 2. 전체 제어 구조

```text
사용자
  │  목표 / workspace / profile / model / permission
  ▼
TUI / CLI
  │
  ▼
Task Intake + Config
  │
  ▼
LLM Actor
  │  plan / task / propose / tool / retrieve / complete 요청
  ▼
Verified-State Harness
  ├─ Workspace boundary
  ├─ Tool / capability policy
  ├─ Evidence store
  ├─ Verification contracts
  ├─ Progress control
  ├─ Recovery
  ├─ Retrieval / Project Memory
  └─ Completion Oracle
  │
  ▼
검증된 결과 + 재현 가능한 실행 기록
```

### 역할 구분

| 주체 | 책임 |
| --- | --- |
| 사용자 | 무엇을 할지와 허용 범위를 설정 |
| LLM Actor | 어떻게 수행할지 계획하고 행동을 제안 |
| Harness | 실제 실행·권한·증거·검증·복구·완료를 통제 |

이 구분은 모델의 추론 품질과 Harness의 신뢰 경계를 분리하기 위한 핵심 설계이다.

---

## 3. Workspace 및 실행 경계

### 문제

Agent가 임의의 파일시스템 또는 실행 환경에 접근할 수 있으면 모델의 실수나 prompt injection이 곧 호스트 변경으로 이어질 수 있다.

### 조치

`WorkspaceContract`를 중심으로 Actor 파일 도구의 루트를 고정하고, 실행 도구는 SecurityConfig 및 backend 정책을 거치도록 했다.

```text
User-selected workspace
        ↓
WorkspaceContract.root
        ↓
file.read / file.search / directory.list / write tools
        ↓
root 내부에서만 접근
```

Linux namespace backend에는 별도 isolation probe와 tool binding 검증이 있으며, local backend는 강한 격리로 간주하지 않는다.

### 결과

- workspace 탈출을 Actor의 일반 파일 작업과 분리
- tool backend binding 검증
- nested submount / isolation probe 유지
- strict isolation 요구 시 fail-closed 가능

### 잔여 위험

범용 Docker/VM/Remote Provider 추상화는 아직 완성된 공통 환경 계층으로 승격되지 않았다. 따라서 현재 안정 경계는 기존 local/Linux namespace 구현을 기준으로 설명해야 한다.

---

## 4. Evidence-first Verified State

### 문제

LLM이 "성공했다", "파일이 존재한다", "테스트가 통과했다"고 말하는 것만으로 상태를 사실로 인정하면 hallucination이 Kernel의 truth state로 오염된다.

### 설계

```text
Actor proposal
   ↓
Hypothesis
   ↓
Evidence artifact
   ↓
Verifier chain
   ↓
Verification contract
   ↓
VERIFIED fact
```

`ClaimStatus`, `VerificationLevel`, `VerificationRequirement`, `VerificationContract`, `VerifierChain`을 사용해 모델의 주장과 Harness의 승인 상태를 분리했다.

### 검증 수준

```text
SCHEMA
STRUCTURAL
LOGICAL
TRANSITION
EXECUTION
EXTERNAL_ORACLE
```

### 결과

- 모델은 `facts`에 직접 쓰지 못함
- content-addressed artifact 무결성 검증
- claim-bound evidence 검증 가능
- 구조화 artifact assertion 지원
- domain-specific verifier를 별도로 구성 가능

---

## 5. Completion Oracle 경계

### 문제

초기 구조에서는 Actor가 sandbox backend를 사용하더라도 최종 acceptance command가 별도 local process에서 실행될 수 있어 Actor와 Oracle의 실행 경계가 달라질 가능성이 있었다.

### 원인

Completion Oracle이 runtime에서 선택한 backend와 독립적으로 process backend를 구성하는 경로가 존재했다.

### 조치

Command 기반 Oracle에 backend를 명시적으로 주입하고 profile에서 Actor 실행 backend와 Oracle backend를 구분하여 구성하도록 변경했다.

### 결과

- completion request 자체는 성공 판정이 아님
- Harness-side Oracle이 acceptance를 수행
- sealed oracle / oracle isolation 요구 옵션 유지

---

## 6. Progress Control과 반복 루프 차단

### 문제

LLM은 `plan → plan → read → plan`처럼 활동은 계속하면서 실질적인 진전을 만들지 못할 수 있다.

### 설계

"새로운 행동"과 "검증 가능한 진전"을 분리했다.

```text
Activity novelty           → credit 0
Verified fact change       → epistemic progress
Profile task advancement   → task progress
```

`no_progress_streak`, `family_repeat_count`, `strategy_generation`을 통해 반복 패턴을 감지한다.

### 결과

다음과 같은 루프를 Harness가 중단·재계획할 수 있다.

```text
plan → plan → plan
file.read → file.read → file.read
동일 tool family 반복
```

### 관찰된 한계

작은 로컬 모델이 structured decision을 자주 깨뜨리면 protocol 오류가 progress loop와 섞여 step budget을 소비했다. 이 문제는 이후 Model Gateway 개선의 직접 원인이 됐다.

---

## 7. Failure Recovery와 Resume

### 목표

실패를 숨기거나 전체 상태를 초기화하는 대신, 실패 원인과 실행 이력을 유지하면서 재시도 가능하도록 한다.

### 현재 구조

- persisted run manifest
- integrity-checked checkpoint
- event log
- tool receipts
- controller runtime state protocol
- recovery transition / strategy generation

비멱등 tool call은 receipt를 통해 resume 시 무조건 재실행되지 않도록 한다.

### 결과

TUI에서 중단해도 persisted state를 `/resume`, `/inspect`로 재사용할 수 있다.

---

## 8. Context Governance와 Retrieval

### 문제

장기 실행에서 모든 로그·관찰·검색 결과를 그대로 모델에 넣으면 token 비용과 prompt injection surface가 함께 증가한다.

### 조치

Stage 07에서 context governance, Stage 08에서 retrieval ownership을 분리했다.

```text
Actor requests query
      ↓
Kernel owns scope / top-k / provider / ranking / admission
      ↓
retrieved artifact
      ↓
untrusted context
```

### 핵심 규칙

- retrieval text는 항상 untrusted data
- instruction authority 없음
- retrieval 자체는 progress credit 없음
- bounded item/content/context limits
- resume 시 retrieval provenance 검증

---

## 9. Project Memory — 현재 실제 구현 상태

### 현재 구현

현재 안정적으로 활성화된 공통 Memory는 `ProjectMemoryStore` 기반의 **Memory v1**이다.

지원 기능:

- `project`, `episodic` memory candidate
- `memory_candidate.*` reserved hypothesis
- 최소 1개 registered evidence ref 요구
- workspace와 memory root 분리
- post-run publish
- frozen run-start snapshot
- integrity envelope
- bounded record/content/tag size
- 다음 run에서 lexical retrieval
- 기억된 텍스트는 항상 `untrusted_project_memory`

```text
Evidence
   ↓
Memory Candidate
   ↓
post-run admission
   ↓
Project Memory Store
   ↓
next-run frozen retrieval snapshot
```

### 중요한 신뢰 규칙

Memory가 evidence를 참조하더라도 자동으로 trusted fact가 되지 않는다.

```text
remembered ≠ verified
retrieved  ≠ instruction
memory     ≠ completion authority
```

### P2 Memory A-D 상태

P2-A~D는 연구 자료와 현재 Kernel 구조를 대조하여 다음 설계까지 확정했다.

```text
P2-A Lifecycle
  semantic_key / append-only lifecycle / current-state resolver

P2-B Evidence Binding
  memory-evidence semantic binding / verification history

P2-C Typed Retrieval
  state / episodic / procedural / constraint + BM25 + query-time assembly

P2-D Lineage
  presented_to / cited_by / required_by / produced impact graph
```

하지만 이전 compressed staging applicator가 무결성 검증을 통과하지 못했으므로 **이 P2-A~D 코드는 현재 안정 runtime에 적용된 것으로 간주하지 않는다.** 실패한 staging workflow·payload는 제거했다.

이는 "실행되지 않은 설계를 완료로 기록하지 않는다"는 evidence-first 원칙을 개발 과정 자체에도 적용한 것이다.

---

## 10. Model Gateway

### 기존 문제

원격 API와 로컬 모델을 모두 하나의 OpenAI-compatible 문자열 경로로 처리하면서 다음 문제가 관찰됐다.

```text
잘린 JSON
Markdown fenced JSON
빈 tool name
thinking output과 final output 혼동
rate limit / timeout / protocol error 혼합
```

Controller에서 JSON을 복구하면 이런 provider protocol 오류가 Harness의 `replan/recovery`로 넘어가 불필요한 step을 사용했다.

### 개선 방향

```text
LLMController
    ↓
ModelGateway
    ├─ Ollama provider
    ├─ LM Studio provider
    └─ OpenAI-compatible provider
    ↓
structured protocol validation
    ↓
canonical JSON decision
```

### 실제 구현

#### Ollama

- provider id: `ollama`
- 기본 native endpoint: `http://127.0.0.1:11434/api/chat`
- JSON Schema structured output
- `stream=false`
- 기본 deterministic temperature
- thinking 옵션 제어

#### LM Studio

- provider id: `lm-studio`
- 기본 endpoint: `http://127.0.0.1:1234/v1/chat/completions`
- OpenAI-compatible `json_schema` response format

#### Gateway protocol validation

다음 오류를 provider protocol 문제로 분류한다.

```text
protocol_truncated
protocol_invalid_json
protocol_schema
empty_response
rate_limit
network_error
timeout
```

로컬 structured provider에서 protocol 오류가 발생하면 Controller로 넘기기 전에 **같은 요청에 대해 1회 protocol repair**를 수행한다.

```text
잘린/잘못된 JSON
     ↓
Gateway detects protocol error
     ↓
1 bounded repair attempt
     ↓
valid canonical decision
     ↓
Controller
```

### 효과

로컬 모델의 출력 형식 오류가 곧바로 Harness 전체의 `repair → replan → strategy switch`로 확대되는 것을 줄였다.

### 검증

`tests/test_local_model_gateway_adapters.py`에 다음 회귀를 추가했다.

- Ollama/LM Studio provider registry
- default endpoint
- truncated JSON repair
- empty tool/schema repair
- protocol repair telemetry

---

## 11. TUI / CLI

### TUI 목적

복잡한 Kernel 내부 이벤트를 모두 노출하지 않고 사용자가 현재 행동과 문제만 확인하도록 한다.

```text
◇ Plan
● Tool
✓ Verify
↻ Retry
✕ Issue
✓ Final
```

### 사용자 통제 영역

- workspace
- profile/domain
- model/provider
- acceptance command
- MCP/Skill discovery
- permissions/status
- resume/inspect
- task interruption

Esc/Ctrl+C 중단 시 run state는 보존된다.

### CLI

동일 runtime을 명시적 parameter로 실행하기 위한 automation/CI 인터페이스로 유지한다.

---

## 12. MCP와 Skills

MCP와 Skill은 Kernel authority를 우회하지 않는다.

```text
Skill = guidance / reusable capability metadata
MCP = external tool surface

둘 모두
→ Capability / Security / Tool Runtime
→ Evidence
→ Verification
```

검색 또는 설치 가능하다는 사실은 trust를 의미하지 않는다.

---

## 13. CI 및 검증 체계

`research-ci.yml`은 단순 pytest 외에도 다음을 함께 검사한다.

- compileall
- CLI module / console
- TUI module / console
- full pytest
- core freeze audit
- resume
- semantic verification
- recovery / adversarial / crash-window
- progress
- context governance
- retrieval / integrity
- namespace/binding probes

### 2026-08-24 정리 과정

한 시점에 전체 pytest는 통과했지만 compile gate만 실패했다.

```text
full pytest  323 passed, 7 skipped
compile      FAIL
```

원인은 런타임 구현이 아니라 다음 stale staging placeholder였다.

```text
scripts/apply_p0_preflight.py
<ACTUAL_APPLICATOR_TO_BE_INJECTED>
```

또한 실패한 P2 compressed applicator와 one-shot workflow가 남아 있었다.

### 조치

- 실행되지 않은 one-shot remediation workflow 제거
- placeholder applicator 제거
- 실패한 P2 applicator/payload 제거
- 과거 staging-only Base64 payload 제거
- 해결된 diagnostic 제거

### 결과

정리 후 CI:

```text
Result                            PASS
compile                           PASS
full pytest                       323 passed, 7 skipped
all listed Stage 02~08 gates      PASS
```

즉 기능 회귀뿐 아니라 저장소 자체의 build cleanliness도 다시 확보했다.

---

## 14. 주요 인과관계 요약

| 관찰된 문제 | 원인 | 변경 | 결과 |
| --- | --- | --- | --- |
| LLM 주장만으로 성공 오염 가능 | Actor와 truth authority 혼합 | Verified State + Verifier | facts/완료는 Harness만 승인 |
| sandbox와 acceptance 실행 경계 불일치 | Oracle backend 독립 생성 | explicit backend injection | Actor/Oracle 경계 추적 가능 |
| plan/read 무한 반복 | activity와 progress 혼합 | deterministic progress credit | no-progress 감지·전략 전환 |
| crash/resume 시 tool 중복 위험 | side effect 재실행 | receipt/checkpoint | durable resume |
| 검색 결과가 지시로 작동할 위험 | retrieval trust 미분리 | untrusted retrieval contract | 검색은 evidence only |
| 장기 작업 경험 소실 | run 간 상태 없음 | Project Memory v1 | frozen cross-run memory |
| 로컬 모델 JSON 오류가 replan 소모 | provider protocol과 Actor failure 혼합 | local structured adapters + repair | Gateway 안에서 형식 오류 흡수 |
| CI compile만 실패 | stale staging placeholder | one-shot artifact cleanup | 전체 gate PASS |
| P2 Memory가 적용된 것처럼 보일 위험 | staging 실패와 구현 상태 혼동 | 실패 payload 제거 + 상태 문서화 | 실제 구현/설계 구분 |

---

## 15. 현재 안정 범위와 다음 단계

### 현재 안정 범위

```text
Verified-State Kernel
Workspace boundary
Tool execution + evidence
Verification contracts
Completion Oracle
Recovery / Resume
Progress control
Context governance
Retrieval
Project Memory v1
TUI / CLI
MCP / Skills boundary
Generic + Ollama + LM Studio model gateway
```

### 다음 우선순위

1. 실제 코드 형태로 P2 Memory Lifecycle/Evidence Binding을 다시 구현한다.
2. 그 후 typed retrieval/query-time assembly를 실험한다.
3. Memory lineage는 먼저 영향 분석만 제공하고 자동 rollback은 후순위로 둔다.
4. local model별 실제 E2E benchmark를 추가한다.
5. Docker/VM/Remote를 포함하는 공통 Environment Provider는 별도 검증 단계로 완성한다.

---

## 16. 결론

현재 `base_harness`의 핵심은 "모델이 알아서 잘하게 만드는 프롬프트"가 아니라 **모델이 틀리거나 반복하거나 형식을 깨더라도 신뢰 경계가 유지되는 실행 시스템**이다.

```text
사용자가 목표와 허용 범위를 정함
           ↓
LLM이 계획·도구·기억을 제안함
           ↓
Harness가 실행·증거·검증·복구를 통제함
           ↓
검증된 결과만 최종 상태로 남김
```

Memory와 Model Gateway의 최근 작업도 동일한 원칙을 따른다. 기억은 참고 정보일 뿐 truth authority가 아니며, 로컬 모델의 protocol 오류는 Kernel 작업 실패로 확대하기 전에 provider boundary에서 처리한다.
