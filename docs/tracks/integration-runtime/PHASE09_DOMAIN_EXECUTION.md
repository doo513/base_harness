# Phase 09 — Software / Hackathon Domain Execution

Status: IMPLEMENTED at the current evidence-supported vocabulary; broader domain semantics remain benchmark-driven.

## Problem / evidence

The Kernel could verify claims and control recovery, but the domain layer was too thin for real development/hackathon work: it exposed goals, tools, and a few verifiers without an explicit workflow contract, verified task milestones, or a separation between hard execution truth and soft quality/judging guidance.

The pre-existing Domain Semantics track already required domain milestones to originate from verified transitions rather than Actor prose. This phase follows that rule instead of inventing broad LLM semantic truth.

## Contract

- a domain may provide an explicit workflow contract for role/execution guidance;
- a domain may provide an advisory evaluation rubric, but rubric scores have no truth/progress/completion authority;
- task-progress milestones are computed only from `HarnessState.facts` already promoted through the verifier path;
- Actor plan/task status, raw command success, retrieval, memory, or soft evaluation cannot directly create a domain milestone;
- final success remains the completion oracle;
- domain verifier vocabulary is expanded only where exact execution evidence is available.

## Software implementation

- workflow: inspect → reproduce → plan → implement → targeted verification → regression → acceptance;
- added structured `argv` alongside shell; CLI-composed workspace READ tools remain available;
- existing build/test/behavior verification classes remain the hard semantic vocabulary;
- `task_progress_snapshot()` now emits only verifier-backed milestones:
  - `verified_artifact_assertion`;
  - `build_passed`;
  - `tests_passed`;
  - `behavioral_acceptance_verified`;
- added advisory quality criteria for scope minimality, maintainability, and regression risk.

## Hackathon implementation

- workflow: scope → prototype → build check → demo check → polish → rehearsal → acceptance;
- added structured `argv` alongside shell;
- added strict execution-check claim classes/verifiers:
  - `hackathon.build_check.*`;
  - `hackathon.demo_check.*`;
  - `hackathon.rehearsal_check.*`;
- milestones are generated only when the corresponding verified fact has `{'succeeded': true}`;
- added advisory judging criteria for problem value, demo clarity, judging coverage, delivery risk, and presentation readiness;
- soft evaluation is explicitly advisory-only and cannot pass a build/demo/rehearsal check or final oracle.

## Context integration

Runtime context now exposes `domain_contract` containing the profile workflow and advisory evaluation descriptors. The contract identifies itself as harness-supplied domain guidance; evaluation subfields explicitly carry no truth/progress/completion authority.

## Structural review

- `DomainProfile.task_progress_snapshot()` remains pure and Kernel-evaluated;
- verified milestones are monotonic functions of current verified facts;
- no milestone is inferred from Actor prose or task checkboxes;
- no advisory criterion is registered as a verifier or completion oracle;
- existing Stage-04 verification and completion paths remain unchanged;
- workflow contracts guide execution order but do not mutate trusted state.

## Validation focus

`tests/test_integration_domains.py` covers:

- unverified Software hypotheses producing no milestone;
- verified Software build/test facts producing deterministic milestones;
- Hackathon execution-check evidence binding;
- Hackathon verified milestone versus advisory evaluation separation;
- model-visible domain workflow/evaluation contract and continued separation from completion authority.

## Remaining limitations

- repository understanding/root-cause/code-quality claims do not receive new semantic truth classes without task-native evidence;
- Hackathon soft judging quality is a prioritization contract, not an objective score oracle;
- deadline timestamps and dynamic feature-value optimization are not yet hard runtime inputs; the workflow preserves deadline/rehearsal policy at the domain-contract level;
- broader classes such as software security properties should continue to be added from real benchmark failures, not speculative vocabulary.
