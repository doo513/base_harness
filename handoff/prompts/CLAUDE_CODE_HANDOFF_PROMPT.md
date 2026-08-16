# Claude Code Handoff Prompt

Continue the Verified-State Harness as an implementation/research agent.

First read `handoff/README_HANDOFF.md`, current status, Stage 03 task, validation gates, evidence standard, and Stage 02 rc2 exit evidence. Then inspect actual source and git state.

Historical guardrail: Stage 02 was PARTIAL when rc2 began; it was promoted only after a real Linux namespace backend, 12 required attacks, 4 defense-in-depth probes, profile integration, and full regression passed. Do not downgrade that standard of evidence.

Current task: **Stage 03 — Persistence / Resume / Reproducibility**.

```text
Inspect → Reproduce → Freeze contract → Minimal implementation
→ kill/resume + corruption + duplicate-effect probes
→ full regression → logic/integrity re-review
→ raw evidence → detailed MD → PASS/PARTIAL/FAIL
```

Do not treat checkpoint-save existence as resume proof. Do not replay committed external side effects during recovery. Preserve failed traces. Stop on PARTIAL/FAIL.
