# Model Capability Inspection + OpenCode Decision Adapter — 2026-08-24

## 1. 목적

이번 변경은 모델을 `SLM / 대형 모델 / 로컬 / 원격` 같은 성능 등급으로 분류하지 않는다.

대신 Harness가 실제로 사용할 수 있는 **기능(feature), 제약(constraint), 관측된 실패율(observed runtime signal)** 을 별도로 기술한다.

핵심 원칙:

```text
Local != SLM != weak model
Model size != Harness protocol capability
```

따라서 7B 로컬 모델과 34B 로컬 모델을 같은 성능 등급으로 묶지 않는다. 같은 모델이라도 provider/endpoint/config에 따라 structured output, context window, reasoning 노출 방식 등이 달라질 수 있기 때문이다.

---

## 2. 근거

### base_harness 기존 상태

기존 `ProviderCapabilities`는 이미 다음 transport capability를 갖고 있었다.

```text
structured_output
native_tool_calling
streaming
vision
reasoning
```

또한 Token-Aware Context Compiler는 `context_window`, output reserve, safety margin을 이용한다.

따라서 새로운 모델 intelligence tier를 추가하는 것보다 기존 provider/config/runtime evidence를 한 곳에서 조회할 수 있게 만드는 것이 구조적으로 더 작고 안전하다.

### OpenCode 공식 구조

OpenCode 공식 문서는 다음을 제공한다.

- automation용 `opencode run`
- `--format json` raw JSON event output
- `--model provider/model`
- `--agent`
- headless server / SDK
- permission의 `allow / ask / deny`
- inline config `OPENCODE_CONFIG_CONTENT`

참조:

- https://opencode.ai/docs/cli/
- https://opencode.ai/docs/permissions/
- https://opencode.ai/docs/config/
- https://opencode.ai/docs/sdk/
- https://github.com/anomalyco/opencode

현재 OpenCode source의 `run.ts`는 stdin이 TTY가 아니면 piped stdin을 읽어 run input으로 사용할 수 있다.

OpenCode는 자체적으로 file/edit/bash/web/subagent 도구를 실행하는 coding agent이므로, 이를 base_harness의 일반 Model Provider처럼 unrestricted하게 실행하면 다음 기존 경계를 우회할 수 있다.

```text
LLM proposal
→ Harness capability/tool runtime
→ observation/evidence
→ verification
```

따라서 이번 통합은 OpenCode의 자체 실행 능력을 base_harness에 위임하지 않는다.

---

## 3. Model Capability Inspector

신규 파일:

```text
src/harness/model_capabilities.py
```

출력 schema:

```text
model-capability-snapshot-v1
```

각 route에 대해 다음을 기록한다.

### 기능

```text
structured_output
native_tool_calling
streaming
vision
reasoning
```

### 제약

```text
context_window
reserved_output_tokens
context_safety_margin_tokens
timeout_seconds
decision_protocol
tool_execution_boundary
```

### 실행 위치

```text
local_process
local_endpoint
remote_endpoint
unspecified
```

이 값은 모델의 지능 평가가 아니라 transport/runtime topology 정보다.

### 명시적으로 저장하지 않는 것

```text
model_tier = null
model_size_class = null
intelligence_classification = none
```

즉 7B/34B 등의 parameter count를 기준으로 Harness behavior를 강제하지 않는다.

---

## 4. Custom provider override

알려지지 않은 provider 또는 adapter는 config에서 feature를 명시할 수 있다.

```toml
[models.example.options]
capability_structured_output = true
capability_native_tool_calling = false
capability_streaming = false
capability_vision = false
capability_reasoning = true
```

이 값도 "성능 등급"이 아니라 해당 route가 Harness에 제공한다고 선언한 protocol capability다.

---

## 5. Runtime observation

Inspector는 `ModelGateway.telemetry_snapshot()`이 있으면 다음 aggregate 값을 함께 기록한다.

```text
requests
failures
protocol_repairs
failure_rate
protocol_repair_rate
last_provider
last_model
last_error_kind
```

중요:

```text
failure_rate가 높음
!=
모델 등급을 자동으로 낮춤
```

현재는 관측만 한다. 이후 실제 E2E benchmark에서 threshold가 검증되기 전까지 자동 모델 등급 또는 자동 protocol downgrade에는 사용하지 않는다.

CLI:

```bash
python -m harness.model_capabilities harness.toml
```

---

## 6. OpenCode 통합 방식

신규 파일:

```text
src/harness/opencode_adapter.py
```

OpenCode를 새 Kernel/tool runtime으로 넣지 않는다.

구조:

```text
LLMController
    ↓
ModelGateway CommandProvider
    ↓ stdin: Harness system + compiled context
OpenCode decision adapter
    ↓
opencode run --format json
    ↓
JSONL text event
    ↓
Harness Decision validation
    ↓
CommandProvider stdout
    ↓
LLMController
    ↓
Harness Tool Runtime / Verification
```

즉 OpenCode는 **Decision 생성 transport**로만 사용한다.

---

## 7. OpenCode tool boundary

Adapter 실행 시:

```text
OPENCODE_CONFIG_CONTENT={permission: deny, ...}
```

를 강제하고, 빈 temporary directory에서 실행한다.

또한:

```text
--dangerously-skip-permissions
```

를 절대 사용하지 않는다.

OpenCode JSONL에서 `tool_use` event가 확인되면 결과를 폐기한다.

따라서 의도한 실행 계약은 다음이다.

```text
OpenCode 내부 tool execution     DENY
OpenCode가 Harness tool을 직접 실행  DENY
OpenCode가 JSON으로 tool 요청 제안   ALLOW
base_harness ActionRuntime 실행      ALLOW under existing policy
```

### 제한

OpenCode config 문서상 managed/admin config는 일반 inline config보다 높은 우선순위를 가질 수 있다. 그러므로 조직 관리 환경에서 tool deny가 외부 정책으로 override되는 구성이 있다면 이 adapter를 강한 sandbox로 간주해서는 안 된다.

현재 adapter의 보안 목적은 OpenCode의 정상 permission contract에서 tool execution을 차단하는 것이다. OS-level process sandbox를 새로 제공하는 기능은 아니다.

---

## 8. OpenCode JSONL fail-closed

OpenCode의 `run --format json`은 automation interface로 제공되지만 2026년에는 일부 환경에서 마지막 `text` 또는 `step_finish` event가 누락되는 이슈가 보고됐다.

참조 사례:

- https://github.com/anomalyco/opencode/issues/26855
- https://github.com/anomalyco/opencode/issues/31435
- https://github.com/anomalyco/opencode/issues/29866

따라서 adapter는:

```text
text event 없음
→ 성공으로 추정하지 않음
→ OpenCodeAdapterError
```

으로 처리한다.

`tool_use`, session error, malformed JSONL, schema-invalid Harness Decision도 동일하게 reject한다.

---

## 9. 설정 예시

OpenCode 설치 및 provider auth는 OpenCode 자체 방식으로 먼저 구성한다.

예:

```toml
[models.opencode]
provider = "command"
command = "python -m harness.opencode_adapter --model ollama/gemma3:latest --agent plan"
timeout_seconds = 240

[models.opencode.options]
adapter = "opencode"
context_window = 8192
reserved_output_tokens = 1024
context_safety_margin_tokens = 256
```

그 후:

```toml
default_model = "opencode"
```

로 선택할 수 있다.

`context_window`는 OpenCode의 크기를 의미하지 않는다. **OpenCode가 실제 사용하는 underlying model의 context window와 맞춰야 하는 Harness-side metadata**다.

---

## 10. 왜 `provider = opencode`를 새로 만들지 않았는가

이번 단계에서는 의도적으로 기존 `CommandProvider`를 재사용한다.

이유:

1. OpenCode는 LLM API provider가 아니라 별도 coding agent runtime이다.
2. OpenCode가 provider registry 안에서 일반 LLM과 동일하게 보이면 자체 tool authority가 숨겨질 수 있다.
3. command transport는 subprocess 경계를 명확히 보여준다.
4. adapter가 최종 JSON Decision 하나만 stdout으로 돌려주므로 기존 Controller contract를 재사용할 수 있다.
5. OpenCode API/SDK가 변경돼도 Kernel/ModelGateway provider contract를 직접 흔들지 않는다.

OpenCode 공식 SDK/server API는 향후 JSONL CLI의 안정성 문제가 실제 운영 병목으로 확인될 때 별도 provider adapter 후보로 검토한다.

---

## 11. 테스트 추가

```text
tests/test_model_capabilities.py
tests/test_opencode_adapter.py
```

검사 내용:

### Capability

- model tier/class가 생성되지 않음
- OpenCode adapter가 `harness_only` tool boundary로 표시됨
- Ollama reasoning/context 제약 표시
- custom capability override
- observed failure/protocol repair rate 계산

### OpenCode

- JSONL text → canonical Harness Decision
- token usage parsing
- internal `tool_use` reject
- no-text JSONL fail-closed
- schema-invalid decision reject
- temporary workspace 사용
- inline `permission=deny`
- `--dangerously-skip-permissions` 미사용
- piped stdin transport

---

## 12. 현재 설계 판단

최종 구조는 다음이다.

```text
Model route
  ├─ provider / adapter
  ├─ features
  ├─ context/output constraints
  └─ observed protocol failures
          ↓
Harness adaptation inputs
```

아래 구조는 사용하지 않는다.

```text
7B → weak
34B → strong
local → SLM
remote → strong
```

따라서 향후 로컬 34B, 원격 소형 모델, OpenCode를 통한 여러 provider 모델 모두 같은 contract 아래 비교할 수 있다.
