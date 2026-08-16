# 02 — Action Timeline

이 문서는 remediation을 결과가 아니라 **의사결정 과정**으로 기록한다.

## Phase A — verified-read integrity (Stage08 prerequisite)

1. **지적 수용 및 source 재검토**
   - 문제: hash 검증한 bytes와 caller에게 반환하는 bytes가 같다는 구조적 보장이 없음.
   - 초기 centralized ArtifactStore candidate에서도 double-read가 남아 있음을 확인.
2. **contract 결정**
   - pathname validation과 content verification을 분리.
   - verified-read의 authority는 `same opened object / same buffer`에서만 발생하도록 결정.
3. **구현**
   - dirfd-relative open, no-follow, regular-file fstat, one FD read loop, same buffer hash/return.
   - Stage04/Stage06 consumer를 path 재오픈이 아닌 verified bytes 소비로 migration.
4. **adversarial race**
   - 첫 read 이후 pathname replacement를 일으켜 already-open inode와 later read를 분리 검증.
5. **과정 중 오류**
   - `storage.py`에 transient placeholder가 들어간 작업 오류 즉시 복구.
   - baseline을 수동 재구성하는 과정에서 manifest/checkpoint envelope가 깨져 `129 passed / 5 skipped / 2 failed` 발생.
   - exact baseline commit `0d396d37...`의 storage semantics를 다시 가져와 ArtifactStore 변경만 재적용.
6. **green**
   - corrected candidate `131 passed / 5 skipped` 및 이전 Stage probes 통과.
   - cost probe로 double-read 제거에 따른 I/O 감소 확인.
7. **freeze**
   - v0.8.1 release/evidence commits로 고정.

## Phase B — Stage02 nested read-only mount

1. **source/mount semantics review**
   - top-level bind remount가 descendant까지 충분한지 검토.
2. **red reproduction**
   - read-only source 아래 별도 writable descendant mount를 구성해 write 가능 상태 재현.
3. **설계 선택**
   - kernel/host별 recursive remount 기능을 추정해 허용하는 대신, 현재 supported security model에서는 nested mount source를 preflight에서 거부하는 fail-closed 정책 선택.
4. **구현/테스트**
   - mount topology detection 및 unit/live probe.
   - topology scan cost 별도 측정.
5. **freeze**
   - red-green evidence와 v0.8.2 release snapshot 저장.

## Phase C — Stage02 Tool backend execution binding

1. **source review**
   - isolation attestation 대상과 `handler()` 실제 실행 대상이 분리 가능함을 확인.
2. **red probe**
   - safe backend attestation + unsafe host handler 조합을 구성.
3. **contract 결정**
   - strict WRITE/EXTERNAL effect는 attested backend가 실제 execution semantics를 소유해야 함.
   - generic host-side handler mismatch는 실행 전 차단.
4. **구현**
   - declarative backend execution path와 attestation binding.
   - backend semantics/provenance fingerprint 보강.
5. **검증**
   - mismatch에서 unsafe handler invocation 0.
   - valid path에서 expected attestation/execution count 확인.
   - cost probe의 boolean 오류도 별도 commit에서 수정하고 기록 유지.
6. **freeze**
   - v0.8.3 release/evidence snapshot.

## Phase D — Stage03 build/release provenance

1. **gap 확인**
   - exact dependency lock, build backend, source/build identity가 release/resume guarantee에 충분히 결합되지 않음.
2. **hardening**
   - CI dependency lock.
   - build backend version pin.
   - typed provenance capture.
   - runtime 생성 시 한 번만 capture하여 per-step I/O를 피함.
3. **재검토에서 추가 결함 발견**
   - provenance를 모으는 것만으로는 enforcement가 아님.
   - 당시 capture data가 manifest/config equivalence에 충분히 연결되지 않았음을 확인.
4. **중대한 regression 발생**
   - provenance 변경 과정에서 `HarnessRuntime.run()`/budget terminalization이 잘려나가 CI가 `49 failed / 91 passed / 5 skipped`.
   - remediation 진행을 즉시 중단하고 `970a365...`에서 run loop 복원.
   - 전체 regression green이 되기 전 다음 hardening으로 넘어가지 않음.
5. **enforcement 연결**
   - semantic build identity → config hash/resume equivalence.
   - full provenance audit → manifest.
   - git commit/tree는 audit용으로 유지하되 docs-only commit이 runtime conflict를 만들지 않도록 semantic key에서 제외.
6. **test**
   - manifest presence와 provenance drift resume fail-closed test 추가.

## Phase E — Stage04 claim-class verification

1. **문제 재정의**
   - verifier가 정확히 artifact assertion을 증명해도 “그 assertion이 어떤 claim 의미를 가질 수 있는가”는 별도 계약 문제임.
2. **설계**
   - claim key를 먼저 class로 resolve.
   - class별 VerificationContract와 allowed verifier set을 고정.
3. **구현**
   - `ClaimContractRegistry`.
   - Software/Hackathon unknown semantic class fail-closed.
   - CTF general intermediate는 명시적 supported-only class.
4. **재검토**
   - registry가 profile source hash에만 간접적으로 기대고 있음을 발견.
   - registry descriptor를 config fingerprint에 직접 추가.
5. **green**
   - claim masquerade, declared class, CTF supported-only, registry drift tests 통과.

## Phase F — Stage06 semantic progress

1. **기존 rule 확인**
   - new integrity-checked successful observation digest가 progress authority였음.
2. **새 contract**
   - `Activity Novelty`: 새 bytes/새 observation, credit 0.
   - `Epistemic Progress`: verified fact content transition, credit 1.
   - speculative state/recovery/failed output는 progress 아님.
3. **candidate 구현** — commit `f6bfc6e...`.
4. **첫 red regression** — CI `31950606445`
   - `147 passed / 5 skipped / 1 failed`.
   - 실패 원인: legacy boundary test가 첫 novel observation을 progress로 기대.
   - production rule을 되돌리지 않고 test oracle을 새 contract에 맞춤.
5. **두 번째 red direct probe** — CI `31950681824`
   - full pytest `148 passed / 5 skipped`.
   - Stage06 strategy direct probe만 FAIL: 같은 legacy assumption.
   - probe 목적을 “strategy switch 후 evidence novelty”에서 “activity는 어느 generation에서도 progress authority가 아님”으로 교정.
6. **green** — CI `31950847647`
   - 전체 Stage03~08 gate SUCCESS.
7. **후속 통합**
   - Stage07 hardening 이후 final CI `31950971636`에서도 Stage06 전 probe SUCCESS.

## Phase G — Stage07 trusted-context bound

1. **source confirmation**
   - verified current facts가 전체 dump되어 model-visible context 증가.
2. **설계 원칙**
   - durable truth는 절대 context 절감을 위해 삭제하지 않음.
   - projection만 bounded.
3. **구현**
   - fact count / per-value / total-value / key / superseded-key bounds.
   - large value preview + stable hash.
   - small scalar exact-value compatibility.
   - deterministic priority/selection.
4. **검증 확장**
   - 기존 Stage07 base/adversarial/resume/compat 유지.
   - trusted-context growth probe와 cost probe를 CI gate로 추가.
5. **green**
   - commit `329f9d52...`, CI `31950971636` SUCCESS.

## Phase H — Stage08 retrieval ownership

현재는 **설계/contract 단계에서 중지**되어 있다.

- 기존 `memory.py` prototype의 mutation, collision, trust, provenance, deterministic ordering, resume 문제가 확인됨.
- 다음 구현은 Actor query/request와 Kernel admission을 분리해야 한다.
- retrieval result는 separate durable retrieval state → Stage07 untrusted projection으로만 들어가야 한다.
- retrieval 자체는 Stage06 progress credit을 받으면 안 된다.
- 이 항목은 아직 green implementation evidence가 없으므로 완료로 기록하지 않는다.
