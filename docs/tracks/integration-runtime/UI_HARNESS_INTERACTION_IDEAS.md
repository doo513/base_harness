# UI ↔ Harness Interaction Ideas

Status: **proposal only — not implemented**

This note proposes ways to expose existing Harness mechanisms through a terminal UX without moving authority into the UI. The visual direction may borrow familiar interaction patterns from conversational coding terminals such as Claude Code, Codex CLI, OpenCode, Antigravity-style consoles, and similar agent shells, but the Harness runtime remains the source of truth.

## Design invariant

```text
User / TUI
   ↓ request, inspect, approve explicit UI choices
Task Intake / Runtime
   ↓
Actor plan + tools
   ↓
Evidence / verification / progress / recovery
   ↓
Harness-side completion oracle
   ↓
FinalResult
   ↓
TUI presentation
```

The TUI may present, filter, or navigate trusted runtime state. It must not synthesize trusted facts, bypass permissions, or manufacture completion.

---

## 1. Plan Rail — plan/checklist ↔ progress control

### UX

Show the current actor plan as a compact collapsible rail next to the transcript:

```text
Plan
  ✓ map repository
  ● inspect entry points
  ○ trace data flow
  ○ write report
  ○ recheck deliverable
```

Default view stays compact; `/plan` or a keyboard shortcut could expand details.

### Harness mapping

- `agent.plan.replaced`
- `agent.task.updated`
- deterministic progress-controller milestones
- task workflow phases from the selected profile/task overlay

### Boundary

The plan is actor bookkeeping, not trusted truth. Checking a box in the UI must not mark a semantic claim as verified or complete the run.

---

## 2. Evidence Lens — tool activity ↔ evidence / verified facts

### UX

Keep the transcript concise, but allow a selected tool/read event to expand into an evidence card:

```text
● Read  src/pipeline.py
  evidence: artifact:read:17
  used by: architecture.pipeline
  status: observed
```

A future `/evidence` view could filter:

- observations
- promoted verified facts
- rejected hypotheses
- artifact references

### Harness mapping

- `state.observations`
- `evidence_refs`
- verified-fact state
- verification assessments
- persisted run artifacts

### Boundary

The UI only renders evidence already recorded by the runtime. It never upgrades an observation into a verified fact.

---

## 3. Verification Gate Card — completion request ↔ oracle status

### UX

When the actor asks to finish, render a small gate card instead of a generic success line:

```text
Completion gate
  ✓ artifact exists
  ✓ project evidence collected
  ✓ source file inspected
  ! one requested section missing

  continuing…
```

After acceptance:

```text
✓ Verified completion
  oracle: evidence_backed_artifact_oracle
```

### Harness mapping

- claim verification registry
- verification contracts
- completion oracle result
- coverage/evidence fields in `CompletionResult`

### Boundary

There is no UI `force success` control. The card explains the oracle; the oracle remains Harness-owned.

---

## 4. Recovery Timeline — failures ↔ deterministic recovery / resume

### UX

Compress repetitive retry logs into one timeline item:

```text
↻ Recovery 2/3
  cause      tool timeout
  action     retry with narrower scope
  checkpoint run/…/checkpoint.json
```

Allow `/inspect` to expand prior recovery decisions and `/resume` to continue from persisted state.

### Harness mapping

- failure taxonomy
- recovery transitions
- strategy changes
- progress controller
- durable checkpoint / resume state

### Boundary

The UI may request stop/resume, but it does not invent a recovery transition. Runtime recovery policy remains authoritative.

---

## 5. Context & Capability Strip — context governor ↔ skills/tools/retrieval

### UX

A compact status strip can explain what the actor currently has available without forcing the user to select everything manually:

```text
context  18k/64k  │ tools 7 │ skills 2 │ retrieval on │ network allow
```

Expandable views could show:

- projected context sources
- active/relevant skill guidance
- available tool contracts
- retrieval admissions/rejections
- current execution/security policy

### Harness mapping

- Context Governor
- retrieval/memory gateway
- Skill Catalog / future Skill Router
- Tool Registry / capability gates
- security config

### Boundary

Skill visibility is not tool authority. Retrieval visibility is not trusted truth. Capability changes must still pass the normal Harness configuration/permission path.

---

## Suggested order if implemented later

1. Plan Rail
2. Verification Gate Card
3. Evidence Lens
4. Recovery Timeline
5. Context & Capability Strip

This order provides immediate usability while preserving the current architecture: first expose state that already exists, then add richer inspection surfaces. No new multi-agent or autonomous-skill authority is required for these UI features.
