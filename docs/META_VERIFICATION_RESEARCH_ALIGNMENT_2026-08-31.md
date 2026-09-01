# Meta Verification Research Alignment and Application Direction

Date: 2026-08-31

Status: **DIRECTION CONFIRMED WITH TARGETED REFINEMENT — proposal, not implementation evidence**

## Executive conclusion

The current Base Harness direction is substantially aligned with the reviewed research and is more advanced than a simple LLM self-critique loop.

The following existing decisions remain valid:

- convert the user request into a source-linked GoalContract before mutation;
- keep Contract, Action, Evidence, Verification, and Ready as separate authority boundaries;
- treat model output and tool output as candidates rather than trusted truth;
- use external execution observations and verifier attestations for correction;
- preserve the existing child scope, Candidate, local repair, and root-only Ready model;
- keep historical Evidence and RAG as non-authoritative verification candidates;
- bound meta review rather than recursively creating reviewers of reviewers.

The principal refinement is narrow:

> Replace unconditional LLM meta review with deterministic Contract Preflight for every request and conditionally invoke MetaReviewer only when typed specification uncertainty, risk, or verifier mismatch justifies it.

This is not a rewrite of the Verified-State model. It is a more efficient admission policy at the front of the existing Kernel.

---

## Situation

The current Kernel implementation creates a GoalContract, validates it deterministically, and then runs an independent read-only MetaReviewer using the selected model in a separate context. Planned work receives a second review at the PlanSpec boundary.

This already prevents several unsafe shortcuts:

- a model cannot mutate before a contract exists;
- a model cannot turn its own review into Evidence or Ready;
- warnings are recorded as assumptions;
- repeated blocking ambiguity is routed through the Question Service;
- plan-only execution cannot mutate the workspace;
- final completion remains controlled by the root verifier path.

However, the current policy can invoke an LLM reviewer even when a request is structurally clear and low risk. The independent context reduces anchoring to the first answer, but it does not remove common-mode model error. It also adds latency and token cost before useful work begins.

The theoretical concern is therefore not that the current layers are wrong. It is that the first layer should distinguish three different concepts more explicitly:

| Concept | Meaning | Authority |
|---|---|---|
| Specification uncertainty | The user's intended target, condition, or outcome is not uniquely determined | Kernel policy decides whether to ask |
| Model uncertainty | The model is unsure how to interpret or implement the request | Model may report candidates; it does not decide authority |
| Verification uncertainty | The Harness lacks an applicable verifier or sufficient observable evidence | Verifier policy blocks Ready or requests evidence |

These concepts must not be collapsed into one natural-language judgment such as "this request seems ambiguous."

---

## Reason

### Research findings

| Finding | Primary source | Implication for Base Harness |
|---|---|---|
| Clarifying underspecified requirements before code generation improves generated-code accuracy | [ClarifyGPT](https://arxiv.org/abs/2310.10996) | Keep an early contract clarification gate |
| Clarification improves code generation, but deciding when and what to ask remains a separate problem | [Python Code Generation by Asking Clarification Questions](https://aclanthology.org/2023.acl-long.799/) | Do not ask on every request; make question selection a policy |
| Structured uncertainty over tool parameters and domains improves coverage while reducing unnecessary clarification questions | [Structured Uncertainty Guided Clarification for LLM Agents](https://aclanthology.org/2026.findings-acl.2028/) | Base the gate on typed missing values, alternatives, side effects, and verifier gaps rather than prompt wording |
| Intrinsic self-correction without external feedback may fail to improve reasoning and can degrade it | [Large Language Models Cannot Self-Correct Reasoning Yet](https://openreview.net/forum?id=IkmD3fKBPQ) | A MetaReviewer pass must not become proof; external observations remain necessary |
| Tool-interactive critique can improve correction because it introduces external information | [CRITIC](https://openreview.net/forum?id=Sx038qxjek) | Preserve execution feedback, tests, Candidate verification, and local repair |
| LLM judges exhibit task-dependent and position-dependent bias | [Judging the Judges](https://arxiv.org/abs/2406.07791) | Keep LLM review advisory and avoid model-majority truth authority |

These results are benchmark evidence, not a proof that the same effect size will hold in Base Harness. They justify an implementation hypothesis that must be evaluated against Harness-specific tasks.

### The appropriate bounded model

The research supports a staged design rather than a single review at the beginning:

```text
Gate 0: Contract Preflight
  deterministic structure, applicability, risk, and verifier checks

Gate 1: Conditional MetaReview
  ambiguity and omission candidate generation only

Gate 2: Execution Feedback
  tool outcomes, tests, hashes, typed failures, and Candidate attestation

Gate 3: Completion Verification
  Claim-Evidence coverage and root-only Ready

Offline qualification
  verifier revision tests and later calibration, outside each run
```

The recursive chain stops at the declared Trusted Base. MetaReviewer is not reviewed by another MetaReviewer during the run. Kernel invariants, protocol validation, hashes, qualified verifier revisions, and externally observable results form the bounded trust boundary.

---

## Comparison with existing project documents

| Existing document | Existing direction | Research comparison | Direction decision |
|---|---|---|---|
| [Kernel planning implementation](./KERNEL_PLANNING_META_DOMAIN_IMPLEMENTATION.md) | Deterministic planning and independent GoalContract/PlanSpec review | Correct boundary, but review invocation is broader than necessary | Retain Kernel ownership; add selective review policy |
| [Canonical direction meta review](./audit/2026-08-24-architecture-reset/02_CANONICAL_DIRECTION_META_REVIEW.md) | Actor proposes, Harness executes, Verifier promotes, Oracle completes | Strongly aligned with limits of intrinsic self-correction | Retain without weakening |
| [Proposal comparison](./audit/2026-08-24-architecture-reset/04_PROPOSAL_COMPARISON_AND_NEXT_ARCHITECTURE.md) | Standalone Agent Shell plus Verified-State Core | Compatible with structured uncertainty and external tool feedback | Retain current architecture |
| [Local work meta protocol](./audit/2026-08-24-architecture-reset/05_META_REVIEW_AND_LOCAL_WORK_PROTOCOL.md) | Meta re-check between implementation slices | Useful for architecture changes but too costly as a universal runtime rule | Keep as development protocol; runtime review becomes trigger-based |
| [Verification Protocol V2](./verification-v2/IMPLEMENTATION_AND_META_AUDIT.md) | Three sections: proposition validity, Claim-Evidence binding, Evidence acceptance | More complete than a single LLM judge and directly aligned with staged verification | Retain; make Contract Preflight its explicit front gate |
| [Stage 04 semantic contract](./stages/stage-04-semantic-verification/CONTRACT.md) | Only a configured, sufficiently strong verifier may commit a claim class | Aligns with external and verifiable feedback | Retain as completion trust boundary |
| [Stage 05 recovery contract](./stages/stage-05-failure-recovery/CONTRACT.md) | Typed, bounded, durable repair without truth fabrication | Aligns with tool-informed correction rather than intrinsic self-correction | Retain; do not route ambiguity to generic repair |
| [Evidence memory lifecycle V2](./tracks/integration-runtime/EVIDENCE_MEMORY_LIFECYCLE_V2.md) | Historical cases remain verification candidates and never current proof | Prevents retrieved consensus from acting as an LLM judge | Retain unchanged |
| [Verification safety foundation](./tracks/integration-runtime/v2-coordinator-delivery/02_VERIFICATION_SAFETY_FOUNDATION.md) | Host-owned FailureEnvelope and structured exploration | Supports typed decisions instead of natural-language classification | Reuse the same typed-policy pattern for Preflight |
| [Coordinator and sidecar v4](./tracks/integration-runtime/v2-coordinator-delivery/04_COORDINATOR_AND_SIDECAR_V4.md) | Candidate verification before commit and scope-local repair | Supplies the external execution feedback missing from pure self-review | Retain unchanged |
| [Validation and residual risks](./tracks/integration-runtime/v2-coordinator-delivery/06_VALIDATION_AND_RESIDUAL_RISKS.md) | Separates targeted validation from release-readiness claims | Consistent with conditional assurance rather than absolute truth | Retain the same claim discipline |

### Comparative verdict

There is no material contradiction between the reviewed research and the existing canonical documents.

The project is progressive in five respects:

1. It already separates proposal authority from truth authority.
2. It already uses source-linked claims rather than free-form completion judgment.
3. It already binds Candidate identity and patch hash to verifier attestation.
4. It already resumes the same local scope after evidence-based rejection instead of relying on generic self-reflection.
5. It already prevents historical memory and LLM review from becoming current-run proof.

The missing refinement is principally an efficiency and calibration issue at request intake, not a defect in the Verified-State foundation.

---

## Action: recommended application model

### 1. Rename and constrain the initial stage

Use `Contract Preflight` for the mandatory first stage. Reserve `MetaReview` for the optional LLM-assisted review.

```text
User request
→ Contract proposal
→ Contract Preflight
   → accept
   → meta_review_required
   → needs_input
```

Every request receives deterministic Preflight. Not every request receives an LLM MetaReviewer call.

### 2. Add a typed uncertainty contract

The exact schema may be adjusted during implementation, but the decision fields should remain structured.

```ts
type PreflightReason =
  | "missing_required_value"
  | "multiple_valid_interpretations"
  | "unsafe_default"
  | "scope_conflict"
  | "applicability_gap"
  | "criterion_not_observable"
  | "verifier_mismatch"
  | "external_side_effect"
  | "high_risk"

interface ContractPreflightResult {
  version: 1
  decision: "accept" | "meta_review_required" | "needs_input"
  reasons: PreflightReason[]
  affectedClaimIds: string[]
  affectedCriterionIds: string[]
  safeDefaultAvailable: boolean
  mutatingActionAllowed: boolean
}
```

Natural-language statements may explain a reason, but they must not select retry, question, blocking, or Ready policy.

### 3. Apply a deterministic invocation policy

| Condition | MetaReviewer | User question | Mutation |
|---|---:|---:|---:|
| Clear atomic request, observable criterion, applicable verifier | No | No | Allowed after contract approval |
| Non-blocking preference with a safe default | Optional by profile | No | Allowed with recorded assumption |
| Multiple interpretations that change a required Criterion | Yes, once | Yes if still unresolved | Blocked until resolved |
| Missing value required by a state-changing tool | Yes or direct question | Yes | Blocked |
| High/critical risk, security, deployment, credential, or external effect | Yes | Only for unresolved decisions | Blocked until reviewed |
| Verifier cannot observe the Claim | No approval by reviewer | Yes or unsupported outcome | Blocked from Ready |

The MetaReviewer remains limited to one initial review and one revision re-check. A second model is not required by default.

### 4. Separate question value from model confidence

Question policy should depend on the consequence of choosing incorrectly, not on a model saying that it is uncertain.

```text
Question required
= no safe default
+ required Criterion changes
  or scope/security/external effect changes
  or verifier applicability changes
```

For low-impact preferences, record a visible assumption and continue. For blocking decisions, use the existing Question Service before the first mutating action.

### 5. Keep execution-time validation external

Do not rerun a general MetaReviewer after every tool call. Existing Coordinator and Verifier paths should remain authoritative.

```text
WorkUnit execution
→ Candidate
→ external observation/test/hash
→ scope verification
→ commit or RepairDirective
```

Resume the existing child session only when a failure is mapped to its Claim, Criterion, and write scope. Provider, protocol, verifier, sandbox, and workspace-conflict failures must remain outside implementation repair.

### 6. Add bounded contract revalidation triggers

Contract or Plan revalidation during execution should occur only when a typed event invalidates an earlier assumption.

```ts
type ContractRevalidationTrigger =
  | "new_required_dependency"
  | "scope_expansion_requested"
  | "applicability_changed"
  | "plan_basis_changed"
  | "verifier_became_unavailable"
  | "required_criterion_changed"
```

An ordinary implementation failure does not reopen the GoalContract. It follows local repair. A foundational trigger may reopen the affected contract section once; it does not automatically discard the entire plan.

### 7. Keep final verification non-LLM-authoritative

Final Ready should continue to require:

- approved root GoalContract;
- no pending action or blocking failure;
- full required Claim coverage;
- applicable non-revoked verifier revision;
- required Evidence-family policy;
- root-only Ready attestation.

MetaReviewer output, model confidence, model agreement, and retrieved experience must not satisfy these conditions.

---

## Implementation sequence

### Phase A — Baseline before policy change

Record current metrics for a fixed task set:

- time and tokens before first mutating action;
- MetaReviewer invocation count;
- clarification question count;
- contract revision count;
- post-start contract invalidation count;
- verified completion rate;
- false rejection and later-discovered false Ready cases where an oracle exists.

Use at least clear atomic, ambiguous, multi-claim, high-risk, and unverifiable task classes. Do not set an arbitrary improvement percentage before obtaining this baseline.

### Phase B — Pure Kernel policy

Add the typed Preflight result and deterministic invocation policy to `@base-harness/kernel`.

The Kernel package should remain free of model calls and I/O. It receives a structured contract proposal and risk/capability information and returns only a decision.

### Phase C — Host integration

Update KernelHost so that:

- deterministic Preflight always runs;
- MetaReviewer is called only for `meta_review_required`;
- `needs_input` routes to the existing Question Service;
- mutation remains blocked until the contract is approved;
- review count and trigger reasons are stored in the run manifest.

### Phase D — Runtime revalidation

Connect the bounded `ContractRevalidationTrigger` events to Coordinator without changing Candidate, Overlay, scope verification, or local repair semantics.

### Phase E — Interface and observability

Expose the following in TUI and headless status:

- `preflight: accepted | reviewing | awaiting_input`;
- typed trigger reasons;
- MetaReviewer call count;
- assumptions accepted without a question;
- contract revision and revalidation reason.

Do not expose internal `meta-review` as a user-selectable agent.

### Phase F — Harness-specific evaluation

Compare three policies on the same task set:

| Policy | Purpose |
|---|---|
| Deterministic only | Establish minimum cost and missed-ambiguity baseline |
| Selective review | Proposed production policy |
| Always review | Current safety-oriented baseline |

The selective policy is promotable only when it reduces review/question cost without increasing unsafe mutation, missed blocking ambiguity, or false Ready outcomes on tasks with an external oracle.

---

## Expected impact

| Area | Expected effect | Residual risk |
|---|---|---|
| Request latency | Fewer unnecessary reviewer calls on clear tasks | Preflight itself still has fixed cost |
| Token use | Reduced duplicated contract context | Complex tasks still require review |
| User fatigue | Fewer low-value clarification questions | Incorrect safe-default policy can hide a preference |
| Goal correctness | Earlier blocking of consequential ambiguity | ContractBuilder can fail to expose an interpretation candidate |
| Repair efficiency | Existing local repair remains focused | Foundational contract changes still require bounded revalidation |
| Verification trust | No change to root-only Ready or Evidence authority | Verifier implementation error remains a Trusted Base risk |
| Model diversity cost | No mandatory second model | Same-model common-mode error remains possible |
| Maintainability | Clear separation of Preflight, MetaReview, and Verifier | Additional typed states and telemetry are required |

---

## Acceptance criteria for a future implementation

1. A clear single-target request reaches an approved contract without an LLM MetaReviewer call.
2. A request with two consequential interpretations cannot mutate before resolution.
3. A missing parameter required for an external side effect produces `needs_input` before tool execution.
4. High/critical risk invokes one MetaReviewer even when the contract is structurally complete.
5. MetaReviewer `pass` never creates Evidence, Claim coverage, or Ready.
6. Meta review cannot recursively invoke another MetaReviewer.
7. An ordinary implementation failure uses local repair without reopening GoalContract.
8. A typed foundational change revalidates only the affected contract or plan section.
9. TUI and headless runs produce the same Preflight and question decisions for the same structured input.
10. Selective review is compared with deterministic-only and always-review baselines before promotion.

---

## Result

The research review confirms the existing architecture rather than replacing it.

The current three-section Verification V2, Verified-State authority model, Candidate attestation, local repair, and Evidence lifecycle already provide the external grounding that pure LLM self-review lacks. The most appropriate next change is a small Kernel admission refinement:

```text
unconditional MetaReviewer
→ deterministic Contract Preflight
→ typed selective MetaReviewer
→ consequence-based user question
```

No new recursive verification layer, second Ready authority, or always-on second model is recommended.

---

## Evidence boundary

This document records a research-to-architecture comparison and an implementation proposal. It does not claim that the selective policy has been implemented or that it improves Base Harness until the proposed A/B evaluation is executed.

The following claims are intentionally not made:

- that clarification always improves every task;
- that one independent-context reviewer eliminates common-mode model error;
- that deterministic Preflight can discover every semantic ambiguity;
- that benchmark improvements transfer directly to this Harness;
- that the current Verifier implementation is infallible;
- that a conditional Ready is universal truth outside its recorded GoalContract and applicability.
# Normative implementation wording

The implemented boundary is **LLM-assisted detection + deterministic Kernel adjudication**. The LLM may propose semantic uncertainty candidates, but it cannot decide whether mutation, user input, or MetaReview is allowed. That decision is made by typed Kernel policy from candidate bindings, contract risk, verification profile, applicability, and contract complexity.

