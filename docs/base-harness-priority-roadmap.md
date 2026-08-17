# Base Harness 우선순위 개발 로드맵

> 대상: `doo513/base_harness`  
> 기준 시점: 2026-08-18, `main` 브랜치 기준  
> 목적: 단순 기능 추가가 아니라 **실제 Codex/LLM 작업 성공률, 안정성, 컨텍스트 효율을 높이는 순서**를 정한다.

## 우선순위

| 우선순위 | 작업 | 핵심 목적 |
|---|---|---|
| P0 | Benchmark / Baseline 구축 | 개선 여부를 실제로 측정 |
| P1 | Agent Loop 연결 | 하네스 로직을 실제 Codex 작업에 적용 |
| P2 | Verification / Evidence 강화 | 틀린 결과를 완료로 판단하는 문제 방지 |
| P3 | Execution / Experiment Loop | 분석 → 실행 → 결과 반영을 자동 연결 |
| P4 | Failure Analysis + Adaptive Retry | 실패 후 같은 행동 반복 방지 |
| P5 | Task Classification / Tool Routing 개선 | 문제에 맞는 도구를 더 정확히 선택 |
| P6 | State / Resume 고도화 | 장기 작업의 정보 손실 방지 |
| P7 | Web / PDF / 외부 Tool 실제 연동 | 입력 범위 확대 |
| P8 | Multi-Agent | 병렬 탐색/검토 |

## 이번 메타 구현 범위

이번 변경은 P0~P3를 실제 기능 개발 전에 안전하게 연결할 수 있는 **메타 계층**을 추가한다.

1. Benchmark 실행/기록 계약
2. Closed-loop 단계와 상태 전이 계약
3. Goal success criteria와 typed evidence 계약
4. Execution observation 계약
5. 기존 workflow와 호환되는 orchestration scaffold

실제 LLM 호출이나 무제한 명령 자동 실행은 이 단계에서 추가하지 않는다. 메타 계층은 deterministic하게 유지하고, 이후 provider/runner를 주입할 수 있도록 인터페이스를 둔다.

## 설계 원칙

```text
Context
→ Reason
→ Act
→ Observe
→ Verify
→ Retry / Complete
```

- 모든 단계는 구조화된 상태를 남긴다.
- 완료는 evidence 존재 여부가 아니라 success criteria 충족 여부로 판단할 수 있어야 한다.
- 실행 결과는 observation으로 정규화한다.
- benchmark는 baseline과 harness 모드를 같은 task contract로 비교할 수 있어야 한다.
- 기존 `run_intake_workflow()`는 그대로 재사용한다.
- 기존 test/validator를 깨지 않는다.

## 후속 구현

P0~P3 메타 계층이 검증된 뒤 실제 Agent provider 연결, adaptive retry, information-gain routing을 순차적으로 구현한다.
