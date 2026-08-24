# OpenCode Persistent Auth `/connect` 구현 보고서 — 2026-08-24

## 목적

`base_harness` TUI에서 OpenCode 모델을 사용할 때 매 실행마다 API key를 다시 입력하지 않도록 `/connect opencode`를 OpenCode의 공식 persistent authentication과 연결했다.

핵심 원칙은 다음과 같다.

```text
Harness가 API key를 저장하지 않는다.
        ↓
/connect opencode
        ↓
opencode auth login --provider opencode
        ↓
OpenCode가 직접 key 입력/저장
        ↓
Harness는 인증 상태만 확인
        ↓
/model opencode
        ↓
선택된 provider/model만 harness.toml에 고정
```

## 공식 근거

OpenCode 공식 CLI 문서는 다음을 명시한다.

- `opencode auth login`으로 provider credentials를 설정할 수 있다.
- `--provider` 플래그로 로그인 provider를 지정할 수 있다.
- credentials는 OpenCode의 persistent auth store에 저장된다.
- `opencode auth list`로 저장된 authenticated provider를 확인할 수 있다.
- OpenCode Zen은 `/connect` 후 API key를 입력하고 `/models`에서 모델을 선택하는 흐름을 사용한다.

참조:

- https://opencode.ai/docs/cli/
- https://opencode.ai/docs/providers/

## 구현

### `src/harness/opencode_auth.py`

신규 persistent-auth bridge를 추가했다.

주요 기능:

```text
parse_auth_list()
opencode_auth_status()
login_opencode_provider()
is_opencode_authenticated()
```

`login_opencode_provider()`는 다음 명령을 실행한다.

```text
opencode auth login --provider opencode
```

중요하게도 subprocess의 stdin/stdout/stderr를 캡처하지 않는다. 따라서 API key는 OpenCode의 공식 terminal prompt에 직접 입력되고 다음 경로를 통과하지 않는다.

```text
Harness argv       X
Harness TOML       X
Harness subprocess input  X
Harness captured stdout   X
Harness env mutation      X
```

OpenCode login이 성공하면 같은 TUI session에는 비밀이 아닌 다음 sentinel만 저장한다.

```text
HARNESS_OPENCODE_AUTH_OK=1
```

이 값은 credential이 아니며 OpenCode auth command를 같은 TUI session에서 불필요하게 다시 실행하지 않기 위한 상태 표시다.

## TUI `/connect`

`src/harness/tui_entry.py`에서 기존 `/connect` 흐름을 확장했다.

### 명시적 연결

```text
/connect opencode
```

동작:

1. `opencode auth list`로 기존 인증 여부 확인
2. 이미 인증됐으면 재입력하지 않음
3. 인증이 없으면 `opencode auth login --provider opencode` 실행
4. OpenCode가 key를 persistent store에 저장
5. Harness는 다음 모델 선택 안내

### provider 선택 화면

기존 route가 없는 상태에서 `/connect`만 입력하면 provider prompt에 `opencode`가 포함된다.

```text
Provider (opencode|gemini|openai|ollama|openai-compatible)
```

### 실행 전 확인

선택된 default route가 OpenCode인데 인증이 확인되지 않으면 실제 Harness run을 시작하기 전에 OpenCode auth flow를 실행한다.

즉 config에 OpenCode model route가 존재한다는 사실만으로 인증 성공을 가정하지 않는다.

## 모델 설정과 credential의 분리

`harness.toml`에는 기존 OpenCode model selector가 선택한 model ID와 context/cost metadata가 저장된다.

예:

```toml
default_model = "opencode"

[models.opencode]
provider = "command"
model = "opencode/<selected-model>"
command = "... harness.opencode_adapter ... --model opencode/<selected-model> ..."
```

API key는 이 TOML에 저장하지 않는다.

따라서 역할은 다음과 같이 분리된다.

```text
OpenCode auth store
= persistent credential source

harness.toml
= selected model / experiment configuration

base_harness run artifacts
= run/evidence/model revision
```

이 구조는 key 재입력을 제거하면서도 실험 model configuration을 재현 가능하게 유지한다.

## 테스트

추가:

```text
tests/test_opencode_auth.py
tests/test_tui_opencode_connect.py
```

수정:

```text
tests/test_tui_opencode_model_selector.py
```

검사 항목:

- `auth list` provider detection
- official `auth login --provider opencode` argv
- secret이 subprocess input/capture에 전달되지 않음
- 이미 persistent auth가 있으면 login 재실행하지 않음
- TUI session에는 non-secret sentinel만 저장
- `/connect` provider prompt에 OpenCode 포함
- OpenCode route 실행 전 auth 확인
- auth missing 시 run 전에 connect flow 실행
- 기존 model selector/TUI composition 유지

## 검증 결과

기능 source commit:

```text
dc5b3988b82737ab1eb9317c7895b5e56eddf104
```

Repository integration CI:

```text
Result: PASS
compile: PASS
cli/tui module + console: PASS
full pytest: 360 passed, 7 skipped
Stage 02~08 gates: PASS
```

## 한계

CI 환경에는 사용자의 실제 OpenCode credential이 없으므로 실제 OpenCode Zen API key를 이용한 live inference까지 성공했다고 주장하지 않는다.

현재 검증한 범위는:

```text
OpenCode official auth command delegation
persistent-auth detection contract
TUI integration
secret non-persistence in Harness config/session
pre-run auth gate
existing Harness regression
```

실제 사용자 환경에서는 최초 한 번:

```text
/connect opencode
/model opencode
```

을 수행한 뒤 이후 TUI 재시작에서도 OpenCode가 저장한 credential을 재사용하는 것이 의도한 최종 흐름이다.
