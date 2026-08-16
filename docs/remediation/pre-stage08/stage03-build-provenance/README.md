# Stage03 remediation — Build / Release Provenance

Finding ID: `R03-PROV-001`  
Status: **PASS for current semantic runtime provenance scope**

## 발견

Stage03 persistence/resume은 runtime config를 강하게 fingerprint했지만, release/build 환경 identity에는 다음 공백이 있었다.

- CI dependency exact lock 부족.
- build backend version pin 부족.
- source/lock/toolchain identity의 typed record 부족.
- provenance를 수집해도 그것이 resume equivalence에 실제 연결되지 않으면 단순 audit metadata에 그칠 수 있음.

재검토 과정에서 마지막 항목을 **추가 결함**으로 발견했다. 즉 “provenance capture 존재”와 “provenance enforcement 존재”를 구분했다.

## 조치 순서

1. `requirements-ci.lock`을 추가하고 CI installation source로 사용 — `c24ce2b...`, `acc9adbe...`.
2. setuptools build backend exact pin — `3e824be...`.
3. typed build provenance capture — `221216f...`.
4. runtime당 한 번만 capture하여 반복 I/O 방지 — `a5fdc14...`.
5. semantic provenance identity와 audit I/O 분리 — `e485f12...`.
6. semantic descriptor를 config hash / resume identity에 실제 binding — `63da5e9...`.
7. manifest presence와 resume drift enforcement test — `94d9eb3...`.

## 중간 regression과 대응

`e485f12...` 이후 runtime source가 잘려 `HarnessRuntime.run()`과 budget terminalization이 유실되었다.

CI 결과:

```text
49 failed / 91 passed / 5 skipped
```

이 시점에서 provenance 작업을 계속하지 않고 stop condition을 적용했다. commit `970a365...`에서 기존 run loop semantics를 최소 복구하고 full regression이 다시 green이 된 뒤 provenance enforcement 작업을 재개했다.

이 incident는 provenance 개선이 runtime behavior보다 우선할 수 없다는 process evidence로 남긴다.

## 최종 semantics

```text
full build provenance
    ├─ audit fields (git commit/tree 등) → run manifest
    └─ semantic fields (source/lock/toolchain 등) → config hash / resume equivalence
```

Git commit/tree 자체를 무조건 semantic equality에 넣지 않은 이유는 documentation-only commit까지 persisted run과 false conflict를 만들기 때문이다. 대신 audit provenance에는 그대로 남긴다.

## 검증

- manifest에 full build provenance 존재.
- semantic build identity drift 시 resume fail-closed.
- prior Stage03 resume behavior 유지.
- final integration CI `31950971636`에서 Stage03 resume probe 포함 전체 gate SUCCESS.

## 남은 한계

모든 실행 환경의 immutable OS/base-image/container digest까지 end-to-end로 고정했다는 의미는 아니다. independent clean-host / immutable environment reproduction은 `../04_OPEN_ITEMS.md`의 별도 coverage item이다.
