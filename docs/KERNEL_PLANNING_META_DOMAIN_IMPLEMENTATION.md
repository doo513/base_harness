# Kernel Planning, Meta Review, and Domain Implementation

## Situation

The runtime exposed model-owned plan agents and allowed planning, execution, and verification responsibilities to overlap.

## Reason

GoalContract and PlanSpec quality must be reviewed before mutation, while user-facing domain and plan controls must remain independent of provider-specific agent modes.

## Action

- Added the pure @base-harness/kernel package for typed domains, planning decisions, PlanSpec validation, meta-review validation, and tool-operation policy.
- Added a Host KernelHost that wraps the Coordinator, persists reviewed plans atomically, validates plan freshness, and gates execution behind typed controls.
- Added independent read-only meta-review child execution using the selected session model, provider, variant, and reasoning configuration.
- Routed repeated blocking meta-review issues through the existing Question Service; warnings remain recorded assumptions.
- Added /develop, /general, /hackathon, /hackathon off, /plan, /plan discard, and /execute controls without forwarding slash text to the model.
- Added headless domain, hackathon, plan-only, and reviewed-plan execution flags, including run --execute-plan for an active Host session.
- Removed the user-facing legacy plan agent registration and retained the build agent only as an internal execution compatibility role.

## Result

Planning decisions are deterministic Kernel outputs, plan-only requests cannot mutate the workspace, and reviewed plans are bound to their domain, skill set, GoalContract hash, revision, and basis file hashes.

## Evidence

- Kernel unit tests cover direct/planned decisions, general-domain permissions, meta-review schema safety, and PlanSpec DAG validation.
- Runtime typechecks and existing Coordinator, verification, Host, and TUI regression suites are the promotion gate.
- Canonical plans are stored under the platform base-harness state directory in plans/planId/revision.json.

## Residual Risk

The initial meta reviewer uses the same model in an independent context, so correlated model errors remain possible. Alternate reviewer models, persisted cross-process execution context, and CTF domains remain intentionally out of scope.
