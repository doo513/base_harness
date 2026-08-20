# Base Harness Recent Evolution — Evidence-Based Causal Report

Date: 2026-08-20

Repository: `doo513/base_harness`

Scope: recent usability/integration changes leading to the current `main` state, with emphasis on provider/MCP connections, TUI evolution, run lifecycle, task intake, workspace handling, evidence-backed deliverables, final result presentation, and architectural compatibility with the verified-state kernel.

---

## 1. Executive summary

The recent changes were not a single feature addition. They were a sequence of corrections driven by concrete usability failures:

```text
connection/config friction
        ↓
skill/catalog + provider/MCP actions
        ↓
MCP UI/runtime mismatch discovered
        ↓
stdio-only correction
        ↓
run-directory reuse produced traceback
        ↓
fresh-run lifecycle + actionable CLI error
        ↓
menu/dashboard TUI felt too configuration-heavy
        ↓
prompt-first OpenCode-style UI
        ↓
conversation/transcript UX requested
        ↓
Claude Code / Antigravity-style conversational TUI
        ↓
real analysis request produced repeated recovery and no useful result
        ↓
workspace/task-intake gap + completion-contract gap + result-channel gap identified
        ↓
bounded task intake
        ↓
evidence-backed artifact task overlay
        ↓
final_result.json + user-facing result presentation
```

The important architectural conclusion is that these changes remain outside the frozen verified-state kernel. They extend the product/integration layer around the kernel rather than replacing its authority model.

The current design is therefore:

```text
Natural-language request
        ↓
Task Intake                     ← new integration layer
        ↓
Workspace / deliverable binding
        ↓
Selected Domain Profile
        +
Optional task-specific contract ← new task overlay
        ↓
Existing LLM Controller
        ↓
Existing Verified-State Kernel
  ├─ tool authority
  ├─ evidence
  ├─ verification
  ├─ progress control
  ├─ recovery
  └─ completion oracle
        ↓
Final Result Presenter          ← new output layer
```

This preserves the project invariant:

> The actor/model may plan, propose and act, but trusted truth and accepted completion remain harness-side decisions.

---

## 2. Evidence method

This report separates evidence into three classes.

### 2.1 Repository-attested evidence

Primary evidence:

- commit history and commit diffs;
- current source files;
- test additions;
- CI ledger in `docs/tracks/integration-runtime/CI_STATUS.md`;
- `main` branch compare results.

### 2.2 Operational evidence

Some design changes were triggered by terminal behavior observed during manual use, for example:

- a non-empty run directory raising `ResumeConflict` as a traceback;
- analysis requests ending with repeated failure/recovery and zero useful tool progress;
- a chat-only local model giving a natural answer while the Harness produced little user-facing explanation.

These observations explain why work was prioritized, but where the raw terminal session is not committed to the repository they are treated as development observations, not immutable repository evidence.

### 2.3 Architecture evidence

The architectural compatibility claim is checked structurally:

- `WorkspaceContract` still owns the actor filesystem boundary;
- core decision kinds and controller authority remain unchanged;
- task-specific completion is implemented as a profile overlay rather than kernel mutation;
- a compare from `80ab65e` to `9406f3b` contains no `src/harness/core/*` changes.

---

# Part I — Connection and capability UX

## 3. Problem: connection setup was too manual

Early usage required the user to understand configuration details before doing actual work. Provider credentials, model routing and MCP configuration were operationally separate concerns, but they surfaced too directly in ordinary use.

The intended experience became:

```text
user task first
configuration only when needed
```

rather than:

```text
edit config
export variables
select mode
select tool
then start task
```

## 4. Skill/catalog layer was introduced

### Evidence

Relevant commits:

- `c5574b5` — `feat(tui): add progressive skill catalog`
- `c2d19b1` — `feat(tui): add provider and MCP skill actions`
- `04a2d5e` — `feat(tui): package built-in harness skills`
- `b02c228` — `feat(tui): add provider connection skill`
- `33fc0f8` — `feat(tui): add MCP discovery skill`
- `9934001` — `feat(tui): add MCP configuration skill`
- `06837d2` — `feat(tui): make task-first UI and skill-driven connections`

`c2d19b1` introduced `src/harness/skill_actions.py` with:

- `ProviderPreset`;
- presets for Gemini, OpenAI, OpenAI-compatible endpoints and Ollama;
- `configure_provider()`;
- `configure_mcp()`;
- MCP Registry search;
- validation of model aliases and environment-variable names.

The key security decision was explicit in `configure_provider()`:

```text
persist env reference
never persist raw API key
```

For example the config stores:

```toml
api_key = "env:GEMINI_API_KEY"
```

rather than the credential value.

### Causal effect

This reduced direct TOML editing and provided a reusable connection layer while keeping credential storage outside Harness ownership.

### Why this did not become the primary user workflow

Later design discussion clarified that skills should not be something a user must manually select for every ordinary task. The current interpretation is:

```text
Skill = reusable guidance / connection capability
Task request = primary interface
```

This is more consistent with the existing actor planning model.

---

## 5. Problem discovered: configuration surface exceeded runtime support

The first MCP connection helper accepted both `stdio` and `http`, but the actual current MCP gateway only executes the existing stdio runtime path.

### Evidence

Commit `2ac5d4b` — `fix(tui): align skills with current MCP/runtime support`

The patch removed the HTTP choice from the interactive TUI and changed the visible configuration flow to:

```text
Transport: stdio (current mcp-gateway-v1 runtime)
```

It also corrected workspace-local skill catalog lookup to use the current workspace rather than an unset/ambiguous default.

Follow-up test/documentation commits:

- `302bcaa` — lock skill workspace and MCP transport boundaries;
- `80ab65e` — align MCP skill documentation with stdio runtime.

### Causal lesson

A configuration schema must not imply an execution capability that the runtime does not actually provide.

This established a recurring rule used later in the project:

> The TUI should expose only capabilities that the runtime can execute and verify now.

---

# Part II — Run lifecycle and terminal UX

## 6. Problem: reusing `./run` caused an internal traceback

A normal repeated invocation could hit an already-populated run directory and surface:

```text
ResumeConflict: run directory is not empty
```

The underlying kernel behavior was correct: a new run must not overwrite an existing persisted run. The product-layer problem was that this internal exception leaked directly to the user.

### Evidence

Commit `08121a2` — `fix(cli): report run-directory conflicts without traceback`

The CLI now catches `ResumeConflict` and explains the valid choices:

- resume the existing run;
- choose a fresh run directory.

Follow-up tests:

- `8910ff0` — fresh TUI run-directory defaults;
- `b525705` — actionable CLI run-directory conflict error.

Documentation:

- `6e9b60d` — run-directory lifecycle and TUI refresh instructions.

### Causal lesson

The persistence contract should remain strict, but strictness should be presented as an actionable workflow rather than an internal Python failure.

---

## 7. First major UI change: task-first visual console

### Evidence

Commit `786c94e` — `feat(tui): add OpenCode-style task console`

This added a task-first visual surface with:

- workspace/model/status display;
- direct task entry;
- `/connect`, `/models`, `/mcp`, `/skills`, `/mode`, `/accept` controls;
- automatic acceptance-command detection;
- session-only credential input.

Related commits:

- `5f24ed6` — point installed TUI command at the visual console;
- `ca92cf9` — helper tests;
- `8e0b090` — documentation and Linux `python3` workflow.

### Why this was still insufficient

The UI was visually clearer, but it still behaved too much like a dashboard/menu. The desired interaction was closer to coding-agent CLIs where:

```text
conversation transcript is primary
slash commands are secondary
```

---

## 8. Second major UI change: Claude Code / Antigravity-style transcript

### Evidence

Commit `acd43b9` — `feat(tui): rebuild console in Claude Code and Antigravity style`

The visual console was reworked around `prompt-toolkit`:

- persistent terminal transcript;
- slash command completion;
- command/model completion;
- bottom toolbar;
- inline plan/tool/verification/recovery events;
- password-style credential prompt;
- prompt history suggestions.

Supporting commits:

- `6e50374` — add `prompt-toolkit` dependency;
- `1ede688` — version bump to `0.10.0`;
- `c1433c5` — conversational session tests;
- `221fa0f` — README aligned to conversational CLI.

### CI regression and correction

Adding `prompt-toolkit` initially caused the locked CI install path to fail because CI installs the project with `--no-deps` after installing `requirements-ci.lock`.

Commit:

- `790aafd` — `build(ci): lock prompt-toolkit TUI dependencies`

This is an important causal example: the UI worked conceptually, but release reproducibility required the new dependency to be represented in the CI lock as well.

### Causal lesson

A UI dependency is still a runtime/release dependency. The product layer cannot bypass reproducibility rules simply because the feature is “only TUI”.

---

# Part III — Why analysis/report tasks failed

## 9. Observed failure pattern

A project-analysis request exposed a more important limitation than visual polish.

The observed behavior was approximately:

```text
user asks for deep project analysis/report
        ↓
Harness starts in normal software workflow
        ↓
no suitable deterministic test-style completion for the requested deliverable
        ↓
actor fails to establish productive file/tool work
        ↓
recovery/strategy transitions repeat
        ↓
run exhausts without a useful final answer
```

The important diagnosis was not simply “a Research mode is missing.”

Three separate architectural issues were identified:

1. the requested project path could differ from the TUI's current workspace;
2. report/document tasks need a different completion contract than code/test tasks;
3. persisted events were not translated into a useful final answer for the user.

---

## 10. Workspace analysis: why the LLM cannot simply follow any path in the prompt

The existing security model deliberately prevents this.

`src/harness/core/workspace.py` defines `WorkspaceContract`:

```text
root = one fixed actor project root
managed directories must remain under root
tool execution workspaces must remain under root
absolute actor paths are rejected
path escape is rejected
```

`src/harness/core/workspace_tools.py` implements `file.read`, `directory.list` and `file.search` using that contract.

Therefore this behavior would be architecturally wrong:

```text
LLM sees arbitrary path in text
→ LLM silently expands its own filesystem authority
```

The correct design is:

```text
user explicitly names a target directory
→ pre-runtime intake resolves it
→ WorkspaceContract.root is built from that user-authorized directory
→ actor still receives only the resulting bounded workspace
```

---

# Part IV — Task intake and evidence-backed deliverables

## 11. Bounded task intake

### Evidence

Commit `408fd23` — `feat: add bounded task intake for explicit workspace and artifact requests`

New file:

- `src/harness/task_intake.py`

Behavior:

### Workspace detection

Only explicit, existing directories are candidates.

If exactly one candidate resolves:

```text
requested_workspace = resolved directory
```

If more than one existing directory is found:

```text
workspace_ambiguous = true
```

and no automatic workspace choice is made.

On non-Windows systems, a Windows path such as:

```text
C:\Users\...\project
```

can be localized to:

```text
/mnt/c/Users/.../project
```

for WSL-style use.

### Deliverable detection

Report/document terms are recognized and mapped to an artifact target.

If no explicit Markdown filename is given, the default is:

```text
PROJECT_ANALYSIS_REPORT.md
```

### Why this remains within the original design

This happens before runtime construction. The actor itself never receives authority to mutate `WorkspaceContract.root`.

---

## 12. Decision: do not add automatic Research mode switching

A separate automatic `research` mode was considered and rejected for the current implementation.

Reason:

The existing architecture already separates:

```text
Domain Profile
= available tools, domain verification semantics, security context

Task-specific requirement
= what this particular user request must produce
```

Automatically replacing `software` with `research` would mix those concerns and create a new routing authority that could choose the wrong domain.

Instead the chosen design is:

```text
current profile
+
task-specific artifact completion overlay
```

This keeps `/mode` as an explicit user/operator override rather than a hidden classifier decision.

---

## 13. Evidence-backed artifact task contract

### Evidence

Commit `2f3834f` — `feat: add evidence-backed artifact task contract`

New file:

- `src/harness/task_contracts.py`

Two major components were added.

### 13.1 `EvidenceArtifactTaskProfile`

This is a profile overlay rather than a new domain mode.

It delegates to the selected base profile for:

- tools;
- verifiers;
- minimum verification level;
- claim-verification registry;
- evaluation contract.

It adds task-specific workflow guidance:

```text
plan
→ inspect
→ evidence
→ analyze
→ synthesize
→ recheck
→ acceptance
```

Important constraints include:

- start from an explicit checklist/plan;
- inspect relevant source before synthesis;
- base findings on observed workspace evidence;
- recheck the output against the original request before completion.

The checklist remains actor bookkeeping only; it does not become trusted truth.

### 13.2 `EvidenceBackedArtifactOracle`

The completion oracle rejects the task unless all of the following hold:

1. artifact target stays inside workspace;
2. enough successful direct workspace evidence was recorded;
3. at least one `file.read` occurred;
4. requested artifact exists;
5. artifact is readable;
6. artifact is non-trivially sized.

On acceptance it records:

- artifact SHA-256;
- artifact size;
- workspace evidence references;
- workspace evidence count;
- source-file read count.

### What this oracle proves

It proves a useful minimum property:

> The requested document was produced after actual project inspection and exists as a concrete workspace artifact.

### What it does not prove

It does **not** prove that every sentence in a report is semantically correct or that every report claim is individually traceable to a specific source line.

That distinction is important. The change prevents evidence-free synthesis, but deeper report-claim verification remains future work.

---

## 14. CLI integration

### Evidence

Commit `4f2ddc7` — `feat: support evidence-backed artifact task contracts`

The CLI gained:

```text
--artifact-target <relative path>
```

When present, the selected profile is wrapped in `EvidenceArtifactTaskProfile`.

This means task intake is not coupled only to the TUI; the same behavior can be invoked non-interactively.

The environment bridge:

```text
HARNESS_TASK_ARTIFACT_TARGET
```

allows the conversational front-end to pass the detected deliverable into the ordinary CLI boundary without bypassing it.

This is a significant architectural choice:

```text
TUI
→ declarative launch request
→ existing CLI
→ existing runtime
```

rather than allowing the TUI to instantiate a separate privileged runtime path.

---

# Part V — Final result channel

## 15. Problem: persisted evidence existed but the user had no useful final answer

The runtime already had:

- event logs;
- checkpoints;
- artifacts;
- evidence refs;
- metrics.

But these are operational/audit structures, not a good final-answer interface.

A user should not need to inspect `events.jsonl` manually to discover whether an analysis succeeded or where the requested report was written.

---

## 16. Deterministic final result artifact

### Evidence

Commit `b0898cf` — `feat: persist evidence-oriented final run result`

New file:

- `src/harness/final_result.py`

Each run now produces:

```text
<run-dir>/final_result.json
```

The schema records:

- completion state;
- step count;
- workspace;
- requested artifact metadata;
- artifact SHA-256 and size when present;
- registered evidence refs;
- successful workspace observations;
- verified facts;
- recent failures.

The artifact path is rechecked to prevent absolute/parent-escape targets from being presented as valid output.

### Causal effect

This creates a stable boundary between:

```text
internal runtime state
```

and:

```text
user-facing result presentation
```

without asking the model to invent its own completion status.

---

# Part VI — Current conversational front-end

## 17. Friendly task-intake conversation front-end

### Evidence

Commit `60e78cd` — `feat(tui): add friendly task-intake conversation frontend`

New file:

- `src/harness/tui_conversation.py`

The front-end:

- accepts the normal user task directly;
- runs task intake before launching the runtime;
- switches workspace only when the user supplied one unambiguous existing directory;
- detects report deliverables;
- uses the artifact task contract without changing profile mode;
- hides low-value internal events such as `state.snapshot`;
- renders plan/tool/verification/recovery events with user-oriented labels;
- reads `final_result.json` and presents evidence/output/failure summary.

Examples of visible event classes:

```text
◇ Plan
● Tool
✓ Verify
↻ Retry
✕ Issue
✓ Final
```

### Entry point evidence

Commit `d845de3` changes:

```toml
verified-harness-tui = "harness.tui_conversation:main"
```

so the friendly conversation front-end is now the installed default rather than the older visual console.

The older TUI module remains useful as shared compatibility/helper code; the kernel and CLI remain the execution authority.

---

# Part VII — Test and CI evidence

## 18. New focused tests

Relevant commits:

- `3ac52df` — task intake and evidence-backed artifact completion tests;
- `9c912a0` — final-result persistence tests.

The tests cover core product-layer properties including:

- explicit single workspace resolution;
- ambiguous path behavior;
- report artifact detection;
- evidence-gated completion;
- final result serialization.

Earlier TUI lifecycle and connection behavior was also covered by dedicated TUI/CLI tests.

---

## 19. Full regression result

CI bot commit `cd2e7d3` records validation of source commit `9406f3b`.

Result:

```text
292 passed
7 skipped
```

The gate ledger records PASS for:

- compile;
- CLI module;
- TUI module;
- CLI console entry point;
- TUI console entry point;
- full pytest;
- core freeze audit;
- Stage 03 resume;
- Stage 04 semantic and real-world probes;
- Stage 05 recovery probes;
- Stage 06 progress probes;
- Stage 07 context probes;
- Stage 08 retrieval/memory probes;
- Stage 02 isolation/binding probes.

Current evidence file:

```text
docs/tracks/integration-runtime/CI_STATUS.md
```

---

# Part VIII — Did the recent work diverge from the original Harness architecture?

## 20. Structural comparison

A repository compare from:

```text
80ab65e
```

to:

```text
9406f3b
```

shows the recent changes concentrated in:

- `README.md`;
- CI evidence;
- package/TUI entry point;
- `src/harness/cli.py`;
- `src/harness/final_result.py`;
- `src/harness/task_contracts.py`;
- `src/harness/task_intake.py`;
- TUI modules;
- focused tests.

No `src/harness/core/*` file appears in that compare.

Therefore the recent behavior is best classified as:

```text
integration/product-layer extension
```

not:

```text
verified-state kernel redesign
```

---

## 21. Original invariants preserved

### 21.1 Workspace authority

Before:

```text
WorkspaceContract.root is kernel-side execution boundary
```

Now:

```text
Task Intake may select the user-explicit root before runtime
WorkspaceContract still enforces it during runtime
```

Preserved.

### 21.2 Actor planning

Before:

```text
actor can create plan/task bookkeeping
```

Now:

```text
artifact workflow asks actor to use that planning more deliberately
```

No new truth authority was granted.

Preserved.

### 21.3 Tool authority

No Skill, task intake or TUI feature directly executes outside the existing tool/runtime path.

Preserved.

### 21.4 Verification and completion

The report task does not trust model prose as completion. A harness-side oracle checks the artifact/evidence preconditions.

Preserved.

### 21.5 Persistence and auditability

The new final result is an additional deterministic projection; existing checkpoint/event/artifact persistence remains intact.

Preserved.

---

# Part IX — Current usage model

## 22. Normal user workflow

The intended default is now:

```text
1. start TUI
2. type task normally
3. let actor create plan/checklist
4. Harness runs tools and records evidence
5. actor rechecks work
6. completion oracle accepts/rejects
7. TUI prints result
```

Users normally do not need to manually choose a Skill or switch mode.

Slash commands are overrides/controls.

---

## 23. Development example

```text
❯ 로그인 API에 rate limit 추가하고 회귀 테스트까지 해줘
```

Expected flow:

```text
current workspace
→ software profile
→ actor plan
→ inspect/edit/test tools
→ deterministic acceptance command
→ completion oracle
→ final result
```

---

## 24. Project analysis example

```text
❯ "C:\Users\me\Downloads\realtime_ocr" 분석해서 딥한 보고서 써줘
```

Expected flow:

```text
explicit path
→ pre-runtime WSL/path localization if needed
→ WorkspaceContract.root = requested project
→ current profile retained
→ artifact target = PROJECT_ANALYSIS_REPORT.md
→ EvidenceArtifactTaskProfile overlay
→ plan/checklist
→ directory/source evidence
→ synthesis
→ re-read/recheck
→ EvidenceBackedArtifactOracle
→ final_result.json
→ TUI output/preview
```

---

# Part X — Current limitations and risks

## 25. Path intake is intentionally conservative

Current behavior only auto-selects one explicit, existing directory.

Limitations:

- multiple project paths require `/workspace` or future richer multi-root semantics;
- heuristic parsing can miss unusual path syntax;
- the feature does not grant cross-workspace actor access.

This is a deliberate safety trade-off.

---

## 26. Artifact-task detection is heuristic

Report detection currently uses explicit report/document terms and optional `.md` filename recognition.

Potential issues:

- false negative for novel wording;
- false positive if “report” is mentioned without requesting a deliverable;
- only the current artifact contract is generalized; richer output types are not yet modeled.

A future classifier may improve intake, but it should not silently gain authority to broaden workspace/tool permissions.

---

## 27. Evidence gate is not yet semantic citation verification

The artifact oracle currently checks that real project evidence was gathered before synthesis.

It does not yet enforce:

```text
every important report claim
→ explicit supporting artifact/source span
→ claim-class verifier
```

This is the largest remaining verification gap for “deep research/report” quality.

---

## 28. Local provider endpoint recovery is not yet implemented

A proposed WSL/Ollama fallback such as:

```text
127.0.0.1
→ WSL gateway
→ host.docker.internal
```

was deliberately not added during the task-intake work because the observed `tools 0` analysis failure was not proven to be caused by endpoint reachability.

Future work should implement this, if needed, as a general local-provider endpoint resolver rather than an Ollama-only special case.

---

## 29. Credentials remain intentionally external/process-scoped

Harness does not own a persistent SecretStore.

Interactive API keys can be held for the current TUI process, while persistent credentials remain the responsibility of OS/shell/CI secret management.

This reduces Harness-owned secret attack surface at the cost of requiring credential re-entry after restarting a session unless an environment-managed credential already exists.

---

## 30. Custom provider UX still has room to improve

OpenAI-compatible endpoints can be configured through the generic connection path, but multiple custom provider aliases and richer provider-specific authentication still need a cleaner interactive registration model.

This is a product-layer issue, not a kernel limitation.

---

# Part XI — Recommended next validation

## 31. Highest-value next experiment

The next meaningful validation should not be another synthetic UI test. It should run a real project-analysis task end-to-end against a representative project such as `realtime_ocr`.

Measure:

```text
workspace correctly selected?
plan created?
tool calls > 0?
source files actually read?
report created?
report completion accepted?
final_result.json coherent?
terminal output understandable?
unsupported claims present?
wall time / model calls / recovery count?
```

Run this with at least:

- one strong hosted model;
- one realistic local model that is intended for daily use.

This would distinguish product-flow correctness from model-capability limitations.

---

## 32. Verification improvement after real E2E

If real reports are created but contain unsupported conclusions, the next layer should be claim-to-evidence traceability rather than another new mode.

Candidate direction:

```text
report finding
→ structured claim
→ evidence_refs
→ evidence/source verifier
→ verified/supported/unsupported label
→ report quality gate
```

This extends the existing evidence/verification philosophy directly.

---

# Part XII — Final assessment

## 33. Current state

The recent development cycle moved Base Harness from a mostly kernel/CLI-oriented system toward a usable task-oriented agent interface.

The most important advances are not cosmetic:

1. provider/MCP connection behavior became explicit and bounded;
2. run persistence errors became user-actionable;
3. the TUI became prompt-first and conversational;
4. user-explicit project paths can safely influence workspace selection before runtime;
5. analysis/report requests can use evidence-backed deliverable completion without inventing a separate automatic Research mode;
6. each run now has a deterministic final-result projection;
7. the TUI presents useful output instead of raw internal state churn.

## 34. Architectural verdict

**The current changes remain aligned with the original Harness architecture.**

The actor still performs problem analysis and planning. Skills remain optional reusable guidance. Task intake interprets user authority before execution. The Kernel still controls execution boundaries, evidence, trusted-state promotion, progress/recovery, and completion.

The resulting design is closer to the original intent:

```text
User request
   ↓
Harness prepares the safe problem-solving environment
   ↓
Actor analyzes the problem and builds a plan
   ↓
Actor chooses/uses available capabilities
   ↓
Harness records evidence and checks plan/result boundaries
   ↓
Actor repairs gaps
   ↓
Harness verifies completion
   ↓
User receives a concrete result and audit trail
```

## 35. Evidence snapshot

Current validated source at the time of this report:

```text
9406f3bddff8477e95b63025f14effda49a7348d
```

CI evidence commit:

```text
cd2e7d39e52536b30c7e2822270e889a395a22e9
```

Validation:

```text
292 passed
7 skipped
core-freeze-audit PASS
Stage 02–08 regression/probes PASS
CLI/TUI entry points PASS
```

This supports the conclusion that the integration changes were added without regressing the established verified-state core gates.