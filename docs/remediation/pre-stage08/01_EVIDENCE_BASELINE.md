# 01 — Evidence Baseline

이 문서는 remediation 판단에서 사용한 evidence의 종류와 실제 적용 사례를 정리한다.

## 1. Evidence 등급

### E1 — Direct source evidence

코드 경로와 authority transition을 직접 추적한다. 단순 함수 존재 여부가 아니라 **검사 결과가 실제 소비/실행/commit 경로에 연결되는지**를 확인한다.

예: Stage02에서 `execution_backend.isolation_attestation()` 이후 실제 effect가 generic `handler()`에서 실행될 수 있음을 확인한 것.

### E2 — Red reproduction / adversarial evidence

문제가 실제로 발생하거나 기존 보장을 우회할 수 있는 최소 재현을 만든다.

예:
- verified-read에서 첫 read 후 pathname 교체.
- nested read-only source 내부 writable submount.
- safe attestation backend와 unsafe handler를 의도적으로 분리.
- 계속 다른 successful bytes를 반환하는 volatile tool.

### E3 — Focused regression

해당 결함을 직접 겨냥한 unit/integration test로 수정 이후 차단 여부를 검증한다.

### E4 — Full regression

`pytest -q` 전체를 통과해야 한다. targeted test가 green이어도 전체 회귀가 깨지면 candidate는 실패다.

### E5 — Previous-Stage direct probes

수정 대상보다 앞선 보장이 깨지지 않았는지 Stage03 resume, Stage04 semantic, Stage05 recovery, Stage06 progress, Stage07 context 등의 direct probe를 재실행한다.

### E6 — Release / provenance evidence

release commit, package version, lock/build identity, manifest/config binding 등을 통해 “어떤 코드와 환경 의미론이 검증되었는지”를 고정한다.

### E7 — Cost evidence

correctness와 별도로 추가 I/O, topology scan, serialization/context size, execution overhead를 측정한다.

---

## 2. Finding별 evidence chain

### R08-INTEGRITY-001 — verified-read TOCTOU

**발견 evidence**

- source review에서 초기 centralized candidate가 검증용 `read_bytes()`와 반환용 `read_bytes()`를 분리하고 있음을 확인.
- 이 구조는 `bytes A hash PASS → pathname replacement → bytes B return`을 허용한다.

**red/adversarial evidence**

- 큰 artifact를 여러 chunk로 읽게 하고 첫 successful read 이후 pathname을 atomic replace하는 race fixture.
- 기존 논리의 취약 조건을 직접 모델링.

**green evidence**

- one opened FD에서 읽은 한 buffer를 hash하고 그 buffer를 그대로 반환.
- replacement 이후 새 logical read는 digest mismatch로 차단.
- Stage04 semantic verifier와 Stage06 observation fingerprint도 verified byte buffer를 직접 소비하도록 migration.
- 기존 v0.8.1 remediation 보고서에 corrected candidate `131 passed / 5 skipped`, Stage03 4/4, Stage04 8/8 FP=0/FN=0, Stage05~07 PASS, integrity probe 6/6, `unverified return buffers=0` 기록.

**cost evidence**

- 4 MiB artifact 기준 logical read `2 → 1`, bytes read `8 MiB → 4 MiB`로 double-read 제거가 오히려 I/O를 감소시킴.

관련 역사적 문서: 상위 `IMPLEMENTATION_REPORT.md`, `EVIDENCE_MATRIX.md`, `COST_REPORT.md`, `FINAL_REREVIEW.md`.

### R02-ISOLATION-001 — nested read-only submount

**발견 evidence**

- mount semantics review: `--rbind` 후 top-level `remount,bind,ro`는 descendant mount의 write flag까지 자동으로 동일하게 고정한다는 보장이 없음.

**red evidence**

- writable nested descendant를 실제 구성하여 read-only source 아래에서 write 가능 상태를 재현.

**green evidence**

- mount topology preflight가 nested source mount를 발견하면 sandbox 실행 전에 fail-closed.
- unit + live probe + CI gate + red/green evidence commit 보존.
- release `v0.8.2` snapshot으로 고정.

**cost evidence**

- 별도 topology cost probe를 CI에 유지.

상세: `stage02-nested-submount/`.

### R02-EXEC-002 — Tool backend binding

**발견 evidence**

- strict isolation 검사와 실제 `handler()` 실행 경로를 source에서 분리 확인.

**red evidence**

- attestation은 안전한 backend가 통과하지만 handler는 별도 unsafe host effect를 수행하도록 구성.

**green evidence**

- strict side-effect path가 declarative backend execution semantics와 결합됨.
- mismatch는 handler 실행 전에 차단.
- direct probe에서 invalid path의 unsafe handler call이 0이고, valid path는 attestation 1회 → 같은 backend execution 1회로 확인.
- backend semantics도 config/provenance fingerprint 대상.
- release `v0.8.3` evidence로 고정.

상세: `stage02-tool-binding/`.

### R03-PROV-001 — build provenance

**발견 evidence**

1. dependency/build environment가 정확히 lock되지 않은 상태 확인.
2. provenance capture를 추가한 뒤 재검토에서 **capture만 하고 config/resume authority에 연결되지 않은 추가 결함** 확인.

**조치 evidence**

- exact `requirements-ci.lock` 추가 및 CI가 이를 직접 설치.
- build backend pin.
- typed `BuildProvenance` capture.
- runtime 생성 시 1회 capture.
- semantic build descriptor → config hash / resume equivalence.
- full audit dump → run manifest.
- git commit/tree는 audit에는 남기되 docs-only commit이 resume conflict를 만들지 않도록 semantic equality에서는 분리.

**회귀 evidence**

- provenance hardening 과정에서 `HarnessRuntime.run()`이 유실되는 회귀가 발생하여 CI `49 failed / 91 passed / 5 skipped`.
- commit `970a365...`에서 run loop와 budget terminalization 복원.
- 그 후 full CI green 확인.

**enforcement evidence**

- commit `94d9eb3...`의 manifest/resume binding test.
- 최종 통합 CI `31950971636`에서 Stage03 resume probe 포함 전 gate SUCCESS.

### R04-VERIFY-001 — claim-class contract

**발견 evidence**

- generic structured artifact assertion은 artifact 구조는 증명하지만 claim key 자체의 의미를 자동 증명하지 않음.
- unknown semantic claim이 generic verifier를 재사용할 수 있는 설계 위험 확인.

**green evidence**

- `ClaimContractRegistry`: key → longest matching claim class → VerificationContract → allowed verifier set.
- Software/Hackathon unknown semantic class는 execution-level commit 실패.
- declared `artifact_assertion.*`는 contract 범위에서 ENVIRONMENT authority 가능.
- CTF catch-all은 `ctf.intermediate_supported`로 명시하고 authority를 SUPPORTED로 제한.
- registry descriptor를 runtime fingerprint에 직접 포함하여 policy drift resume 차단.
- initial claim-class CI run `31950306061` SUCCESS, 이후 최종 CI `31950971636`에서도 Stage04 semantic probe SUCCESS.

### R06-PROGRESS-001 — novelty ≠ progress

**발견 evidence**

- 기존 `ProgressPolicy` descriptor에 novel successful observation digest가 progress authority로 명시되어 있었음.
- volatile tool이 매번 다른 successful bytes를 생성하면 실질 task 진전 없이 progress streak를 reset 가능.

**green evidence**

- novel observation fingerprint 계산/무결성 검증은 유지하되 `activity`, credit 0으로 분리.
- verified fact content hash transition을 `epistemic`, credit 1로 인정.
- direct probe 결과: volatile novel outputs `activity_events=3`, `progress_events=0`, no-progress failure 발생.
- verified fact delta: `epistemic_events=1`, `max_credit=1.0`.

**contract migration evidence**

- run `31950606445`: `147 passed / 5 skipped / 1 failed`. 오래된 test가 첫 novel observation을 progress로 기대해 실패.
- 기대 contract를 교정.
- run `31950681824`: full pytest `148 passed / 5 skipped`, 그러나 별도 strategy probe가 같은 오래된 가정을 유지하여 FAIL.
- strategy probe도 교정.
- run `31950847647`: 전체 SUCCESS.
- 이 실패들은 새 보장을 약화해 없애지 않고 **기존 test oracle 자체가 잘못된 계약에 묶여 있었음을 보여주는 evidence**로 보존.

### R07-CONTEXT-001 — trusted context bound

**발견 evidence**

- 기존 `_project_facts()`가 current verified facts 전체 dump를 model-visible trusted namespace에 넣음.
- fact 수/값 크기 증가가 prompt/context 증가로 직접 연결.

**green evidence**

- durable `HarnessState.facts`는 손대지 않음.
- model projection에서 fact count, per-value chars, total value chars, key chars, superseded key 수 제한.
- large value는 bounded preview + stable value hash + evidence metadata.
- small scalar compatibility 유지.
- deterministic priority/selection 적용.
- prior Stage07 compatibility/resume/adversarial probes와 새 growth/cost probe를 함께 실행.
- final CI `31950971636`: Stage07 기존 4개 probe + trusted-context growth + cost 모두 SUCCESS.

### R08-RETRIEVAL-002 — query ownership

현재 **green evidence 없음**. contract/preflight만 있으며 runtime 구현을 아직 승인하지 않았다. 따라서 이 항목은 문서상 OPEN으로 유지한다.
