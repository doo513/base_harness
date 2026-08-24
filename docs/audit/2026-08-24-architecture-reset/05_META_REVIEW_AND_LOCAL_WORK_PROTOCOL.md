# Meta Review Log and Local Work Protocol

Date: 2026-08-24

This document has two purposes:

1. record the meta re-check performed between each audit work unit;
2. define the mandatory local workflow before future implementation slices.

---

# Part I — Meta review log for this audit

## Work 1 — Historical source reconstruction

### Work performed

- identified initial commit `35cbce265852ce5cc689ad1b4cfde14e3fb76221`;
- inspected initial `docs/architecture.md` and old Codex-oriented hooks/skills/config;
- identified explicit standalone pivot `48fc5efa32ca50c77c31e86f01de649615811154`;
- inspected Stage-02 direction and handoff architecture;
- identified later Integration Runtime track and its own phase chronology.

### Meta re-check

Initial temptation:

```text
current complexity != June architecture
→ current architecture is wrong
```

Rejected because the August standalone conversion was explicit and intentional.

Adjusted criterion:

```text
Genesis product shape = historical restraint evidence
Verified-State authority invariants = current absolute criterion
```

### Closing comment

**Proceed.** The history contains a real intentional product pivot, so documents must be classified by epoch rather than read as one continuous specification.

---

## Work 2 — Document reclassification

### Work performed

Classified material into:

```text
Genesis Thin Harness
Verified-State Research Kernel
Execution Operationalization
Integration Runtime Expansion
Windows/Live Incident Remediation
Model/Memory/Context Compatibility
Failure/Provider Hardening
Architecture Reset Audit
```

Added current-authority labels rather than physically moving historical files.

### Meta re-check

Question:

> Should obsolete docs be moved into archive or edited to reflect current behavior?

Decision:

**No during this audit.** Historical documents are evidence. Moving or rewriting them destroys easy path/commit correlation and may make past decisions look cleaner than they were.

### Closing comment

**Proceed.** Reclassification is an overlay/index, not history rewriting.

---

## Work 3 — Canonical direction review

### Work performed

Reviewed core areas against:

- Genesis restraint;
- Verified-State authority;
- documentation/executable/evidence consistency.

### Meta re-check

Question:

> Do live failures show that Verified-State Core should be replaced by another agent runtime?

Decision:

**No.** Most observed operational failures occur at or above model/tool/OS/retrieval/UI integration boundaries. The core trust model continues to provide useful fail-closed guarantees.

New finding:

```text
Trusted Progress
and
Execution Liveness
```

must be distinct concepts.

### Closing comment

**Proceed with Shell/Core convergence, not Core rewrite.**

---

## Work 4 — Causal problem atlas

### Work performed

Mapped symptoms to causal boundaries and current status.

Major chain:

```text
missing portable mutation/runtime tools
→ model-generated OS shell syntax
→ failed/no-op changes
→ more inspection
→ delayed verified progress
→ no-progress recovery
→ optional retrieval/provider path
→ budget depletion
→ weak operational resume trajectory
```

### Meta re-check

Question:

> Could this be solved by only raising no-progress thresholds?

Decision:

**No.** That hides the symptom and lets genuine loops run longer. The root includes missing portable tool primitives and progress/liveness coupling.

Question:

> Could all successful tool activity reset progress?

Decision:

**No.** That violates Stage-06 anti-gaming goals.

### Closing comment

**Proceed only with a two-channel progress/liveness design and portable tool baseline first.**

---

## Work 5 — Proposal comparison

### Compared

```text
A. Continue current patch-by-patch hardening
B. Host base_harness inside another agent
C. Standalone own Agent Shell + Verified-State Core
```

### Meta re-check

A is valuable for confirmed defects but weak as a long-term architecture method.

B has high short-term operational maturity but weakens independent product identity and experiment attribution.

C preserves the existing Kernel and allows known-agent design patterns to be reused without making another agent the host authority.

### Closing comment

**Recommendation: C.** Implement incrementally; no big-bang package rewrite.

---

# Part II — Mandatory local work protocol

Every future implementation slice should use this exact sequence.

## Step 0 — Pin local evidence state

Record:

```text
git branch --show-current
git rev-parse HEAD
git status --short
python --version
```

If the task is platform-sensitive, also record:

```text
OS
shell
sys.executable
workspace path
execution backend
```

Do not begin from an unknown dirty tree.

---

## Step 1 — Restate the problem as a causal claim

Template:

```text
Observed symptom:

Immediate failure boundary:

Claimed root cause:

Evidence supporting root cause:

Alternative explanations not yet excluded:

Affected canonical invariant:

Current source locations:
```

If only the symptom is known, the task is investigation, not implementation.

---

## Step 2 — Check whether the criticism is stale

Before planning a fix:

```text
rg current source
read latest audit/hardening docs
inspect relevant tests
inspect git log for recent fixes
```

Classify:

```text
CURRENT
PARTIALLY FIXED
RESOLVED
HISTORICAL ONLY
```

Do not re-implement a fix because an older phase document still describes the old state.

---

## Step 3 — Assign ownership: Core or Agent Shell

Mandatory question:

> If the implementation were replaced by another OS/provider/TUI/MCP transport, would the Verified-State meaning change?

If **no**, the mechanism probably belongs in Agent Shell/integration.

If it directly decides:

```text
trusted truth
permission authority
evidence admission
durable recovery meaning
accepted completion
```

it belongs in Core or in a Core-owned policy contract.

Write the ownership decision in the commit/work note before code changes.

---

## Step 4 — Compare proposed change with current proposal

Use `04_PROPOSAL_COMPARISON_AND_NEXT_ARCHITECTURE.md`.

For every change write:

```text
Reset phase: R0..R9
Why now:
Why not later:
What old implementation is reused:
What is explicitly not changed:
```

If the work does not fit a reset phase, either the proposal needs revision or the work is opportunistic scope creep.

---

## Step 5 — Write the failing characterization test first where practical

Examples:

### Cross-platform tool issue

```text
same file.write contract
→ Windows
→ Linux
→ identical logical workspace result
```

### Progress/liveness issue

```text
read → read → patch → test
must not false-trigger
```

and adversarial counter-case:

```text
novel read loop
must still terminate
```

### Retrieval capability issue

```text
retrieval unavailable at run start
→ not advertised to Actor
```

### Failure routing issue

```text
same FailureContext
→ same PolicyDecision
independent of Python exception subclass
```

---

## Step 6 — Implement the smallest boundary-correct change

Rules:

1. Prefer a new adapter/contract over provider/OS special cases inside Core.
2. Do not weaken verifier/oracle requirements to make a run pass.
3. Do not repair model semantics by guessing.
4. Do not turn activity into trusted progress.
5. Do not add hidden fallback behavior.
6. Preserve failure evidence and provenance.
7. Avoid unrelated cleanup in the same commit.

---

## Step 7 — Run layered validation

Minimum:

```text
targeted new regression
relevant existing test family
full pytest when boundary changed
core-freeze/stage gates when Core touched
platform-specific replay when the bug is platform-specific
```

A Linux CI pass cannot close a Windows-only causal claim by itself.

---

## Step 8 — Mandatory meta re-check before next task

Answer briefly:

```text
1. Did the test prove the root cause or only remove the symptom?
2. Did responsibility move to the correct layer?
3. Did any new authority path appear?
4. Did the change create a new platform/provider assumption?
5. Did a previous invariant/test have to be weakened?
6. Is the next proposed task still the highest causal blocker?
```

Then leave a short work comment:

```text
Meta result: PASS / ADJUST / STOP
Evidence:
Residual risk:
Next allowed work:
```

No next implementation slice begins before this comment exists.

---

## Step 9 — Update documents by status, not optimism

Every implementation note must have separate sections:

```text
Current implementation
Validated evidence
Remaining limitation
Future target (NOT implemented)
```

Never write future architecture in the same tense as current code.

---

# Part III — Local first-pass checklist for the next session

The next local session should **not immediately implement R1**. First run a short evidence refresh:

```text
git checkout develop
git pull --ff-only
git rev-parse HEAD
git status --short
```

Then inspect:

```text
README.md
docs/audit/2026-08-24-architecture-reset/00_AUDIT_INDEX.md
docs/audit/2026-08-24-architecture-reset/02_CANONICAL_DIRECTION_META_REVIEW.md
docs/audit/2026-08-24-architecture-reset/03_CAUSAL_PROBLEM_ATLAS.md
docs/audit/2026-08-24-architecture-reset/04_PROPOSAL_COMPARISON_AND_NEXT_ARCHITECTURE.md
```

Run the keyword searches from the causal atlas and compare the local HEAD to the source SHAs referenced by the historical docs.

Only then prepare an **R1 Contract Fence implementation plan**.

---

# Final audit meta comment

```text
Meta result: PASS WITH ARCHITECTURE ADJUSTMENT

Preserve:
- Verified-State authority/evidence Kernel
- Stage 02–08 security/integrity invariants
- latest failure/provider hardening

Adjust:
- explicit Agent Shell boundary
- portable developer tool primitives
- progress vs liveness separation
- run capability negotiation
- tool failure normalization
- durable approval bridge

Do not claim solved:
- universal plugin/process OS sandbox
- semantic context quality
- interactive persisted approval
- remote HTTP MCP built-in support
- Windows/Linux parity for model-generated shell escape-hatch commands
```
