# 03 — Validation Ledger

이 ledger는 “무엇을 수정했는가”보다 **어떤 evidence까지 확보되어 현재 어떤 수준의 주장을 할 수 있는가**를 기록한다.

## 1. Current validated head

- branch: `research/verified-state-stage03`
- validated hardening head: `329f9d52d704ce6af4726d41e7f30745fccdd66d`
- final integration workflow: `31950971636`
- result: **SUCCESS**

해당 workflow에서 성공한 gate:

- Full pytest regression
- Stage03 resume probe
- Stage04 semantic probe
- Stage05 recovery / adversarial / terminal / crash-window / strategy probes
- Stage06 base / adversarial / resume / boundary / strategy probes
- Stage07 base / adversarial / resume / compatibility probes
- Stage07 trusted-context growth probe
- Stage07 trusted-context cost probe
- Stage08 single-buffer artifact integrity probe
- verified-read cost probe
- Stage02 nested read-only submount probe
- Stage02 mount-topology cost probe
- Stage02 backend-execution binding probe
- Stage02 backend-binding cost probe

## 2. Remediation ledger

| ID | Main implementation/evidence commits | Validation | 판정 |
|---|---|---|---|
| R08-INTEGRITY-001 | `923c6ff...`, `8ad5867...`, `7cef657...`, `85def03...`, `a3b7859...`, `d63f2ac...`, `2153501...` | single-buffer race, full regression, prior Stage probes, cost | **PASS** |
| R02-ISOLATION-001 | `046303e...`, `05a2f13...`, `185a6fc...`, `1464dd6...`, `27ffdd1...`, `df13738...` | red writable descendant, defense probe, cost, release evidence | **PASS within fail-closed nested-mount policy** |
| R02-EXEC-002 | `5933424...`, `3f12963...`, `6792876...`, `1031de2...`, `3873d31...`, `8eacb2f...` | red backend/handler mismatch, handler-call proof, cost, release evidence | **PASS** |
| R03-PROV-001 | `c24ce2b...`, `3e824be...`, `221216f...`, `a5fdc14...`, `63da5e9...`, `94d9eb3...` | exact lock/build pin, manifest + resume drift tests, final integration | **PASS for semantic runtime provenance scope** |
| R04-VERIFY-001 | `0db93e8...`, `45be145...`, `ae3f949...` | unknown class fail-closed, supported-only CTF, registry fingerprint | **PASS for registered claim classes** |
| R06-PROGRESS-001 | `f6bfc6e...`, `7350770...`, `8aaf70a...` | volatile activity credit 0, verified fact credit 1, resume/strategy probes | **PASS for activity/epistemic split** |
| R07-CONTEXT-001 | `4f31b13...`, `329f9d5...` | prior Stage07 probes + growth + cost | **PASS for trusted-fact projection** |
| R08-RETRIEVAL-002 | contract/preflight only | no accepted runtime candidate | **OPEN** |

## 3. Meaningful failed validations retained as evidence

### F-ARTIFACT-001 — ArtifactStore reconstruction regression

- context: verified-read remediation 과정.
- result: `129 passed / 5 skipped / 2 failed`.
- cause: manual restoration이 Stage03 manifest/checkpoint envelope를 잘못 재구성.
- response: exact baseline `0d396d37...`에서 storage semantics를 복원하고 ArtifactStore hardening만 재적용.
- meaning: targeted integrity fix가 persistence authority를 훼손할 수 있음을 보여준 회귀 evidence.

### F-PROV-001 — Runtime run loop truncation

- context: Stage03 provenance hardening.
- result: `49 failed / 91 passed / 5 skipped`.
- cause: `HarnessRuntime.run()`과 budget terminalization 경로 유실.
- response: remediation을 중지하고 commit `970a365...`에서 최소 복구 후 full CI green 확인.
- meaning: provenance feature가 green이어도 runtime execution semantics가 깨지면 release 불가라는 stop condition을 실제 적용.

### F-PROGRESS-001 — stale unit-test contract

- CI: `31950606445`.
- result: `147 passed / 5 skipped / 1 failed`.
- cause: test가 `first novel successful observation = progress`라는 과거 Stage06 contract를 기대.
- response: production rule rollback 대신 test oracle을 activity/epistemic contract로 변경.

### F-PROGRESS-002 — stale direct-probe contract

- CI: `31950681824`.
- result: full pytest `148 passed / 5 skipped`, Stage06 strategy direct probe FAIL.
- cause: direct probe 자체가 같은 legacy novelty assumption 보유.
- response: probe의 의미를 새 contract에 맞게 수정.
- final: `31950847647` SUCCESS.

## 4. Release / integration boundary

다음 release snapshot은 remediation evidence가 개별적으로 존재한다.

- v0.8.1 — verified-read single-buffer hardening.
- v0.8.2 — Stage02 nested read-only mount fail-closed hardening.
- v0.8.3 — Stage02 Tool backend binding hardening.

Stage03/04/06/07 후속 보강은 현재 연구 branch 위에서 integration CI로 검증되었으며, 이 문서 작성 시점에는 **전체 remediation exit release로 별도 승격하지 않는다.** Stage08 retrieval ownership이 아직 OPEN이기 때문이다.

## 5. Overall decision

```text
integrity/security P0          PASS
Stage03 provenance enforcement PASS (bounded scope)
Stage04 claim-class mechanism  PASS (registered scope)
Stage06 semantic progress      PASS (activity/epistemic scope)
Stage07 trusted fact bounds    PASS (projection scope)
Stage08 retrieval ownership    OPEN
Pre-Stage08 remediation        PARTIAL / NOT EXITED
```
