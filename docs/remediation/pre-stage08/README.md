# Pre-Stage08 Consolidation / Remediation

Status: **PARTIAL — core hardening validated, Stage 08 retrieval ownership remains open**  
Working branch: `research/verified-state-stage03`

이 디렉터리는 Stage 08 retrieval/memory 구현 전에 기존 Stage 00~08을 재검토하면서 발견된 문제와 실제 수정 이력을 한곳에 모은다.

## 1. 현재 판정

| Finding | 영역 | 판정 | 현재 상태 | 핵심 evidence |
|---|---|---|---|---|
| R08-INTEGRITY-001 | verified-read double-read / TOCTOU | confirmed defect | **PASS** | single-buffer race/adversarial test, full regression, v0.8.1 evidence |
| R02-ISOLATION-001 | recursive read-only submount | confirmed isolation gap | **PASS (fail-closed policy)** | writable descendant red reproduction, topology probe, v0.8.2 evidence |
| R02-EXEC-002 | Tool backend attestation/execution split | confirmed defect | **PASS** | mismatched handler/backend red probe, handler-not-called proof, v0.8.3 evidence |
| R03-PROV-001 | build/release provenance not enforcement-bound | design/enforcement gap | **PASS for current runtime identity scope** | lock/build pinning, typed provenance, manifest + resume binding tests |
| R04-VERIFY-001 | generic verifier reuse across semantic claim classes | design gap | **PASS for registered claim classes** | unknown semantic class rejection, registry fingerprint/resume tests |
| R06-PROGRESS-001 | novelty ≠ progress | confirmed semantic-control defect | **PASS for activity vs epistemic split** | volatile novel outputs credit 0, verified fact delta credit 1, no-progress probes |
| R07-CONTEXT-001 | unbounded model-visible trusted facts | confirmed growth risk | **PASS for trusted-fact projection** | growth probe, cost probe, prior Stage07 compatibility/resume probes |
| R08-RETRIEVAL-002 | retrieval query ownership / gateway admission | design not implemented | **OPEN** | Stage08 contract only; runtime implementation not yet accepted |

`PASS`는 해당 remediation 범위만 의미한다. Stage 04 real-world semantic benchmark, Stage 05 effectiveness benchmark, independent clean-host reproduction 등은 별도 open item이다.

## 2. 문서 지도

### 공통 기록

- [`00_DISCOVERY_REGISTER.md`](./00_DISCOVERY_REGISTER.md) — 처음 제기된 문제, 분류, 심각도, 처리 여부.
- [`01_EVIDENCE_BASELINE.md`](./01_EVIDENCE_BASELINE.md) — 어떤 종류의 evidence를 근거로 판단했는지.
- [`02_ACTION_TIMELINE.md`](./02_ACTION_TIMELINE.md) — red → 수정 → 실패 → 재수정 → green 순서.
- [`03_VALIDATION_LEDGER.md`](./03_VALIDATION_LEDGER.md) — commit / CI / probe 기반 현재 검증 상태.
- [`04_OPEN_ITEMS.md`](./04_OPEN_ITEMS.md) — 아직 닫지 않은 한계와 다음 검증 대상.

### remediation별 기록

- [`stage08-verified-read/`](./stage08-verified-read/) — TOCTOU / artifact integrity primitive.
- [`stage02-nested-submount/`](./stage02-nested-submount/) — nested read-only mount topology.
- [`stage02-tool-binding/`](./stage02-tool-binding/) — attestation과 실제 execution binding.
- [`stage03-build-provenance/`](./stage03-build-provenance/) — dependency/build/source provenance와 resume binding.
- [`stage04-claim-contracts/`](./stage04-claim-contracts/) — claim class별 verification contract.
- [`stage06-semantic-progress/`](./stage06-semantic-progress/) — activity novelty와 epistemic progress 분리.
- [`stage07-trusted-context/`](./stage07-trusted-context/) — model-visible trusted state bound.
- [`stage08-retrieval-ownership/`](./stage08-retrieval-ownership/) — 아직 미완료인 retrieval ownership 설계 상태.

## 3. 기존 루트 보고서의 의미

이 디렉터리에 기존부터 존재하던 다음 네 파일은 삭제하거나 새 의미로 덮어쓰지 않는다.

- `IMPLEMENTATION_REPORT.md`
- `EVIDENCE_MATRIX.md`
- `COST_REPORT.md`
- `FINAL_REREVIEW.md`

이 네 파일은 **v0.8.1 verified-read hardening 당시 작성된 역사적 snapshot**이다. 이후 전체 remediation을 대표하는 문서가 아니다. 현재 전체 상태의 canonical remediation index는 이 `README.md`와 `00~04` 문서다.

## 4. 전체 작업 원칙

이번 consolidation의 핵심 invariant는 다음과 같다.

> 검사·검증·attestation한 대상과 실제 실행·소비·commit되는 대상 사이에 재해석 가능한 틈이 없어야 한다.

따라서 단순히 테스트 개수를 늘리는 것이 아니라, 보장의 authority가 실제 transition에 연결되어 있는지를 우선 검토한다.
