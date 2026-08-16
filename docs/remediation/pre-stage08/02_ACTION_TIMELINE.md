# 02 — Action Timeline

이 문서는 remediation을 결과가 아니라 **문제 발견 → evidence → contract → 구현 → red/green 검증 → 잔여 한계** 순서로 기록한다.

## Phase A — verified-read integrity

1. hash 검증한 bytes와 caller가 실제 소비하는 bytes가 같은 객체라는 구조적 보장이 없는 TOCTOU 문제를 확인했다.
2. pathname validation과 content verification을 분리하고 `same opened object / same buffer`만 verified content authority를 갖도록 contract를 고정했다.
3. dirfd-relative open, no-follow, regular-file fstat, one-FD read loop, same-buffer hash/return으로 변경했다.
4. 첫 read 이후 pathname replacement를 일으키는 adversarial race로 검증했다.
5. 작업 중 manual persistence envelope 복구 오류로 `129 passed / 5 skipped / 2 failed`가 발생했다. exact baseline semantics를 복원한 뒤 ArtifactStore 변경만 다시 적용했다.
6. verified-read cost probe에서 4 MiB payload의 logical read가 2→1, bytes read가 8 MiB→4 MiB로 감소했고 SHA-256 verification은 유지됐다.

## Phase B — Stage02 nested read-only mount

1. top-level bind remount가 descendant mount까지 read-only를 보장하지 않는지 검토했다.
2. writable descendant mount를 가진 source를 직접 구성했고 top-level rbind/remount-ro 후에도 descendant write가 source canary를 변경할 수 있음을 재현했다.
3. recursive remount 지원을 추정하지 않고 nested mount가 있는 read-only source를 preflight에서 거부하는 fail-closed 정책을 선택했다.
4. 최신 CI `31957540019`의 hosted Ubuntu 24.04.4 runner에서도 uid 0 live probe가 실행되어 raw defect와 defense를 모두 확인했다.
5. 다만 별도의 clean VM/self-hosted host에서 provisioning부터 독립 재현한 것은 아니므로 external reproducibility gap은 유지한다.

## Phase C — Stage02 tool backend execution binding

1. isolation attestation 대상과 실제 `handler()` 실행 대상이 분리될 수 있는 구조를 확인했다.
2. safe backend attestation + unsafe host handler mismatch reproducer를 구성했다.
3. strict WRITE/EXTERNAL effect는 attested backend가 execution semantics를 직접 소유하도록 contract를 변경했다.
4. mismatch는 handler 실행 전에 차단하고 valid sandbox path는 one attestation → same backend execution으로 고정했다.
5. 최신 backend probe에서도 unsafe handler calls 0, valid path attestation 1/execution 1을 확인했다.

## Phase D — Stage03 build/release provenance

1. exact dependency lock/build backend/source identity가 release/resume equivalence에 충분히 결합되지 않은 gap을 확인했다.
2. exact CI lock, build backend pin, typed build provenance, source semantic hash, lock hash, runtime/toolchain identity를 추가했다.
3. provenance 수집만으로 enforcement가 아니라는 재검토 결과를 반영해 semantic descriptor를 config/resume equivalence에 연결하고 full provenance는 manifest audit에 기록했다.
4. 이 과정에서 `HarnessRuntime.run()`/budget terminalization이 잘려 CI가 `49 failed / 91 passed / 5 skipped`가 되는 중대한 회귀가 발생했다.
5. remediation을 즉시 중단하고 `970a365...`에서 run loop를 복원한 뒤 full regression green 후에만 provenance hardening을 계속했다.
6. 현재 exact immutable base image/VM recipe까지 모든 환경에 대해 고정했다는 주장은 하지 않는다.

## Phase E — Stage04 claim-class verification + repository benchmark

1. artifact assertion이 참이어도 그 evidence가 어떤 semantic claim class를 증명할 수 있는지는 별도 문제라고 재정의했다.
2. `ClaimContractRegistry`를 추가하여 key prefix → claim class → verification contract → allowed verifier를 명시적으로 결합했다.
3. unknown class는 fail closed하고 CTF generic intermediate는 supported-only authority로 제한했다.
4. registry descriptor를 config fingerprint에 직접 넣어 resume semantics에 연결했다.
5. 이후 frozen software semantic scope를 확장해 다음 class를 실제 execution evidence와 연결했다.
   - `software.build_result`
   - `software.test_result`
   - `software.behavioral_acceptance`
6. `stage4-repository-execution-semantics-v1` 17-case corpus에서 TP=5, TN=12, FP=0, FN=0을 기록했다.
7. `software.security_property` 및 CTF remote/exploit semantics는 아직 별도 contract/benchmark가 없어 coverage gap으로 유지한다.

## Phase F — Stage05 Recovery mechanism + A/B effectiveness

1. Recovery 자체의 안전성/재개 semantics는 기존 probes로 검증했다.
2. “Recovery가 실제 성공률을 높이는가”는 별도 empirical question으로 분리했다.
3. matched deterministic scenarios에서 production Recovery와 conservative no-automatic-recovery baseline을 비교했다.
4. recoverable scenarios 3/3에서 Recovery arm completion rate=1.0, baseline=0.0, delta=+1.0을 기록했다.
5. safety regressions=0, unsafe retries=0을 유지했다.
6. 비용은 recovered success당 평균 +2.3333 persisted steps, +1.3333 task tool calls였다.
7. 실제 LLM variability와 broad repository/CTF/hackathon corpus 효과는 여전히 external-validity gap이다.

## Phase G — Stage06 semantic progress

### G1 — activity/epistemic split

1. novel successful observation digest가 progress authority인 기존 rule을 확인했다.
2. `Activity Novelty = credit 0`, `Verified fact semantic transition = Epistemic credit 1`로 분리했다.
3. 첫 candidate CI `31950606445`: `147 passed / 5 skipped / 1 failed`. Legacy unit test가 novelty=progress를 기대했다.
4. test oracle을 새 contract로 migration했다.
5. 다음 CI `31950681824`: full pytest `148 passed / 5 skipped`, Stage06 strategy direct probe가 같은 legacy assumption으로 FAIL.
6. direct probe도 새 contract로 교정했고 CI `31950847647`에서 green이 됐다.

### G2 — task/world progress authority

1. verified fact 증가도 goal과 무관할 수 있다는 잔여 한계를 재검토했다.
2. `DomainProfile.task_progress_snapshot()`을 추가했다. Default는 `None`으로 task authority 없음.
3. 첫 구현은 deterministic snapshot hash 변화에 credit을 주었다.
4. **이 candidate가 green인 상태에서도 구조 재검토를 계속했고**, snapshot regression/토글 역시 hash change이므로 progress로 잘못 인정될 수 있음을 발견했다.
5. contract를 deterministic monotonic `{milestones, score}` schema로 축소했다.
6. milestone 제거/score 감소/arbitrary churn은 credit 0, state-mutating hook 및 authority availability toggle은 fail closed하도록 변경했다.
7. `task-world-progress-v2`에서 implicit task authority=0, regressions credited=0, state mutation accepted=0을 확인했다.

## Phase H — Stage07 trusted context + mandatory goal bounds

### H1 — trusted fact projection

1. verified current facts 전체 dump로 model-visible trusted context가 증가하는 경로를 확인했다.
2. durable truth는 삭제하지 않고 projection만 count/value/key/total bounds로 제한했다.
3. deterministic authority/identity selection, large-value preview+hash, compatibility boundary를 유지했다.
4. trusted-context growth/cost probe를 기존 Stage07 base/adversarial/resume/compat probes에 추가했다.

### H2 — oversized mandatory GoalContract

1. trusted facts가 bounded여도 goal/acceptance/constraints/pinned 자체가 무제한이면 mandatory prompt payload는 여전히 팽창할 수 있음을 확인했다.
2. mandatory semantics를 projection에서 silent truncation하지 않고 GoalContract construction 전에 fail closed하도록 결정했다.
3. limits: goal 16k chars, criteria field당 64 items, criterion당 4k chars, aggregate mandatory text 64k chars, task_id 256 chars.
4. `mandatory-goal-bounds-v1` 5/5 PASS, silent truncations 0.
5. 이보다 긴 contract를 external content-addressed representation으로 지원하는 기능은 아직 없다.

## Phase I — Stage08 typed retrieval / memory gateway

1. 기존 memory prototype에서 mutation/collision/trust/provenance/deterministic ordering/resume 문제를 확인했다.
2. retrieval을 Observation/Facts와 분리된 durable `RetrievalState`로 만들고 Actor query request와 Kernel admission을 분리했다.
3. Kernel이 scope/top-k/provider/index/ranking/admission/request identity/bounds를 소유한다.
4. provider descriptor는 inspected deterministic snapshot을 request/candidate/admission 전 경로에서 동일하게 사용한다.
5. retrieval result는 `untrusted_retrieval`, `instruction_authority=none`으로 Stage07 projection에만 들어가며 Stage06 progress credit은 0이다.
6. source/content/metadata/history/context bounds, explicit supersession, resume drift/tamper checks를 추가했다.
7. 초기 hardening CI에서 bound-test fixture가 policy-inconsistent하여 `5 failed / 173 passed / 5 skipped`가 발생했다. Production bound를 약화시키지 않고 fixture를 수정했다.
8. 다음 candidate에서는 full pytest와 prior stages는 green이었으나 adversarial probe에 같은 fixture 오류가 남아 red가 됐다. Probe fixture도 교정했다.
9. 전체 구조 재검토에서 candidate별 state mutation으로 mid-batch failure 시 partial state commit 가능성을 발견했다.
10. 모든 candidate를 먼저 prepare/verify하고 off-side `next_retrieval/artifacts/evidence_refs`를 만든 뒤 한 번에 state commit하는 batch transaction으로 변경했다.
11. adversarial probe에서 mid-batch failure 시 live items/snapshots/artifact refs가 모두 0임을 확인했다.
12. v0.9.0 scope에서 base/adversarial/resume/cost/single-buffer probes가 모두 green이다.

## Phase J — final integration and warning cleanup

1. Stage06/07 후속 hardening을 CI gate에 추가했다.
2. 첫 통합 green 이후 pytest test regex 문자열의 invalid escape warning 2건을 발견했다.
3. production 오류는 아니지만 evidence noise를 남기지 않기 위해 raw regex string으로 교정했다.
4. 최종 validated HEAD `d72f7e9b468702fb2a787870278e4008919acabb`, CI `31957540019`:

```text
205 passed / 5 skipped
Stage03 resume                         PASS
Stage04 semantic + repository corpus  PASS
Stage05 recovery + A/B                PASS
Stage06 all + task/world              PASS
Stage07 all + goal bounds             PASS
Stage08 base/adversarial/resume/cost  PASS
verified-read remediation             PASS
Stage02 mount/backend remediations    PASS
```

Pytest warning 2건은 제거됐다. GitHub Actions가 출력하는 Node action deprecation warning은 repository test/code warning이 아니라 외부 action runtime 경고로 분리한다.

## 남은 항목의 성격

현재 알려진 남은 항목은 core code blocker라기보다 다음 범주다.

- independent clean-host Stage02 reproduction;
- all-deployment immutable Stage03 environment provenance;
- Stage04 security/CTF 등 추가 semantic class corpus;
- Stage05 broad stochastic/real-world effectiveness;
- Stage06 domain-specific milestone definitions;
- Stage07 long-contract externalization;
- Stage08 conservative global orphan GC;
- future remote retrieval provider proof.

이들은 `04_OPEN_ITEMS.md`에서 완료된 mechanism과 분리해 유지한다.
