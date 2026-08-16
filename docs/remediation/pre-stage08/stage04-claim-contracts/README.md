# Stage04 remediation — Claim-Class Verification Contracts

Finding ID: `R04-VERIFY-001`  
Status: **PASS for registered claim classes / real-world coverage remains open**

## 문제

Stage04의 structured artifact verifier는 artifact 내부의 명시적 assertion을 검증하는 mechanism으로는 유효했다. 그러나 다음 두 질문은 서로 다르다.

1. `artifact.output.returncode == 0`을 실제 artifact가 증명하는가?
2. 그 assertion이 `security.sql_injection_success` 같은 임의 semantic claim을 ENVIRONMENT authority로 증명할 수 있는가?

기존 verifier chain만으로는 두 번째의 **claim meaning ownership**이 충분히 명시되지 않았다. generic verifier가 정확히 동작해도 claim class가 자유로우면 semantic authority inflation이 가능하다.

## 조치

`ClaimContractRegistry`를 추가하여 verification 전에 claim key의 contract를 결정하게 했다.

```text
claim key
→ claim class resolution
→ VerificationContract
→ allowed verifier names/set
→ verifier execution
→ authority ceiling
→ Kernel commit
```

### Software / Hackathon

현재 명시적으로 선언된 execution-level artifact assertion class만 해당 contract를 사용할 수 있다. unknown semantic key는 generic assertion artifact를 붙여도 VERIFIED/ENVIRONMENT로 commit되지 않는다.

### CTF

기존 intermediate flexibility를 완전히 제거하지 않고 `ctf.intermediate_supported`라는 명시적 catch-all class를 둔다. 단 이 class의 authority ceiling은 `SUPPORTED`이며 ENVIRONMENT/EXTERNAL_ORACLE 수준으로 자동 승격하지 않는다.

## 재검토에서 추가한 조치

첫 claim-class 구현 이후 registry가 profile source hash에 간접적으로만 반영되는 점을 발견했다. 정책 객체 자체가 runtime semantics이므로 registry descriptor를 config fingerprint에 직접 포함했다.

- main implementation: `0db93e8...`
- registry fingerprint: `45be145...`
- enforcement tests: `ae3f949...`

## Evidence

- longest-prefix claim class resolution.
- Software unknown semantic claim → verification failure / facts 미commit.
- declared `artifact_assertion.*` → contract 범위에서 ENVIRONMENT authority.
- CTF arbitrary intermediate → SUPPORTED ceiling.
- registry policy drift가 persisted runtime semantics와 분리되지 않도록 descriptor fingerprint.
- initial claim-class CI `31950306061` SUCCESS.
- final integration CI `31950971636`에서 Stage04 semantic probe와 전체 prior gates SUCCESS.

## 보장 범위

이번 remediation은 **claim class와 verifier contract의 binding mechanism**을 강화했다.

다음은 아직 증명하지 않는다.

- 모든 실제 software/security/CTF semantic claim class가 구현됨.
- 실제 corpus에서 semantic verifier FP/FN가 충분히 낮음.
- CTF exploit primitive, remote acceptance 등 domain-specific verifier가 완성됨.

따라서 real-world semantic benchmark는 `../04_OPEN_ITEMS.md`에 남긴다.
