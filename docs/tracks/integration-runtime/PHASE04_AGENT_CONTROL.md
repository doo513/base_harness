# Phase 04 — Agent Control

Status: IMPLEMENTED; targeted tests added; full regression remains enforced by `develop` CI.

## Problem / evidence

The verified-state loop could decide one action at a time but had no durable representation of a longer task plan, active task, or dependencies. Using hypotheses/facts for this bookkeeping would incorrectly mix actor intent with truth authority.

## Contract

- planning/task state is durable actor workflow bookkeeping only;
- workflow state has no truth, verification, progress, or completion authority;
- dependency graphs are bounded, deterministic, acyclic, and fail closed on invalid references;
- task completion does not create a verified fact or Stage 06 task-progress event;
- model-visible workflow state is projected through the existing Runtime Context boundary, not a side channel;
- invalid actor workflow transitions route to replanning/no-progress recovery without mutating trusted state.

## Implementation

- added `AgentControlState`, `AgentTask`, and `AgentTaskStatus`;
- added bounded objective/task/note fields and dependency-cycle validation;
- persisted workflow state inside `HarnessState` snapshots with backward-compatible empty loading;
- added `plan` and `task` actor decisions;
- added Kernel dispatch handlers for plan replacement and task status updates;
- added `agent_workflow` to model-visible governed context with explicit `instruction_authority=none`, `progress_authority=false`, and `completion_authority=false`;
- added focused tests for graph rejection, dependency activation, state round-trip, context authority, and absence of direct truth/progress/completion mutation.

## Structural review

- existing fact verification and `STATE_COMMIT` path are untouched;
- workflow `done` is not a verified domain milestone;
- completion still requires the existing completion oracle;
- Stage 06 receives plan/task as ordinary actor decision families and no positive progress credit is manufactured;
- Stage 07 trusted/untrusted projection remains intact; workflow state is a separate explicitly non-authoritative namespace;
- Stage 03 snapshot/resume naturally includes workflow state through `HarnessState`.

## Remaining limitations

- the current FailureKind vocabulary has no dedicated invalid-actor-action class, so invalid plan/task transitions use `NO_PROGRESS` and replan recovery; this may be refined only in the later Progress/Recovery phase;
- task decomposition quality is still model-driven; this phase governs state and dependencies, not semantic plan quality;
- domain milestones remain separate and are implemented in the domain phase.
