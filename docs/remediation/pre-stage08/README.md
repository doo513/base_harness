# Pre-Stage08 Consolidation / Remediation

Status: **CORE MECHANISMS GREEN — residual external/coverage/operational gaps tracked separately**  
Working branch: `research/verified-state-stage03`  
Current package line: `v0.9.0`

이 디렉터리는 기존 Stage 00~08을 재검토하면서 발견된 문제와 실제 수정 이력을 한곳에 모은다. 완료된 mechanism과 아직 증명하지 않은 external-validity/reproducibility/future-scope 항목을 분리한다.

## 1. 현재 판정

| Finding | 영역 | 현재 상태 | 핵심 evidence |
|---|---|---|---|
| R08-INTEGRITY-001 | verified-read double-read / TOCTOU | **PASS** | same-opened-object/same-buffer race test, tamper/missing/path probes, cost |
| R02-ISOLATION-001 | recursive read-only submount | **PASS on validated host / clean-host gap remains** | live writable-descendant repro, fail-closed topology defense, cost |
| R02-EXEC-002 | Tool backend attestation/execution split | **PASS** | mismatch blocked before handler, safe path attestation=execution |
| R03-PROV-001 | build/release provenance enforcement | **PASS for semantic runtime scope / environment breadth PARTIAL** | exact lock/build pin, source/toolchain identity, manifest + resume binding |
| R04-VERIFY-001 | claim-class verification | **PASS for registered classes** | registry, unknown-class fail closed, config fingerprint |
| R04-REALWORLD-002 | software execution semantics | **PASS for frozen 17-case corpus / broader domain PARTIAL** | TP=5/TN=12/FP=0/FN=0 |
| R05-EFFECT-001 | Recovery effectiveness | **PASS for controlled A/B / broad real-world PARTIAL** | recoverable 3/3 vs 0/3, safety regressions 0 |
| R06-PROGRESS-001 | novelty ≠ progress | **PASS** | activity credit 0, verified fact epistemic credit 1 |
| R06-TASK-002 | task/world progress authority | **PASS for mechanism / domain milestone coverage PARTIAL** | explicit monotonic milestones/score, regression credit 0, pure hook |
| R07-CONTEXT-001 | unbounded model-visible trusted facts | **PASS** | growth/cost + compatibility/resume probes |
| R07-GOAL-002 | oversized mandatory goal/control | **PASS for current GoalContract** | entry-time fail closed, 5/5 direct probe, silent truncation 0 |
| R08-RETRIEVAL-002 | typed retrieval ownership / admission | **PASS — v0.9.0 scope** | base/adversarial/resume/cost, batch state atomicity |

`PASS`는 표에 적힌 scope만 의미한다. independent clean-host reproduction, immutable deployment recipe breadth, broader security/CTF semantic corpus, stochastic Recovery evaluation, long-contract externalization, retrieval orphan GC/remote-provider proof는 `04_OPEN_ITEMS.md`에서 별도로 유지한다.

## 2. 최신 통합 evidence

문서 정정 직전 code/test validated head:

```text
HEAD        d72f7e9b468702fb2a787870278e4008919acabb
CI          31957540019
package     0.9.0
pytest      205 passed / 5 skipped
```

동일 HEAD에서 Stage03~08 및 Stage02/P0 remediation gate가 모두 성공했다. Stage06 task-world progress와 Stage07 mandatory goal bound도 동일 workflow에서 검증됐다.

## 3. 문서 지도

### 공통 기록

- [`00_DISCOVERY_REGISTER.md`](./00_DISCOVERY_REGISTER.md) — 발견사항의 최초 분류와 genealogy.
- [`01_EVIDENCE_BASELINE.md`](./01_EVIDENCE_BASELINE.md) — evidence 종류와 판단 기준.
- [`02_ACTION_TIMELINE.md`](./02_ACTION_TIMELINE.md) — red → 수정 → 실패 → 재수정 → green 및 후속 re-review.
- [`03_VALIDATION_LEDGER.md`](./03_VALIDATION_LEDGER.md) — commit / CI / probe 기반 현재 검증 상태.
- [`04_OPEN_ITEMS.md`](./04_OPEN_ITEMS.md) — 아직 닫지 않은 한계와 미래 scope.

### remediation별 기록

- [`stage08-verified-read/`](./stage08-verified-read/) — TOCTOU / artifact integrity primitive.
- [`stage02-nested-submount/`](./stage02-nested-submount/) — nested read-only mount topology.
- [`stage02-tool-binding/`](./stage02-tool-binding/) — attestation과 실제 execution binding.
- [`stage03-build-provenance/`](./stage03-build-provenance/) — dependency/build/source provenance와 resume binding.
- [`stage04-claim-contracts/`](./stage04-claim-contracts/) — claim class별 verification contract.
- [`stage04-real-world-verification/`](./stage04-real-world-verification/) — frozen repository-style semantic corpus.
- [`stage05-recovery-effectiveness/`](./stage05-recovery-effectiveness/) — controlled matched A/B evaluation.
- [`stage06-semantic-progress/`](./stage06-semantic-progress/) — activity/epistemic + profile-explicit monotonic task progress.
- [`stage07-trusted-context/`](./stage07-trusted-context/) — trusted projection 및 mandatory GoalContract bounds.
- [`stage08-retrieval-ownership/`](./stage08-retrieval-ownership/) — v0.9.0 typed retrieval ownership/integrity.

## 4. 기존 루트 보고서의 의미

이 디렉터리에 기존부터 존재하던 다음 네 파일은 v0.8.1 verified-read hardening 당시의 역사적 snapshot이며 삭제하거나 현재 전체 remediation 의미로 덮어쓰지 않는다.

- `IMPLEMENTATION_REPORT.md`
- `EVIDENCE_MATRIX.md`
- `COST_REPORT.md`
- `FINAL_REREVIEW.md`

현재 전체 상태의 canonical remediation index는 이 `README.md`와 `00~04` 문서다.

## 5. 전체 작업 원칙

핵심 invariant:

> 검사·검증·attestation한 대상과 실제 실행·소비·commit되는 대상 사이에 재해석 가능한 틈이 없어야 한다.

따라서 테스트가 green이어도 구조 재검토를 중단하지 않는다. 실제로 Stage06 task-progress 첫 candidate는 green이었지만 regression-as-progress 문제를 후속 re-review에서 발견하여 monotonic contract로 다시 좁혔다.
