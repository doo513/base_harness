# 00 — Discovery Register

이 문서는 Pre-Stage08 재검토에서 제기된 문제를 **수정 여부와 무관하게** 등록한다. 구현이 끝난 항목만 남기는 목록이 아니다.

## 분류

- `confirmed defect` — 코드 또는 실제 red reproduction으로 보장 위반이 확인됨.
- `design debt` — 현재 contract가 불완전하거나 authority/ownership 경계가 약함.
- `coverage gap` — mechanism은 존재하지만 외부/real-world 검증 범위가 부족함.
- `documentation gap` — 코드 보장과 연구 계보를 재현할 canonical 기록이 부족함.

## Findings

### R00-DOC-001 — Stage 00 canonical 문서 / 계보

- 원 제기: `canonical 문서 누락`, `연구 계보 단절`.
- 분류: **documentation gap**.
- 발견 근거: `docs/stages/`의 canonical Stage 구조가 Stage 02 이후에 집중되어 있고 Stage 00은 동일 수준의 canonical package가 없음.
- 보정 판단: artifact index와 과거 commit이 남아 있으므로 계보가 완전히 소실된 것은 아니다. 정확한 표현은 **“증거는 남아 있으나 canonical Stage 문서로 승격되지 않음”**이다.
- 상태: **OPEN** — retrospective reconstruction 필요.

### R01-DOC-001 — Stage 01 canonical 문서 / hardening 기록 분산

- 분류: **documentation gap**.
- 근거: Stage 01 COMPLETE 표시는 존재하지만 현재 Stage 02+와 같은 canonical 디렉터리/contract/evidence 구성은 없음.
- 상태: **OPEN**.

### R02-ISOLATION-001 — nested read-only submount

- 원 제기: recursive read-only submount 검증 부족.
- 분류: **confirmed isolation gap**.
- 직접 근거: `rbind` 후 top-level `remount,bind,ro`만으로 descendant mount의 RO를 보장할 수 없고, red probe에서 writable descendant가 실제 재현됨.
- 위험: read-only source tree라는 Stage02 보장보다 실제 mount topology가 약해질 수 있음.
- 조치 결정: recursive semantics를 추정하지 않고 **nested source mount 발견 시 preflight fail-closed**.
- 상태: **PASS for fail-closed policy**.

### R02-EXEC-002 — Tool backend attestation / execution split

- 원 제기: Tool backend 우회 가능성.
- 분류: **confirmed defect**.
- 직접 근거: strict isolation은 `execution_backend.isolation_attestation()`을 검사하지만 generic `ToolSpec.handler`가 별도 host-side 실행 경로가 될 수 있었음.
- 위험: 검사한 backend A가 안전해도 실제 effect는 handler B에서 일어날 수 있음.
- 조치 결정: strict WRITE/EXTERNAL effect에서 attested backend와 실제 execution semantics를 결합하고 mismatch를 handler 호출 전에 차단.
- 상태: **PASS**.

### R02-REPRO-003 — independent clean-host reproduction

- 분류: **coverage gap**.
- 근거: live namespace probe와 hosted CI가 있지만 독립적으로 준비한 clean host에서 동일 release를 재현하는 별도 evidence package는 충분하지 않음.
- 상태: **OPEN**.

### R03-PROV-001 — release/build provenance

- 원 제기: release-level provenance, container/image/lockfile hash 부족.
- 분류: **design/enforcement gap**.
- 발견 과정: provenance capture를 추가한 뒤 재검토했을 때, 수집된 provenance가 manifest/config resume identity에 실제 연결되지 않은 상태를 추가 발견.
- 위험: 기록은 남아도 의미 있는 build drift가 resume equivalence에 반영되지 않을 수 있음.
- 조치: exact CI lock, build backend pin, typed build provenance, once-per-runtime capture, semantic descriptor → config hash, full audit → manifest.
- 상태: **PASS for current semantic build identity scope**, immutable clean-host/container image provenance는 별도 open 범위.

### R04-VERIFY-001 — claim-type별 verifier contract

- 원 제기: real-world semantic verifier 검증 부족 / claim-type 계약 부족.
- 분류: claim-type 계약은 **design gap**, real-world coverage는 **coverage gap**.
- 직접 근거: generic artifact assertion verifier가 구조적으로는 강해도 임의 semantic key와 결합되면 claim 의미보다 artifact 구조를 증명하게 됨.
- 조치: `ClaimContractRegistry`를 통해 claim key → claim class → contract → allowed verifier set을 먼저 결정. registry 자체를 resume fingerprint에 포함.
- 상태: **PASS for registered mechanism**, real-world claim library benchmark는 **OPEN**.

### R05-RECOVERY-001 — Recovery effectiveness

- 원 제기: Recovery 효과 benchmark 없음 / 실제 task 성공 개선 미검증.
- 분류: **coverage / effectiveness gap**.
- 현재 증명 범위: durable recovery transitions, resume ordering, unsafe retry 차단 등의 mechanism correctness.
- 미증명 범위: recovery enabled/disabled A/B에서 실제 task success rate 개선.
- 상태: **OPEN**.

### R06-PROGRESS-001 — novelty ≠ progress

- 원 제기: 새로운 출력이 쓸모없어도 progress가 될 수 있음.
- 분류: **confirmed semantic-control defect**.
- 직접 근거: 기존 policy가 `novel_integrity_checked_successful_observation_digest`를 progress authority로 사용했고, 계속 다른 bytes를 내는 tool이 no-progress를 무한 reset할 수 있었음.
- 조치: **Activity Novelty**와 **Epistemic Progress** 분리. novel successful observation은 integrity-check/기록하지만 credit 0. verified fact content transition만 현재 deterministic epistemic credit를 얻음.
- 상태: **PASS for activity/epistemic boundary**. profile-defined task/world progress는 OPEN.

### R07-CONTEXT-001 — trusted context growth

- 원 제기: trusted context hard-cap 부족 / 대형 verified state 팽창.
- 분류: **confirmed growth/control risk**.
- 직접 근거: 기존 `_project_facts()`가 current verified facts를 사실상 lossless하게 전체 투영하여 fact count/value size에 비례해 model payload가 증가.
- 조치: durable fact는 보존하고 model-visible projection에 count/value/key/total limits와 stable hash/preview를 적용. compatibility가 필요한 작은 scalar는 exact value 유지.
- 상태: **PASS for trusted-fact projection boundary**.

### R08-INTEGRITY-001 — verified-read TOCTOU

- 원 제기: hash한 bytes와 caller에게 반환되는 bytes가 구조적으로 동일하지 않음.
- 분류: **confirmed defect**.
- 직접 근거: 초기 centralized candidate에서 `read → hash → path를 다시 read → return` 구조 확인.
- 조치: one FD / one logical buffer / hash same buffer / return same buffer. path helper는 verification authority가 아니라고 명시.
- 상태: **PASS**, v0.8.1 evidence snapshot 존재.

### R08-RETRIEVAL-002 — retrieval query ownership / retrieval ≠ progress

- 분류: **design debt / not implemented**.
- 현재 근거: Stage08 frozen contract와 기존 `memory.py` prototype의 mutating search, arbitrary authority, blind ID overwrite, deterministic tie/resume/integrity 부재.
- 요구 경계: Actor request와 Kernel admission 분리, provider/source provenance, bounded query/result, untrusted projection, retrieval-only progress credit 0.
- 상태: **OPEN — Stage08 feature 구현 전 필수 gate**.
