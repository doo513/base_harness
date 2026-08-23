# Token-Aware Context Compiler 구현 보고서 — 2026-08-24

## 1. 목적과 범위

이 문서는 `base_harness`의 로컬 모델 실행에서 확인된 context-window 초과 문제를 기존 Stage 07 Context Governance / Stage 08 Retrieval-Memory 계약을 유지한 채 개선한 작업을 기록한다.

작업 브랜치: `develop`

이번 단계의 목표는 RAG, Vector DB, Wiki 메모리 계층을 새로 추가하는 것이 아니다. 우선 기존 Harness가 이미 보유한 상태·evidence·retrieval을 **모델별 입력 예산에 맞는 Working Context로 조립**하여, 모델이 매 step마다 읽어야 하는 양 자체를 줄이는 것이 목표다.

핵심 불변식은 기존과 같다.

> Context를 줄이는 것은 durable truth/evidence를 삭제하는 작업이 아니다. 모델-visible representation만 줄이며, trusted truth와 completion authority는 기존 Kernel/Verifier/Oracle에 남는다.

---

## 2. 문제 증거

### 2.1 실제 로컬 실행 증상

운영자 실행에서 4096 context route에 대해 다음과 같은 provider 오류가 반복됐다.

```text
request (4127 tokens) exceeds the available context size (4096 tokens)
request (4369 tokens) exceeds the available context size (4096 tokens)
request (4605 tokens) exceeds the available context size (4096 tokens)
...
request (4871 tokens) exceeds the available context size (4096 tokens)
```

결과 흐름은 다음과 같았다.

```text
초기 Actor JSON 출력 실패
  ↓
repair / recovery
  ↓
최근 failure/control 정보 증가
  ↓
전체 model request 증가
  ↓
4096 context 초과
  ↓
provider HTTP 400
  ↓
추가 repair
  ↓
hard budget 소진
```

이 증상 자체는 운영자 제공 runtime evidence이며 repository CI 증거와 구분한다.

### 2.2 기존 문서가 이미 지적한 구조적 문제

`HARNESS_EVIDENCE_BASED_ARCHITECTURE_REVIEW_2026-08-21.md`는 이미 다음 gap을 명시했다.

```text
Context Governor는 bounded이지만
model context window를 인식하지 않는다.
```

그리고 향후 P3로 다음 구조를 제안했다.

```text
Model route
  context_window
  reserved_output_tokens
       ↓
Context Compiler
       ↓
mandatory system + goal + control
       ↓
remaining budget
  tools / workflow / facts / observations / failures / retrieval-memory
```

즉 이번 작업은 기존 아키텍처를 교체한 것이 아니라, 이미 문서화된 Token-aware Context Compiler 계획을 실제 model boundary에 연결한 작업이다.

### 2.3 Active Context의 additive 문제

`PHASE07_CONTEXT_RELEVANCE.md`는 `active_context`가 원래 Stage-07 projection을 대체하지 않고 **추가되는 namespace**라는 한계를 명시한다.

실제 runtime도 다음 형태였다.

```text
Stage-07 base projection
+ domain_contract
+ agent_workflow
+ active_context
+ retrieval preview
+ project_memory descriptor
```

따라서 relevance view가 있어도 전체 prompt의 token 비용이 자동으로 줄지 않았다.

---

## 3. 메타 검토: 문제를 어떻게 다시 정의했는가

### 잘못된 문제 정의

```text
Ollama context가 4096이라서 문제다.
→ num_ctx를 무조건 크게 올린다.
```

이 방식은 4K 모델에서는 다시 실패하고, context가 큰 모델에서도 불필요한 history를 계속 읽게 한다.

### 이번 작업에서 사용한 문제 정의

```text
모델마다 context window가 다르다.
        +
Harness가 같은 형태의 큰 projection을 보낸다.
        +
Active Context가 기존 context를 대체하지 않고 중복 추가된다.
        ↓
모델별 Working Context Compiler가 필요하다.
```

따라서 이번 작업의 목적은 context window를 크게 만드는 것이 아니라 **필요한 정보만 모델에게 보여주는 구조를 먼저 만드는 것**이다.

---

## 4. 기존 Stage 07 / 08 계약과의 적합성

### Stage 07

Stage 07의 핵심 원칙은 다음과 같다.

```text
representation 축소 가능
truth authority 변경 금지
raw evidence 삭제 금지
mandatory task/control 안전 정보 유지
```

특히 원문 observation은 artifact에 남고, prompt에는 bounded preview만 노출하도록 이미 설계돼 있다.

### Stage 08

Stage 08은 더 직접적으로 다음 구조를 가진다.

```text
full retrieval content
→ content-addressed artifact에 보존

model-visible context
→ bounded preview + artifact reference
```

따라서 향후 RAG/Wiki를 사용하더라도 저장소 전체를 매번 prompt에 넣는 것이 아니라, Stage-08 admission을 통해 필요한 일부만 가져오는 것이 기존 설계와 맞는다.

### 이번 구현의 위치

```text
Durable HarnessState / Artifact / Project Memory
                    ↓
          Stage-07 Context Projection
                    ↓
          Active Context Relevance
                    ↓
          Stage-08 Retrieval Preview
                    ↓
       Token-Aware Context Compiler   ← 이번 구현
                    ↓
          Working Context Packet
                    ↓
               LLM Actor
```

Compiler는 durable state를 수정하지 않는다.

---

## 5. 구현 내용

## 5.1 `src/harness/core/context_compiler.py`

새로운 모델-visible context compilation 계층을 추가했다.

주요 타입:

```text
RouteContextBudget
ContextCompileResult
ContextBudgetError
```

주요 책임:

```text
ModelGateway descriptor
        ↓
model route의 context budget 결정
        ↓
기존 ContextProjection 복사
        ↓
Active Context를 primary namespace에 fold
        ↓
중복/저우선순위 preview 축소
        ↓
입력 예산 안에 들어오는 첫 bounded level 선택
        ↓
Working Context v1
```

### Token estimate

현재 exact provider tokenizer에 Kernel을 결합하지 않기 위해 다음 보수적 estimator를 사용한다.

```text
estimated tokens ≈ UTF-8 bytes / 3
```

이 수치는 provider의 실제 usage를 측정하는 용도가 아니다. 모델 호출 전에 과대 prompt를 차단하기 위한 admission guard다.

향후 provider tokenizer가 안정적으로 제공되면 estimator interface를 교체할 수 있다.

---

## 5.2 모델별 context budget

현재 compiler는 ModelGateway descriptor의 default route를 본다.

명시 설정:

```toml
[models.local.options]
context_window = 8192
reserved_output_tokens = 1024
context_safety_margin_tokens = 256
```

로컬 route가 명시적으로 window를 주지 않은 경우 다음 provider/port를 보수적으로 4096으로 취급한다.

```text
provider = ollama
provider = lm-studio
port 11434
port 1234
```

이는 Ollama/LM Studio 서버 설정을 자동으로 변경한다는 의미가 아니다.

```text
context_window
= Harness compiler가 사용할 입력-budget metadata

Ollama num_ctx / 서버 설정
= 실제 provider context 설정
```

둘은 실제 운영에서 일치시켜야 한다.

---

## 5.3 출력 token reserve와 safety margin

전체 context window를 입력으로 다 사용하지 않는다.

```text
context_window
- reserved_output_tokens
- safety_margin_tokens
= max_input_tokens
```

이유는 Actor가 완전한 JSON Decision을 생성할 출력 공간을 남겨야 하기 때문이다.

이전 로컬 실행에서 JSON이 중간에 잘린 증상과 context overflow가 연속해서 나타났기 때문에, 입력을 window 끝까지 채우는 방식은 사용하지 않는다.

---

## 5.4 `active_context` 중복 제거

기존에는:

```text
trusted/untrusted 전체 bounded projection
+
active_context relevance view
```

였다.

이번 compiler에서는 route budget이 알려진 경우:

```text
active_context
→ relevant fact/hypothesis/observation 선택 신호로 사용
→ primary trusted/untrusted namespace에 fold
→ 별도 active_context namespace는 model packet에서 제거
```

즉 relevance 정보를 잃지 않으면서 같은 내용을 두 번 보여주는 문제를 줄였다.

---

## 5.5 Verified Fact 보존 정책

초기 구현 단계에서는 active context에 포함된 fact만 Working Context에 남기는 방안을 검토했다.

그러나 메타 재검토 결과 이것은 기존 Stage-07의 "current verified fact visibility" 계약과 긴장이 있었다.

따라서 최종 구현은 다음으로 수정했다.

```text
모든 current verified fact
→ key / status / authority / trust 식별자는 유지

현재 task와 관련도가 높은 fact
→ value preview + 제한된 evidence ref 유지

관련도가 낮은 fact
→ 내용은 compact stub으로 축소하거나 생략
→ fact의 존재/권위 자체는 유지
```

즉:

```text
Fact를 지움 X
Fact의 model-visible payload를 줄임 O
```

이 보정은 `tests/test_context_compiler_verified_facts.py`로 회귀 고정했다.

---

## 5.6 Untrusted / Observation / Retrieval 축소 우선

context pressure가 생기면 다음 정보가 먼저 줄어든다.

```text
hypothesis preview
observation preview
retrieval preview
failure message text
workflow 상세 text
tool description text
```

반대로 다음은 유지한다.

```text
goal_contract
verified fact identities
recovery/control state
tool names
side-effect / idempotence
input schema
trust / instruction authority boundary
artifact/content references where selected
```

이 순서는 context 절감 때문에 capability/trust 경계가 사라지지 않도록 하기 위한 것이다.

---

## 5.7 Raw Evidence는 삭제하지 않음

Compiler가 observation 또는 retrieval text를 줄여도 다음 원본은 변경하지 않는다.

```text
HarnessState
ArtifactStore
Retrieval admitted artifacts
Project Memory store
checkpoint / event history
```

따라서 필요한 정보가 Working Context에 없으면 Actor는 기존 `retrieve` 또는 workspace read tool을 사용해 다시 가져와야 한다.

SYSTEM contract에도 다음 원칙을 추가했다.

```text
필요한 evidence가 context에 없다면
추측하지 말고 retrieve/read를 사용한다.
```

---

## 5.8 `LLMController` context 전송 변경

기존:

```python
{"goal": goal, "context": context}
```

Stage-07 context 안에 이미 `goal_contract`가 존재하므로 raw goal을 sibling으로 다시 직렬화하는 것은 중복이었다.

변경 후:

```python
{"context": compiled_context}
```

만 전달한다.

효과:

1. goal text 중복 제거
2. model-visible context 경계를 Context Governor/Compiler 하나로 통일
3. raw GoalContract를 별도 숨은 경로로 직렬화하지 않음

SYSTEM prompt 자체도 동일한 authority/protocol 의미를 유지하면서 더 짧게 정리했다.

---

## 5.9 불가능한 context는 provider 호출 전에 차단

추가 회귀 테스트는 다음을 고정한다.

```text
mandatory goal/control 자체가 4K route에 들어가지 않음
        ↓
ContextBudgetError
        ↓
model.complete() 호출 횟수 = 0
```

즉 이전처럼 명백히 큰 prompt를 provider에 반복 전송하지 않는다.

현재 limitation은 `ContextBudgetError`가 runtime의 별도 first-class failure kind로 아직 승격되지 않았다는 점이다. 즉 provider request는 차단하지만 상위 recovery taxonomy는 추후 `MODEL_CONTEXT_ERROR` 또는 동등한 타입으로 분리하는 것이 더 적절하다.

---

## 6. 변경 파일

### 신규

```text
src/harness/core/context_compiler.py
tests/test_context_compiler.py
tests/test_context_compiler_verified_facts.py
tests/test_context_compiler_budget_failure.py
```

### 수정

```text
src/harness/core/controller.py
```

### 주요 구현 commit 흐름

```text
0bf7b37  feat(context): add token-aware working context compiler
d6be4e4  feat(context): compile selective model context before actor call
b3b902f  test(context): cover local token-aware context compilation
1440d6b  fix(context): preserve untrusted instruction boundary wording
0d9b473  refactor(context): preserve verified fact identities under token pressure
03aae87  test(context): preserve verified fact identities under local compaction
7313028  test(context): fail before provider on impossible local context
```

CI bot commit은 검증 결과 문서 갱신용이며 기능 구현 commit과 구분한다.

---

## 7. 검증 결과

최종 기능/test source는 다음 commit이다.

```text
7313028ba5b33b92b321528ff39315035e2e4cf0
```

Repository integration CI가 이 source를 기준으로 다음을 기록했다.

```text
Result: PASS
compile: PASS
CLI/TUI module + console: PASS
full-pytest: PASS
core-freeze-audit: PASS
Stage 02 isolation/binding: PASS
Stage 03 resume: PASS
Stage 04 semantic verification: PASS
Stage 05 recovery/adversarial/terminal: PASS
Stage 06 progress/adversarial/resume: PASS
Stage 07 context/adversarial/resume/compat/cost/goal-bounds: PASS
Stage 08 retrieval/adversarial/resume/cost/integrity: PASS
```

전체 pytest:

```text
331 passed, 7 skipped in 29.80s
```

이 결과에는 다음 신규 회귀가 포함된다.

```text
- 4096 local route의 conservative budget
- explicit context_window override
- OpenAI-compatible localhost 11434/1234 route 감지
- active_context fold 및 중복 namespace 제거
- goal_contract 유지
- 모든 tool name / safety metadata 유지
- verified fact identity 전체 유지
- relevant fact preview/evidence 우선 유지
- remote route metadata 미지정 시 passthrough
- LLMController의 duplicate raw goal 제거
- 4K에 절대 맞지 않는 mandatory context는 provider 호출 전에 차단
```

따라서 현재 repository evidence 기준으로 이번 구현은 **compile/full regression 및 기존 Stage 02~08 gate를 깨지 않고 PASS**했다.

---

## 8. RAG / Wiki / Memory를 이번 단계에서 추가하지 않은 이유

현재 문제의 원인은 검색 능력이 부족해서가 아니라 **이미 선택된 정보까지 중복해서 prompt에 넣는 것**이었다.

따라서 먼저 다음을 해결해야 한다.

```text
전체 context를 작게 만든다
        ↓
필요한 과거 정보만 retrieval한다
        ↓
그래도 lexical retrieval 품질이 부족한지 측정한다
        ↓
그때 Vector RAG / Wiki index를 검토한다
```

지금 Vector RAG를 추가하면:

```text
기존 context
+ active_context
+ vector result
```

이 되어 오히려 prompt가 커질 수 있다.

Stage 08은 이미 retrieval provider를 교체할 수 있는 계약을 제공한다. 따라서 Vector RAG/Wiki가 필요하다는 실증이 나오면 같은 admission interface 뒤에 provider로 추가하는 것이 적절하다.

---

## 9. 예상 전체 흐름

변경 후 목표 구조는 다음과 같다.

```text
User Goal
   ↓
Task Intake / Workspace
   ↓
Verified-State / Evidence / History
   ↓
Stage-07 Context Projection
   ↓
Active Relevance + Stage-08 Retrieval
   ↓
Model Route Budget
   ↓
Token-Aware Context Compiler
   ↓
Working Context Packet
   ↓
LLM Actor
   ↓
Canonical Decision
   ↓
Tool / Evidence / Verification
   ↓
새 durable state
```

과거 기록은 계속 저장되지만 LLM은 현재 판단에 필요한 subset만 읽는다.

---

## 10. 메타 재검토

### 10.1 설계가 기존 architecture를 약화시키는가?

판정: **아니오.**

이유:

- Context Compiler는 durable state를 수정하지 않는다.
- retrieval/memory trust가 올라가지 않는다.
- verified fact authority를 재계산하지 않는다.
- progress/completion authority를 추가하지 않는다.
- tool execution permission을 변경하지 않는다.
- raw evidence를 삭제하지 않는다.

### 10.2 Active Context를 단순 추가하는 것보다 나은가?

판정: **토큰 절감 목적에서는 더 적절하다.**

Active Context는 relevance signal로는 유효하지만 additive 상태에서는 base projection과 중복된다. 이번 compiler는 active relevance를 최종 working packet의 선택 기준으로 사용한다.

### 10.3 Context를 무조건 크게 늘리는 것보다 나은가?

판정: **기본 전략으로 더 적절하다.**

Context window 증가는 필요 시 사용할 수 있지만, 관련 없는 history를 매번 읽게 하는 문제를 해결하지 않는다. Compiler가 먼저 context를 줄인 뒤 실제 workload evidence에 따라 8K/16K가 필요한지 판단하는 것이 비용·성능 원인을 분리하기 쉽다.

### 10.4 RAG/Wiki를 지금 함께 넣어야 하는가?

판정: **아직 아니다.**

먼저 Working Context token/완료율을 측정해야 한다. lexical/project-memory retrieval이 부족하다는 실제 실패가 나온 뒤 vector 또는 linked Wiki retrieval을 추가해야 설계 효과를 분리해 측정할 수 있다.

---

## 11. 남은 한계와 다음 검증

### 현재 한계

1. token estimate는 provider tokenizer exact count가 아니라 UTF-8 기반 보수적 추정이다.
2. local default 4096은 Harness 쪽 보수적 admission 값이다. 실제 서버 설정을 자동 변경하지 않는다.
3. `ContextBudgetError`는 provider 호출 전에 차단되지만 runtime failure taxonomy에는 아직 전용 context/model failure kind가 없다.
4. remote provider가 `context_window` metadata를 주지 않으면 기존 projection passthrough를 유지한다.
5. compact된 verified fact의 상세 값을 semantic key로 즉시 expand하는 별도 tool은 아직 없다. 원본 evidence/retrieval 경로를 사용한다.
6. 실제 Ollama/LM Studio E2E에서 token reduction과 verified completion 개선 정도는 별도 benchmark가 필요하다.

### 다음 측정 항목

```text
source estimated input tokens
compiled estimated input tokens
실제 provider input tokens
context overflow rate
protocol repair rate
steps to first useful tool action
verified completion rate
retrieval 횟수
재조회 때문에 증가한 총 token 비용
```

목표는 단순히 prompt를 가장 작게 만드는 것이 아니다.

> **필요한 evidence를 잃지 않으면서 verified completion까지의 총 context/token 비용을 줄이는 것**이 최종 평가 기준이어야 한다.

---

## 12. 결론

이번 변경은 기존 Context Governance / Retrieval / Project Memory를 폐기하거나 대체하지 않는다.

기존 구조에 빠져 있던 마지막 model-facing 조립 단계를 추가했다.

```text
과거 기록과 evidence는 보존
        ↓
관련성에 따라 선택
        ↓
모델별 context budget에 맞춰 축약
        ↓
LLM은 작은 Working Context만 읽음
        ↓
필요한 원문은 retrieve/read
```

이 구조는 향후 Wiki/Vector RAG를 넣더라도 그대로 유지할 수 있다. Wiki/RAG는 저장·검색 provider가 되고, 최종적으로 LLM에게 얼마를 보여줄지는 Context Compiler가 계속 통제하는 것이 적절하다.
