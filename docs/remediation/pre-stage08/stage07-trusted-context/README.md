# Stage07 remediation — Bounded Model-Visible Trusted Context

Finding ID: `R07-CONTEXT-001`  
Status: **PASS for trusted-fact projection boundary**

## 문제

기존 Context Governor는 hypotheses, observations, failures, tool descriptions 등 untrusted/control 주변 데이터를 상당히 잘 bound했다. 하지만 current verified facts는 `_project_facts()`에서 거의 전체 `claim.dump()` 형태로 model-visible `trusted.facts`에 들어갔다.

따라서 durable facts가 많아지거나 verified value가 커지면:

```text
verified state growth
→ model-visible trusted payload growth
→ prompt/context expansion
```

이 직접 발생했다.

중요한 점은 해결을 위해 durable verified truth를 삭제하거나 임의 요약하면 안 된다는 것이다. 따라서 **truth storage와 model projection을 분리**했다.

## 조치

ContextPolicy에 trusted-fact projection bound를 추가했다.

- maximum visible verified fact count
- per verified value character bound
- total verified value character bound
- verified key character bound
- superseded key list bound

큰 value는 다음과 같은 bounded representation을 사용한다.

```text
stable projected identity
key/key preview
status
verified authority
bounded value preview
value content hash
evidence metadata
```

작은 scalar는 기존 controller/model compatibility를 위해 exact `value`를 유지할 수 있다.

Durable `HarnessState.facts` 자체는 context 절감을 위해 삭제/변형하지 않는다.

## Determinism / selection

단순 insertion order가 model context를 결정하지 않도록 stable deterministic ordering을 사용한다. 제한 때문에 일부 fact를 projection에서 생략해야 할 경우 authority/identity 기준이 재현 가능해야 한다.

비정상적으로 큰 key 역시 그대로 model payload를 팽창시키지 않고 bounded/stable identity를 사용한다.

## Compatibility boundary

Stage07의 기존 compatibility 요구를 유지했다.

- model JSON에는 governed namespaced projection만 노출.
- moved legacy Python controller read snapshot은 model serialization에 들어가지 않음.
- same-key `tools` 등은 Python/JSON split-brain을 만들지 않음.
- existing Stage07 base/adversarial/resume/compat probes를 그대로 재실행.

## Evidence

CI gate 추가: `4f31b13...`  
main hardening: `329f9d52...`

새 direct probes:

- trusted-context growth probe
- trusted-context cost probe

기존 probes:

- context projection
- adversarial context
- context resume
- compatibility projection

최종 integration CI `31950971636`에서 위 6개 Stage07 gate와 Stage02~08 prior gates가 모두 SUCCESS.

## 무엇을 증명하는가

- verified durable state가 커져도 model-visible trusted-fact projection은 policy bound를 가진다.
- context 절감을 위해 durable verified fact를 삭제하지 않는다.
- policy 변경은 runtime config semantics에 포함되어 resume equivalence를 보호한다.
- 기존 compatibility boundary를 유지한다.

## 무엇을 아직 증명하지 않는가

이번 수정은 **trusted facts**의 projection growth를 직접 다룬다.

다음은 별도 entry/control hardening 범위다.

- 비정상적으로 거대한 goal/acceptance/constraints 자체.
- 모든 mandatory control payload의 universal byte hard-cap.
- content-addressed externalization을 포함한 장문 goal contract 설계.

이들은 `../04_OPEN_ITEMS.md`에 유지한다.
