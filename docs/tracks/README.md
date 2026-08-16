# Post-Stage08 Tracks

Stage 00~08은 Core implementation cycle로 유지한다. 이 디렉터리는 Stage 09 이상을 만들지 않고 post-Stage08 작업을 Track으로 관리한다.

## Core Freeze baseline

- branch: `research/verified-state-stage03`
- hardening implementation commit: `abed36ae430d0aa11711da267750847f792d61b6`
- implementation CI: `31959676893` — **SUCCESS**
- pytest: `209 passed, 5 skipped`
- package freeze line: **0.9.1**
- new Stage created: **no**

이번 audit에서 문서의 주장을 source보다 우선하지 않았다. Source → tests/runtime/probes → commit/CI → historical docs 순으로 검토했다.

## Track map

| Track | Current status | Immediate decision |
|---|---|---|
| A. Core Freeze Audit | **PASS at hardening baseline** | 현재 발견된 3개 core debt 수정 및 regression 고정 |
| B. Independent Reproduction | **GAP** | official benchmark 전에 clean-host + immutable benchmark profile 필요 |
| C. Domain Semantics | **PARTIAL** | Software security / CTF semantic verifier와 domain milestones를 benchmark 전 정의 |
| D. Real Evaluation | **GAP** | 실제 LLM/repository/CTF repeated evaluation 필요 |
| E. Full Harness Ablation | **REQUIRED BEFORE PERFORMANCE CLAIM** | 동일 model/task/tools/budget/oracle 조건으로 incremental ablation |
| F. Operational Extensions | **CONDITIONAL / DEFER** | long contract, global GC, remote provider는 필요 evidence가 생길 때만 |

## Documents

- [`core-freeze-audit/POST_STAGE08_EVIDENCE_REVIEW.md`](./core-freeze-audit/POST_STAGE08_EVIDENCE_REVIEW.md)
- [`core-freeze-audit/EVIDENCE_MATRIX.md`](./core-freeze-audit/EVIDENCE_MATRIX.md)
- [`core-freeze-audit/FREEZE_SNAPSHOT.md`](./core-freeze-audit/FREEZE_SNAPSHOT.md)
- [`independent-reproduction/README.md`](./independent-reproduction/README.md)
- [`domain-semantics/README.md`](./domain-semantics/README.md)
- [`real-evaluation/README.md`](./real-evaluation/README.md)
- [`full-harness-ablation/README.md`](./full-harness-ablation/README.md)
- [`operational-extensions/README.md`](./operational-extensions/README.md)

## Freeze rule

Core의 새로운 기능 수를 늘리는 것을 목표로 하지 않는다. 기존 Stage invariant를 깨는 confirmed defect는 해당 Stage 책임 안에서 최소 수정한다. 그 외에는 external validation, benchmark, ablation, operational extension으로 분리한다.
