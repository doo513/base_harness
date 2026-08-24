# OpenCode Model Catalog Selection — 2026-08-24

## 1. 목적

이번 변경의 목표는 `base_harness`에서 OpenCode를 coding-agent 실행기로 사용하는 것이 아니라, **OpenCode가 제공하는 모델 catalog에서 underlying model을 선택하고 그 모델을 Harness의 Actor model transport로 고정해서 사용하는 것**이다.

요구사항은 다음 세 가지로 정리했다.

```text
1. 로컬 모델은 현재 실험 기준으로 안정성이 부족하다.
2. 비교 실험에서는 하나의 OpenCode 무료 모델을 고정해 사용한다.
3. Harness 기능으로는 OpenCode model을 다시 선택/교체할 수 있어야 한다.
```

따라서 설계 원칙은 다음과 같다.

> **Discovery는 동적이지만, 한 run/실험에서 사용하는 model identity는 config에 고정한다.**

---

## 2. OpenCode 근거

OpenCode CLI는 모델을 `provider/model` 형식으로 식별하고 다음 명령을 제공한다.

```text
opencode models [provider]
opencode models [provider] --verbose
opencode models [provider] --refresh
```

OpenCode source의 `packages/opencode/src/cli/cmd/models.ts` 기준으로 `--verbose`는 각 `provider/model` 식별자 뒤에 model metadata JSON을 출력한다.

또한 `opencode run`은 다음처럼 underlying model을 명시적으로 받을 수 있다.

```text
opencode run --model provider/model
```

참조:

- https://opencode.ai/docs/cli/
- https://opencode.ai/docs/models/
- https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/cli/cmd/models.ts

따라서 Harness가 model catalog를 직접 새로 정의할 필요 없이 OpenCode의 현재 catalog를 discovery source로 사용할 수 있다.

---

## 3. 전체 흐름

```text
verified-harness-tui
        ↓
/model opencode
        ↓
opencode models opencode --verbose
        ↓
OpenCode catalog parser
        ↓
FREE / paid / cost-unknown 표시
        ↓
사용자 model 선택
        ↓
harness.toml [models.opencode] 갱신
        ↓
default_model = "opencode"
        ↓
ModelGateway / CommandProvider
        ↓
opencode_adapter
        ↓
opencode run
  --model <고정 provider/model>
  --agent harness-model
        ↓
Harness Decision JSON
        ↓
기존 Harness Tool Runtime / Verification
```

OpenCode catalog는 **선택 시점에만** 조회한다.

실제 task loop에서 매 step마다 `opencode models`를 다시 호출하지 않는다.

---

## 4. TUI 사용법

### catalog 열기

```text
/model opencode
```

또는 compatibility alias:

```text
/models opencode
/change opencode
```

### catalog refresh 후 선택

```text
/model opencode refresh
```

### 정확한 model id를 알고 있을 때

```text
/model opencode/<model-id>
```

정확한 ref가 현재 catalog에 없으면 fail-closed한다.

TUI는 현재 `opencode` provider catalog를 사용한다. 이는 OpenCode Zen 계열 모델을 실험 대상으로 쓰려는 현재 목적에 맞춘 기본 scope다.

별도 CLI selector도 제공한다.

```bash
python -m harness.opencode_selection harness.toml
```

provider scope를 바꾸려면:

```bash
python -m harness.opencode_selection harness.toml --provider <provider>
```

---

## 5. 무료 모델 판정 정책

무료 여부는 model 이름이나 누락된 cost metadata로 추측하지 않는다.

```text
input cost가 명시적으로 0
AND
output cost가 명시적으로 0
        ↓
explicitly_free = true
```

반대로 cost metadata가 없으면:

```text
explicitly_free = unknown
```

으로 둔다.

이유는 OpenCode/model metadata 생태계에서 cost omission이 실제 무료를 의미한다고 보장할 수 없기 때문이다.

따라서 TUI는 다음 순서로 표시한다.

```text
1. 명시적으로 FREE
2. cost unknown
3. 명시적 paid
```

실험에서는 이 중 `FREE`로 명시된 하나를 선택해 model id를 고정하는 것이 권장된다.

---

## 6. Config에 무엇을 고정하는가

선택 후 다음과 같은 route가 생성/갱신된다.

```toml
[models.opencode]
provider = "command"
model = "opencode/<selected-model>"
command = "... harness.opencode_adapter ... --model opencode/<selected-model> ..."
timeout_seconds = 240

[models.opencode.options]
adapter = "opencode"
catalog_provider = "opencode"
catalog_model_id = "<selected-model>"
opencode_agent = "harness-model"
context_window = <catalog context limit when available>
catalog_input_limit = <when available>
catalog_output_limit = <when available>
catalog_explicitly_free = true # only when explicitly known
catalog_cost_input = 0
catalog_cost_output = 0
reserved_output_tokens = <derived reserve>
context_safety_margin_tokens = <derived margin>
context_safety_margin_source = "opencode_adapter_overhead_guard"
```

그리고:

```toml
default_model = "opencode"
```

로 변경된다.

이 정보는 `ModelGateway.descriptor()`와 revision에 들어가므로, 선택된 underlying model identity와 관련 config가 run provenance에 반영된다.

즉:

```text
catalog가 이후 변경됨
≠
기존 실험 run의 model이 자동 변경됨
```

이다.

---

## 7. OpenCode를 가능한 한 "모델만" 사용하기 위한 경계

OpenCode는 본래 coding agent이므로 단순 raw model API와 동일하지 않다.

특히 built-in `plan` agent를 사용하면 OpenCode의 planning prompt/behavior가 실험 결과에 추가로 섞일 수 있다.

따라서 adapter는 이제 자체 inline agent를 사용한다.

```text
agent name = harness-model
mode       = primary
permission = * deny
```

agent prompt도 decision transport 역할만 짧게 지정한다.

동시에 global permission도 deny하며 JSONL에서 `tool_use` event가 관찰되면 결과를 reject한다.

```text
OpenCode file/edit/bash/web/subagent execution  → DENY
OpenCode internal tool_use event                 → reject
OpenCode text decision                           → validate
Harness ActionRuntime                            → 기존 policy에 따라 실행
```

OpenCode agent 설정이 custom prompt와 permissions를 지원하는 것은 현재 OpenCode agent source와 문서에서 확인 가능하다.

참조:

- https://github.com/anomalyco/opencode/blob/dev/packages/opencode/src/agent/agent.ts
- https://opencode.ai/docs/agents/

### 중요한 한계

이 구조가 OpenCode를 **완전한 raw inference API**로 바꾸는 것은 아니다.

OpenCode 자체의 공통 runtime/system envelope가 여전히 존재할 수 있다. 따라서 benchmark 결과는 정확히 다음 실험으로 해석해야 한다.

```text
selected underlying model
+ OpenCode transport/runtime
+ base_harness
```

이지, underlying model 단독 benchmark라고 부르면 안 된다.

다만 built-in coding/planning agent와 tool execution을 제거해 OpenCode 영향은 이전 adapter보다 줄였다.

---

## 8. Context budget 보정

OpenCode catalog가 예를 들어 `context=131072`를 보고해도, 그 전체를 base_harness prompt 입력으로 사용할 수 있다고 가정하지 않는다.

OpenCode 자체 envelope가 추가되기 때문이다.

따라서 선택 시 다음 값을 별도로 둔다.

```text
catalog context limit
- Harness output reserve
- OpenCode adapter safety margin
= Harness max input budget
```

현재 safety margin은 모델 context에 따라 bounded하게 계산한다.

```text
min(4096, max(512, context_window / 16))
```

이는 OpenCode 실제 system-token 크기의 정확한 측정값이라고 주장하지 않는다.

목적은 catalog context를 그대로 전부 사용해 다시 context-overflow가 발생하는 것을 막는 보수적 guard다.

실제 token 사용은 향후 real OpenCode E2E에서 telemetry로 측정해야 한다.

---

## 9. 구현 파일

### 신규

```text
src/harness/opencode_selection.py
src/harness/tui_entry.py

tests/test_opencode_selection.py
tests/test_tui_opencode_model_selector.py
tests/test_opencode_model_only_boundary.py
```

### 수정

```text
src/harness/opencode_adapter.py
pyproject.toml
harness.example.toml
```

TUI console entrypoint:

```text
verified-harness-tui
→ harness.tui_entry:main
→ 기존 tui_conversation.main
```

즉 기존 runtime/TUI 구현을 교체하지 않고 model-selection integration layer만 앞에 composition했다.

---

## 10. 테스트에서 고정한 계약

### Catalog

- `provider/model` + verbose metadata parse
- context/input/output limits parse
- explicit zero input/output cost만 FREE
- missing cost는 FREE로 추정하지 않음
- `--refresh`, provider scope, `shell=False`

### Persistence

- 선택 model id가 `models.opencode.model`에 저장됨
- `default_model=opencode`
- 같은 alias 재선택은 기존 OpenCode route를 교체
- non-OpenCode route와 alias collision 시 fail-closed
- catalog context/cost snapshot 저장

### TUI

- `/model opencode` catalog selection
- explicitly-free model 우선 표시
- exact `opencode/<id>` 선택
- 기존 Ollama/API model switching은 기존 handler로 위임
- console entrypoint만 composition하고 Harness runtime을 대체하지 않음

### Model-only boundary

- custom `harness-model` primary agent 존재
- agent-level `* = deny`
- global permission deny
- default OpenCode run이 `--agent harness-model`
- selected `--model provider/model` 사용

---

## 11. 검증 상태

중간 구현 source `49763f45ca3cb13585c6b586d0310dceb963e4c3` 기준 GitHub integration CI 결과:

```text
Result: PASS
compile: PASS
CLI/TUI module + console: PASS
full pytest: 350 passed, 7 skipped
Stage 02~08 gates: PASS
```

이 결과에는 catalog selection, TUI switching, minimal `harness-model` boundary가 포함된다.

이 문서 직전의 소규모 help/example 정리 변경은 기능 authority를 바꾸지 않지만 최종 branch CI 상태를 별도로 확인한다.

---

## 12. 아직 검증하지 않은 것

다음을 완료했다고 주장하지 않는다.

```text
실제 사용자 PC의 OpenCode 설치 탐지
실제 OpenCode 로그인/Zen 계정 인증
실제 현재 무료 model에 대한 live inference E2E
실제 OpenCode overhead token 수치 측정
모델별 benchmark 결과
```

현재 CI는 subprocess boundary와 OpenCode output format을 mock/fake event로 검증한다.

따라서 다음 실험 단계는 실제 환경에서:

```text
1. opencode models opencode --verbose 확인
2. FREE 모델 하나 선택
3. 같은 task set을 model id 고정 상태로 반복 실행
4. valid decision rate / tool transition rate / completion rate / token usage 측정
```

하는 것이다.

---

## 13. 최종 판단

현재 요구에는 다음 구조가 가장 적합하다.

```text
OpenCode catalog는 model discovery 용도
             ↓
선택된 하나의 free model은 experiment config에 고정
             ↓
OpenCode는 tool 없는 model transport로 사용
             ↓
실제 행동/검증은 base_harness가 담당
```

이렇게 하면 로컬 모델의 현재 불안정성을 우회하면서도, 향후 OpenCode의 다른 무료/유료 model로 교체 가능한 Harness 기능을 유지할 수 있다.
