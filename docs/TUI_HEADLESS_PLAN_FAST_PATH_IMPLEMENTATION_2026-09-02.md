# TUI, Headless, Plan Fast Path Implementation Report

## Situation

- TUI에서 `/plan`, `/execute`, `/develop`, `/general`, `/hackathon` 명령과 Harness 상태가 나타나지 않았다.
- Headless의 `--plan`과 TUI의 `/plan`은 Host API까지 연결됐지만, plan-only 요청에도 legacy Core가 자연어 휴리스틱으로 선행 Explore child를 자동 생성했다.
- 이 때문에 짧은 계획 요청도 별도 모델 호출과 도구 실행을 소비해 응답이 느리고, 사용자는 TUI와 Headless가 서로 다른 로직처럼 인식할 수 있었다.

## Reason

- builtin verification plugin initializer가 Solid reactive owner 밖에서 `useSync()`를 호출해 plugin activation이 실패했다.
- plugin command 등록이 현재 TUI V2의 keymap layer가 아니라 legacy command registration 계약을 사용했다.
- prompt orchestration은 Kernel의 typed `planningPreference`를 보지 않고, 사용자 문장의 단어와 길이를 정규식으로 판정해 Explore subtask를 합성했다.
- TUI와 Headless는 같은 Host Coordinator 구현을 사용하지만, 독립 실행 시에는 각각 별도 Host process와 run을 생성하므로 attach하지 않으면 동일 live session을 공유하지 않는다.

## Action

- verification plugin에서 Solid hook 의존성을 제거하고 설정은 SDK client로 비동기 조회하도록 변경했다.
- Harness 명령을 TUI V2 `keymap.registerLayer`에 등록하고 `/plan`, `/execute`, domain/skill 명령을 typed `harness.control` 요청으로 연결했다.
- 입력 전 control을 session별 pending queue에 저장하고 첫 prompt 직전에 Host로 flush해 새 session에서도 선택한 domain과 plan-only 상태가 먼저 적용되게 했다.
- agent 선택 UI와 prompt footer를 domain 선택 의미로 바꾸고 `HARNESS <domain>` 및 계획 상태를 노출했다.
- root prompt가 시작될 때 Host의 `planningPreference`를 읽고, 값이 `plan_once`인 경우에만 exploration을 `manual`로 강제했다.
- plan-only 합성 지시는 GoalContract와 WorkGraph 제출, read-only 기본값, `plan_ready` 정지, `/execute` 필요 조건만 전달하도록 분리했다.
- 분기 판단에는 사용자 문장 키워드를 사용하지 않고 typed Kernel state만 사용했다.

## Result

- TUI에서 Harness plugin, 상태 표시, domain 선택, 계획 관련 slash command가 같은 Host API를 사용한다.
- Headless `--plan`과 TUI `/plan`은 모두 `planning.plan_once` control을 먼저 적용한 뒤 동일 prompt 경로에 들어간다.
- 명시적 plan-only 요청은 legacy 자동 Explore subtask를 합성하지 않으며, workspace mutation 없이 계약과 계획 생성에 집중한다.
- 자동 계획 모드의 기존 adaptive exploration 정책은 변경하지 않아 일반 실행의 기존 동작 범위를 보존했다.

## Evidence

- 로컬 TUI 실행에서 `HARNESS develop`, domain shortcut, `/plan`, `/plan discard`, `/execute`, `/hackathon`, `/hackathon off` 노출을 확인했다.
- TUI `/plan` 선택 후 `planning.plan_once`가 staged되고 첫 prompt에서 Host Coordinator run이 생성되는 것을 확인했다.
- Headless `run --plan --format json`이 동일 Host/Kernel control 경로로 진입하고 Coordinator run artifact를 생성하는 것을 확인했다.
- 선행 실행에서 plan-only 요청이 `Pre-plan exploration` subtask를 생성하는 병목을 재현했고, 최종 코드는 typed `planningPreference === "plan_once"`일 때 synthetic exploration 생성을 비활성화한다.
- 이번 최종 fast-path 패치 이후 자동 테스트와 타입체크는 실행하지 않았다.

## Residual Risk

- `auto` 계획의 선행 탐색 여부는 Core의 기존 자연어 휴리스틱에 남아 있으며, 향후 Contract Preflight의 typed uncertainty 신호로 완전히 이전해야 한다.
- PlanSpec과 GoalContract 생성 및 Plan MetaReview에는 모델 호출이 필요하므로 plan-only가 무모델 실행으로 바뀌는 것은 아니다.
- 독립 TUI와 독립 Headless process는 저장소와 구현을 공유하지만 live process state는 공유하지 않으며, 동일 live run 관찰에는 attach가 필요하다.
- 최종 패치의 회귀 테스트, 타입체크, Windows Terminal 상호작용 재검증은 후속 검증 단계로 남는다.

