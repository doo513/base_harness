# Post-Stage08 Evidence-Based Review

## 1. Executive Conclusion

현재 Stage 00~08 Core는 **재오픈이 필요한 구조적 blocker 없이 freeze 가능한 상태**다. 다만 이번 source-first audit에서 기존 문서에 충분히 반영되지 않았던 current defect 3개를 발견했고 `abed36a...`에서 수정했다.

1. refuted hypothesis reopen이 새 evidence **ref 문자열**에 의존하던 문제.
2. same-key fact가 재검증된 뒤 current `refuted_hypotheses` marker가 남을 수 있던 문제.
3. large dict/list tool output이 full artifact와 durable Observation state에 동시에 크게 저장되던 문제.

CI `31959676893`에서 `209 passed, 5 skipped`, 새 Core Freeze probe 4/4와 기존 Stage02~08 gates가 전부 성공했다.

가장 큰 남은 위험은 현재 알려진 Kernel invariant defect가 아니라 **external validity**다. clean-host isolation reproduction, official benchmark execution identity, domain-native security/CTF verification, 실제 LLM/task corpus evaluation과 full ablation이 아직 부족하다.

가장 먼저 할 일은 새 기능 추가가 아니라 **B. Independent Reproduction → C. Domain Semantics → D/E. Real Evaluation + Ablation** 순서다.

지금 하지 말아야 할 일은 Stage 09 추가, 모든 deployment의 완전 immutable화, 64K+ contract externalization 선구현, always-on global GC, 사용 계획 없는 remote retrieval protocol이다.

---

## 2. Stage 00~08 Completion Verification

| Stage | Verdict | Evidence-based reason | Residual scope |
|---|---|---|---|
| 00 Research Contract / Architecture | **PASS** | Actor/Verifier/Oracle/Kernel role separation과 trusted-commit 경계가 현재 security/runtime 구조에 유지됨 | historical research evidence는 retrospective 성격 |
| 01 Truth / Execution Integrity | **PASS WITH RESIDUAL SCOPE** | fail-closed decision/tool/verification 경계 유지. 이번 audit에서 evidence novelty + stale refuted marker를 추가 수정 | full fact dependency/version graph는 evidence 없으므로 미구현 |
| 02 Capability Isolation / Sealed Oracle | **PASS WITH RESIDUAL SCOPE** | nested mount fail-closed와 backend-execution binding probe green | independent clean-host reproduction |
| 03 Persistence / Resume / Reproducibility | **PASS WITH RESIDUAL SCOPE** | checkpoint/replay/resume/provenance drift gates green | official benchmark/release image/VM identity 강화 |
| 04 Semantic Verification Contract | **PASS WITH RESIDUAL SCOPE** | registered software build/test/behavior classes + 17-case execution benchmark FP=0/FN=0 | security_property + CTF task-native semantics |
| 05 Failure Recovery | **PASS WITH RESIDUAL SCOPE** | durable typed recovery + controlled matched A/B positive utility | real LLM/repository/CTF statistical effectiveness |
| 06 Progress Control | **PASS WITH RESIDUAL SCOPE** | activity credit 0, epistemic transition, explicit monotonic profile milestone/score hook | real domain milestone definitions/benchmark |
| 07 Context Governance | **PASS WITH RESIDUAL SCOPE** | trusted/untrusted projection bounded; GoalContract > limits fails closed; durable structured Observation now bounded | >64K contract externalization only if workload proves need |
| 08 Retrieval / Memory Gateway | **PASS WITH RESIDUAL SCOPE** | untrusted authority, deterministic admission, integrity/resume/provenance/false-progress/context bounds all green | global orphan GC; future remote provider proof |

No Stage 09 is required.

---

## 3. Resolved Historical Issues

| Historical issue | Current judgment | Current evidence |
|---|---|---|
| verified-read double-read / TOCTOU | **RESOLVED** | same opened object/same buffer is hashed and returned; attack probe green |
| nested read-only submount | **RESOLVED** within supported policy | nested topology is detected and rejected fail-closed; raw writable descendant reproduction retained |
| Tool backend attestation != actual execution | **RESOLVED** | strict side-effecting tool must use backend-owned execution; mismatch blocked before handler |
| trusted context unbounded fact growth | **RESOLVED** | bounded trusted projection; 200-fact cost probe shows 99.2614% serialized-char reduction proxy |
| retrieval false-progress | **RESOLVED** | retrieval changes do not grant progress credit |
| evidence novelty by ref string | **RESOLVED in this audit** | same bytes under different refs are not novel; content delta can reopen |
| stale refuted marker after verified commit | **RESOLVED in this audit** | same-key successful verified commit clears current refuted marker |
| durable large structured Observation duplication | **RESOLVED in this audit** | full raw artifact retained; durable preview bounded |

---

## 4. Current Confirmed Defects

At validated head `abed36a...`, **reviewed scope에서 남아 있는 confirmed correctness/security defect는 발견하지 못했다.**

이번 audit에서 발견한 결함은 아래와 같았고 같은 audit에서 수정/검증했다.

```yaml
finding_id: CFA-001
title: Refuted hypothesis reopen accepted ref-string novelty
affected_stage: Stage 01 / Stage 06 control boundary
class: confirmed_defect
severity: P1
evidence:
  code: runtime_execution.py used set(prior.evidence_refs) and new ref strings
  test: same bytes can produce distinct content-address refs with different basename suffixes
  runtime: core_freeze_audit_probe same_content_new_ref_not_novel PASS after fix
  docs: previous hardening test only covered no-new-ref case
reproduction: same source/same bytes -> different artifact basename/ref -> attempt reopen
impact: refuted path could bypass no-new-evidence control without new semantic evidence
existing_stage_pass_affected: narrowed Stage01/06 control guarantee; did not bypass verifier trusted commit by itself
recommended_fix: verified content digest + stable source provenance identity
regression_risk: medium
cost_impact: one integrity read/hash per reopen evidence ref; reopen is exceptional path
status: RESOLVED at abed36a...
```

Answers: 실제 결함이었다. Stage 전체 PASS를 무효화할 P0는 아니지만 no-refuted-retry invariant를 약화했다. Kernel trusted commit을 직접 우회하지는 않는다. 특정 domain이 아니라 공통 control 경계다. 구현 수정이 필요했고 적용했다. 추가 복잡도는 exceptional reopen path에 국한되어 이득이 더 크다.

```yaml
finding_id: CFA-002
title: Verified same-key commit could coexist with stale refuted marker
affected_stage: Stage 01 / Stage 07 current-state coherence
class: confirmed_defect
severity: P2
evidence:
  code: HarnessState.commit_verified removed hypothesis but not refuted_hypotheses
  test: direct same-key state transition regression added
  runtime: core_freeze_audit_probe verified_commit_clears_stale_refuted_marker PASS
  docs: context already treated refuted hypotheses as current untrusted state
reproduction: refute key -> reopen -> verify same key
impact: current state could expose logically conflicting verified/refuted records
existing_stage_pass_affected: no trusted fact corruption, but current-state coherence was incomplete
recommended_fix: successful same-key verified commit clears current refuted marker; event log preserves history
regression_risk: low
cost_impact: O(1) dict removal
status: RESOLVED at abed36a...
```

```yaml
finding_id: CFA-003
title: Large structured tool output duplicated into durable Observation state
affected_stage: Stage 07 / Stage 03 persistence cost
class: confirmed_defect
severity: P2
evidence:
  code: string-only truncation left large dict/list preview unbounded
  test: 40K canonical structured output regression added
  runtime: full=40073 chars, durable preview=2861 chars, reduction=0.928605
  docs: context projection was bounded but durable checkpoint state was not
reproduction: tool returns large nested dict/list
impact: checkpoint/event-state growth and duplicated storage despite artifact-backed evidence
existing_stage_pass_affected: context safety PASS remained valid; durability/cost bound was incomplete
recommended_fix: artifact keeps exact raw output; durable Observation keeps bounded preview+digest+artifact ref
regression_risk: medium for consumers expecting huge raw preview; small outputs remain exact
cost_impact: extra canonical serialization/hash only when structured output exceeds bound; checkpoint size decreases
status: RESOLVED at abed36a...
```

---

## 5. Security Hypotheses

No new P0/P1 security hypothesis is promoted to confirmed status without reproduction.

- **Remote provider honesty**: a future provider may claim stable revision while serving mutable results. This is not a current shipped-local-provider defect. Status: `HYPOTHESIS / CONDITIONAL`.
- **Cross-host namespace differences**: current CI and local topology probes may not represent every clean Linux host/kernel configuration. Status: `GAP`, not a reproduced escape in current implementation.

---

## 6. Validation / Research Gaps

1. **Stage02 independent reproduction — GAP**: hosted/internal CI is not independent clean-host reproduction.
2. **Stage03 official benchmark execution identity — GAP**: source/lock/toolchain/platform provenance exists, but official benchmark image/VM identity is not a mandatory profile contract.
3. **Stage04 domain semantic breadth — GAP**: Software build/test/behavior exists; `software.security_property.*` and CTF exploit/service/remote classes do not.
4. **Stage05 external effectiveness — GAP**: deterministic controlled A/B is positive but does not prove stochastic real-LLM benefit.
5. **Stage06 domain milestones — GAP**: framework exists; shipped domain profiles mostly do not define real task milestones.
6. **Full Harness ablation — GAP**: individual mechanism probes do not quantify incremental end-to-end task benefit.
7. **Verifier duplicate integrity reads — SUPPORTED operational debt**: EvidenceRefVerifier verifies the artifact and a following domain verifier reads/verifies it again in the same attempt. Correctness is conservative; optimization is not justified until measured on realistic artifact sizes.
8. **Full fact version/dependency graph — GAP but DEFER**: event log/history and supersession fields exist; no reproduced stale dependency failure justifies a graph yet.

---

## 7. Required Work List

| Priority | Work | Why | Evidence | Expected benefit | Implementation cost | Runtime/token/storage cost | Risk |
|---|---|---|---|---|---|---|---|
| **REQUIRED BEFORE BENCHMARK** | Stage02 clean-host reproduction | isolation portability claim needs independent host | current tests are same-project CI | confidence in security/reproducibility | medium ops | no model-token cost | host privilege variability |
| **REQUIRED BEFORE BENCHMARK** | Official benchmark/release execution profile | fair repeated benchmark requires immutable execution identity | provenance currently warns/records rather than requiring full image identity | comparable runs | medium | low per run; capture once | over-constraining local dev if applied globally |
| **REQUIRED BEFORE BENCHMARK** | Domain semantic verifier set | benchmark truth cannot depend on generic structural evidence | CTF remains supported-only; security property unregistered | lower false completion | medium-high/domain-specific | verification calls increase | verifier bugs/coverage gaps |
| **REQUIRED BEFORE BENCHMARK** | Domain milestone definitions | Stage06 task credit needs verified task-native transitions | base hook exists, profiles not populated | meaningful progress/recovery analysis | medium | low metadata, verifier-dependent | false milestone design |
| **REQUIRED BEFORE PERFORMANCE CLAIM** | Real repeated evaluation + full ablation | current mechanism tests cannot prove task-success ROI | no full same-model incremental benchmark | causal benefit/cost evidence | high experiment cost | model/tool/token cost dominates | stochastic variance |
| **CONDITIONAL** | verifier read-cache / verified-buffer sharing | duplicate integrity reads are conservative but costful for large evidence | source review confirms repeated reads | reduce I/O | medium | lower I/O, small cache metadata | widening lifetime of verified buffer |
| **DEFER** | >64K ContractArtifact externalization | current fail-closed bound is correct; workload need not shown | no workload evidence | supports rare large contracts | high | retrieval/index overhead | authority/projection complexity |
| **CONDITIONAL** | safe global orphan GC | orphan files consume disk but have no truth authority | Stage08 preparation can leave unreferenced blobs | disk hygiene | medium-high | scans/storage I/O | accidental deletion |
| **CONDITIONAL** | remote retrieval receipt/proof | no shipped remote provider requires it | current provider is local lexical | replayability/provenance | high/provider-specific | retrieval metadata | false sense of provider honesty |

---

## 8. Work Direction

### NOW

- Freeze current Core after this audit and documentation.
- Do not add another Stage.
- Treat `abed36a...` + green CI as Core Freeze implementation baseline.

### NEXT

1. Independent Stage02 reproduction on a fresh privileged Linux VM/self-hosted host.
2. Define official benchmark/release execution profile; keep local development warnings permissive.
3. Implement only the domain semantic verifiers required by the first real benchmark corpus.
4. Bind Stage06 domain milestones to Stage04 verified transitions.

### LATER

- Run actual LLM software/CTF repeated evaluations.
- Run full incremental ablation.
- Optimize duplicate verification reads only if measured I/O/cost is material.

### DEFER

- 64K+ ContractArtifact externalization until real tasks hit the limit.
- global orphan GC until storage pressure/operational need is measured.
- remote provider proof until a remote provider enters the roadmap.
- full fact dependency graph until stale dependency failures are reproduced.

---

## 9. Benchmark / Ablation Plan

The final experiment must keep `model`, `task`, `tools`, `budget`, and `oracle` identical per matched trial.

Arms:

1. Minimal Baseline
2. + Verified State
3. + Semantic Verification
4. + Failure Recovery
5. + Progress Control
6. + Context Governance
7. + Retrieval / Memory

Recovery-specific sub-ablation should compare:

- Recovery OFF
- Retry-only
- Full Replan
- Typed Targeted Recovery

Metrics:

- success rate
- false completion
- state corruption
- verifier FP/FN
- repeated failure
- recovery success / steps to recovery
- tokens / solved
- tool calls / solved
- wall time / solved
- cost / solved
- checkpoint/event/artifact storage where relevant

Synthetic/frozen probes remain mechanism evidence only. Real LLM/task trials are required for performance claims.

---

## 10. Final Research Judgment

**Core design / integrity: A**

The authority boundaries, fail-closed verification, persistence, progress separation, governed context and retrieval ownership form a coherent architecture after the freeze fixes. No reviewed current defect requires reopening a Stage.

**Empirical task-performance evidence: B (provisional)**

Controlled mechanism probes and limited repository-style semantic/recovery benchmarks are strong enough to justify further evaluation, but not enough for an S/A-level claim that the complete harness improves real task success/cost across models and domains.

The next research question is therefore not “what feature should be added?” but:

> Under matched real tasks, which existing layers measurably reduce false completion/state corruption or improve solve rate enough to justify their token/tool/I/O/complexity cost?
