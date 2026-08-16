# Stage08 prerequisite — Verified-read / Artifact Integrity

Finding ID: `R08-INTEGRITY-001`  
Status: **PASS**  
Release snapshot: **v0.8.1**

## 문제

초기 verified-read 중앙화 candidate는 artifact ref의 digest를 검사할 때 한 번 파일을 읽고, caller에게 bytes를 돌려줄 때 pathname을 다시 읽는 구조였다.

```text
read A
→ hash(A) PASS
→ pathname changes
→ read B
→ return B
```

이 구조에서는 검증한 객체와 실제 consumer가 받은 객체가 다를 수 있다. 따라서 `hash PASS`가 반환 bytes의 integrity authority가 될 수 없었다.

## 판단 근거

- source-level double-read 확인.
- pathname replacement를 이용한 deterministic race fixture.
- Stage04/Stage06도 path 또는 중복 integrity logic을 통해 같은 종류의 gap을 다시 만들 수 있는지 consumer 추적.

## 조치

verified-read authority를 다음 primitive로 제한했다.

```text
artifact root dirfd
→ token-relative open
→ no-follow / regular-file check
→ one opened FD에서 logical buffer 읽기
→ SHA-256(buffer)
→ artifact ref digest와 비교
→ 동일 buffer 반환
```

`resolve_ref_path()`는 confinement/path resolution helper일 뿐, 이후 pathname read를 보증하는 verified object가 아니라고 경계를 명확히 했다.

Stage04 semantic verifier와 Stage06 progress evidence reader도 `verified_read_bytes()`를 통해 받은 **검증된 동일 buffer**를 소비하도록 정리했다.

## Red / Green 과정

수정 과정의 실패도 evidence로 보존되어 있다.

- transient 작업 오류로 `storage.py` placeholder가 들어갔다가 즉시 복구.
- 첫 baseline reconstruction에서 manifest/checkpoint envelope를 잘못 재구성하여 `129 passed / 5 skipped / 2 failed`.
- exact baseline `0d396d37...`의 persistence semantics를 복원하고 ArtifactStore 변경만 재적용.
- corrected candidate: `131 passed / 5 skipped`, Stage03 resume 4/4, Stage04 semantic 8/8 FP=0/FN=0, Stage05~07 PASS, Stage08 integrity 6/6, unverified return buffers 0.

## Cost

4 MiB artifact 기준:

- logical reads: `2 → 1`
- bytes read: `8 MiB → 4 MiB`

즉 integrity 강화를 위해 추가 double-read cost를 지불한 것이 아니라 기존 중복 I/O도 제거했다.

## 관련 문서

이 항목은 remediation 작업 초기에 이미 상세 4종 보고서가 상위 디렉터리에 작성되어 있다. 역사적 snapshot이므로 그대로 유지한다.

- `../IMPLEMENTATION_REPORT.md`
- `../EVIDENCE_MATRIX.md`
- `../COST_REPORT.md`
- `../FINAL_REREVIEW.md`

## 잔여 경계

이 PASS는 artifact content-address verified-read primitive에 대한 것이다. Stage08 retrieval provider/admission/query ownership 자체가 검증되었다는 의미는 아니다.
