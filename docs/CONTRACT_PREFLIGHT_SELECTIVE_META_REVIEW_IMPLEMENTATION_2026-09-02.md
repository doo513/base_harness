# Selective Contract Preflight Implementation Report

## Situation

The Kernel planning implementation always sent every GoalContract to the same-model MetaReviewer. This reduced direct execution efficiency and made an LLM review appear to be the authority over another LLM artifact, while PlanSpec review and mutation gating still needed to remain fail-closed.

## Reason

Semantic uncertainty cannot be derived completely by deterministic code, but an LLM must not control the policy decision that follows. The selected boundary is **LLM-assisted detection + deterministic Kernel adjudication**: the actor proposes typed uncertainty candidates, and the Kernel validates references and decides `accept`, `meta_review_required`, or `needs_input`.

## Action

- Added typed `InterpretationProposal`, `ContractPreflightResult`, uncertainty impact, reason, and revalidation trigger contracts to `@base-harness/kernel`.
- Added `contract_preflight` to the planning state machine and denied mutation while that state is active.
- Made `harness_contract.interpretation` mandatory at the model-facing tool schema and validated candidate source references plus Claim and Criterion bindings in the Kernel.
- Allowed clear, low-risk, atomic contracts with implementation-only assumptions to bypass GoalContract MetaReview.
- Routed consequential ambiguity to the existing Question Service before any mutating action.
- Required GoalContract MetaReview for high or critical risk, strict verification, external Claims, unresolved applicability, or multiple required Claims or Criteria.
- Kept every PlanSpec on the existing mandatory independent MetaReview path, including one revision and one re-review limit.
- Removed Preflight-only metadata before forwarding the normalized GoalContract to the Coordinator and Python verifier, preserving sidecar protocol v4 and Evidence and Ready schemas.
- Added typed foundational revalidation entry points; ordinary implementation failures continue to use existing local repair and do not reopen the contract.
- Added Host and TUI status fields for decision, reasons, questions, assumptions, and reviewer call count.
- Migrated stale tests that still expected the removed native `plan` agent to the Kernel and hidden `meta-review` architecture.

## Result

- A clear atomic contract reaches `planning_decision` with zero GoalContract reviewer calls.
- Consequential ambiguity reaches `awaiting_input` before the canonical contract is forwarded or mutation is allowed.
- High-risk and strict contracts call the GoalContract reviewer once on a passing response and fail closed when review is unavailable or malformed after the existing bounded repair.
- MetaReview output remains audit metadata and cannot create Evidence, Claim coverage, or Ready.
- The canonical GoalContract hash excludes actor-provided Preflight metadata, so verifier behavior and persisted Evidence and Ready compatibility remain unchanged.
- Deterministic fixtures compare `deterministic-only`, `selective`, and `always-review`; selective review reduces calls while retaining typed blockers.

## Evidence

- Bun version used for generation and validation: `1.3.14` through `bunx bun@1.3.14`.
- SDK official codegen: passed; generated V2 SDK output was unchanged.
- Typecheck: Kernel, Base Harness Host, Coordinator, Verification, Core, TUI, and SDK all passed.
- Kernel tests: 8 passed, 0 failed.
- KernelHost Preflight and plan-only tests: 6 passed, 0 failed.
- Migrated agent regression tests: 47 passed, 0 failed.
- Question Service tests: 14 passed, 0 failed.
- Coordinator tests: 3 passed, 0 failed.
- Verification tests: 15 passed, 0 failed.
- Python sidecar tests: 22 passed, 0 failed.
- CLI checks: `base-harness --help` and `base-harness run --help` both exited 0.
- Formatting check: `git diff --check` exited 0; Git emitted only configured LF-to-CRLF working-copy warnings.
- No paid or external model call was used; all policy comparisons used deterministic fixtures.
- Broad TUI baseline run: 186 passed, 1 skipped, and 7 existing Windows path and branding snapshot tests failed outside this change surface.
- A broad Host run reproduced previously known TUI migration and branding baseline failures and was stopped after the scoped failures were isolated; all affected Kernel, agent, Question Service, Coordinator, Verification, and sidecar suites were then rerun successfully.

## Reviewer Call Policy

| Contract condition | Kernel decision | GoalContract reviewer calls |
| --- | --- | ---: |
| Low-risk atomic, implementation choice only | `accept` | 0 |
| Consequential unresolved ambiguity | `needs_input` | 0 before user input |
| High or critical risk, strict, external, unresolved applicability, or complex required coverage | `meta_review_required`, then `accept` on pass | 1 normally |
| Reviewer schema or transport failure | fail-closed bounded repair | At most 2 attempts |
| Any PlanSpec | mandatory plan review | 1 normally, at most one revision review |

## Difference From the Previous Structure

Previously, the same-model GoalContract reviewer was unconditional and its presence was required even for deterministic low-risk work. The new structure uses the model only to detect and describe uncertainty; the Kernel owns binding validation, escalation, question gating, mutation permission, and typed revalidation. Plan review remains mandatory because a PlanSpec introduces DAG, coverage, ownership, and execution-order risk that is not present in every atomic contract.

## Residual Risk

- The actor and MetaReviewer may share the same model and therefore retain common-mode semantic errors; deterministic adjudication limits authority but cannot prove that every uncertainty candidate was discovered.
- A malicious or weak actor may omit a real uncertainty candidate. High-risk, strict, external, unresolved, and complex contracts still force review, but low-risk misclassification remains possible.
- The Kernel policy depends on a correct normalized GoalContract and verifier policy; selective Preflight does not eliminate verifier specification errors.
- Existing Windows TUI config migration, path normalization, and branding snapshot failures remain outside this implementation and should keep their separate remediation track.
- `net_monitor.py` remained untracked and was excluded from staging, both commits, and push.
