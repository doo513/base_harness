# Stage08 remediation — Retrieval Query Ownership

Finding ID: `R08-RETRIEVAL-002`  
Status: **OPEN — contract/preflight only; no accepted runtime implementation**

이 문서는 아직 구현되지 않은 항목을 완료된 것처럼 보이지 않게 하기 위한 상태 기록이다.

## 발견된 기존 prototype 문제

현재 `src/harness/core/memory.py`의 prototype은 Stage08 contract를 만족하지 않는다.

- `authority`가 arbitrary string.
- `add()`가 같은 ID를 silent overwrite.
- `search()`가 `recall_count`를 증가시켜 query 자체가 store를 mutation.
- score tie에 explicit deterministic tie-break 없음.
- source revision/provenance admission contract 없음.
- artifact integrity binding 없음.
- supersession omission enforcement 없음.
- checkpoint/resume semantics 없음.
- retrieval result가 model instruction authority를 얻지 못하도록 하는 typed boundary 없음.

따라서 이 prototype 위에 ad-hoc 기능을 추가하는 방식은 사용하지 않는다.

## Frozen ownership 방향

### Actor

Actor는 retrieval이 필요하다는 **request/proposal**을 만들 수 있다. Actor narrative 자체가 trusted query authority는 아니다.

### Kernel

Kernel이 다음을 소유하거나 검증한다.

- normalized query descriptor
- allowed scope
- top-k / result count
- per-request / per-step retrieval budget
- provider identity and revision
- admission rule
- collision/supersession behavior
- durable request/result state

### Provider / Gateway

provider는 evidence candidate를 반환할 뿐 verified truth를 commit하지 않는다.

### Context Governor

admitted retrieval은 model에 들어갈 때 항상:

```text
trust = untrusted_retrieval
instruction_authority = none
```

이어야 한다.

## Stage06와의 경계

retrieval 자체는 progress가 아니다.

```text
new retrieval result
→ activity/evidence availability
→ progress credit 0

retrieved evidence로 claim proposal
→ 아직 progress 아님

independent verifier를 거쳐 verified fact/task milestone transition
→ 그 transition만 progress 후보
```

retrieval result를 일반 successful observation으로 섞어 “새 bytes”를 progress source로 만드는 구현은 금지한다.

## Stage08 구현 전 요구 evidence

1. prompt-injection retrieval item이 system/control authority를 얻지 못함.
2. forged `authority` field가 typed admission에서 차단됨.
3. admitted/indexed artifact가 이후 tamper되면 verified-read에서 fail-closed.
4. same ID different content collision silent overwrite 없음.
5. equal score tie deterministic.
6. query가 store state를 mutation하지 않음.
7. superseded item default omission.
8. flood가 count/text budget을 넘지 않음.
9. resume 후 same state/query/config result 동일.
10. provider/config/index revision drift resume conflict.
11. retrieval-only loop의 Stage06 progress credit 0.
12. Stage07 context bound 안에서 retrieval preview 제한.

## 현재 판정

위 direct evidence가 아직 없으므로 **Stage08 retrieval gateway는 PASS가 아니다.**

다음 구현은 이 문서를 출발점으로 하며, candidate가 생기면 이 디렉터리에 `IMPLEMENTATION_REPORT.md`, `EVIDENCE_MATRIX.md`, `COST_REPORT.md`, `FINAL_REREVIEW.md`를 추가한다.
