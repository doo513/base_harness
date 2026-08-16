# Remediation Documentation

이 디렉터리는 canonical Stage 문서와 별도로 **결함 수정(remediation)·hardening·회귀 복구 이력**을 관리한다.

Stage 문서는 해당 Stage가 무엇을 보장하는지 설명하고, 이 디렉터리는 그 보장이 이후 재검토에서 어떤 문제를 드러냈고 어떤 근거로 수정되었는지를 추적한다. 따라서 기존 Stage의 PASS 기록을 조용히 다시 쓰지 않는다.

## 관리 원칙

1. **Finding first** — 구현 전에 문제를 식별하고 `confirmed defect`, `design debt`, `coverage gap`, `documentation gap`으로 분류한다.
2. **Evidence before claim** — 코드 해석만으로 PASS를 선언하지 않는다. 가능한 경우 red reproduction, adversarial probe, full regression, 이전 Stage probe, cost probe를 남긴다.
3. **Red → change → green** — 실제 재현 가능한 결함은 수정 전 실패 증거와 수정 후 차단 증거를 함께 보존한다.
4. **Same-object invariant** — 검사한 객체와 실제 실행·소비·commit되는 객체가 구조적으로 동일해야 한다. TOCTOU, attestation/execution split, verification/commit split을 이 원칙으로 검토한다.
5. **Regression is evidence** — 수정 과정에서 발생한 실패와 잘못된 가정도 삭제하지 않고 원인·수정 과정을 기록한다.
6. **Cost is separate** — 보안/정확성 개선과 성능 비용을 혼동하지 않고 별도 측정한다.
7. **No silent scope inflation** — mechanism correctness와 real-world effectiveness를 구분한다. benchmark가 없으면 없다고 기록한다.
8. **PASS requires boundaries** — PASS는 해당 remediation contract 범위에서만 의미하며 남은 한계는 `OPEN_ITEMS.md`에 유지한다.

## 현재 remediation series

- [`pre-stage08/`](./pre-stage08/) — Stage 08 본 구현 전, Stage 02~08 기반 보장 재검토 및 hardening.

## 권장 하위 구조

각 remediation 항목은 가능하면 다음 파일을 사용한다.

```text
<remediation-name>/
├── README.md                 # 문제·결론·관련 문서 인덱스
├── IMPLEMENTATION_REPORT.md  # 발견 → 판단 → 구현 과정
├── EVIDENCE_MATRIX.md        # 주장별 증거와 결과
├── COST_REPORT.md            # 성능/복잡도 비용
└── FINAL_REREVIEW.md         # 수정 후 재검토와 잔여 한계
```

작은 remediation은 `README.md` 하나로 시작할 수 있으나, release 또는 Stage exit에 영향을 주는 수정은 위 네 보고서를 분리한다.
