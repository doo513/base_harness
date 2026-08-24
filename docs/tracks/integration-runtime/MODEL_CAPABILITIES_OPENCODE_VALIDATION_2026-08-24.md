# Model Capability / OpenCode Adapter 검증 기록 — 2026-08-24

## 검증 대상

기능 및 테스트가 모두 포함된 source commit:

```text
07fb36cb8ef3aeae0162d6051b55d702f4e9c503
```

포함 변경:

```text
src/harness/model_capabilities.py
src/harness/opencode_adapter.py
tests/test_model_capabilities.py
tests/test_opencode_adapter.py
harness.example.toml
```

## 독립 smoke

`model_capabilities.py`를 별도 Python 환경에서 parse/execute하여 다음을 확인했다.

```text
model_tiering = disabled
OpenCode adapter tool_execution_boundary = harness_only
OpenCode native_tool_calling = false
custom reasoning capability override 반영
runtime failure_rate 계산
```

결과:

```text
model_capabilities_smoke PASS
static_parse_smoke PASS
```

## Repository CI

`docs/tracks/integration-runtime/CI_STATUS.md`가 source commit `07fb36c...`에 대해 다음을 기록했다.

```text
Result                                            PASS
compile                                           PASS
CLI/TUI                                           PASS
full pytest                                       PASS
Stage 02 isolation/binding                        PASS
Stage 03 resume                                   PASS
Stage 04 semantic verification                    PASS
Stage 05 recovery                                 PASS
Stage 06 progress                                 PASS
Stage 07 context                                  PASS
Stage 08 retrieval/integrity                      PASS
```

전체 pytest:

```text
338 passed, 7 skipped in 30.18s
```

이전 검증 baseline은 `331 passed, 7 skipped`였으므로 신규 capability/OpenCode 테스트가 추가된 상태에서도 전체 회귀가 유지됐다.

## 검증 해석

확정 가능한 범위:

- 모델 tier 없이 capability/constraint snapshot 생성 경로가 회귀 테스트를 통과함.
- OpenCode JSONL parser와 Decision schema 검증이 통과함.
- OpenCode 내부 `tool_use` reject가 테스트됨.
- `permission=deny`, temporary workspace, no `--dangerously-skip-permissions` 계약이 테스트됨.
- 기존 Context/Memory/Verification/Recovery 경계가 전체 CI에서 회귀하지 않음.

아직 확정하지 않는 범위:

- 실제 사용자의 OpenCode 설치본 + 실제 provider/model을 사용한 live E2E 성공률.
- OpenCode JSONL의 플랫폼별 장시간 안정성.
- 조직 managed OpenCode config가 존재하는 환경에서의 강한 OS sandbox 보장.

따라서 현재 상태는 **adapter 구현 및 repository regression PASS**이며, 실제 OpenCode 모델의 성능 평가는 별도 live benchmark 대상으로 남긴다.
