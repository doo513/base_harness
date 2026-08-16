# General Continuation Prompt — Historical Stage 02 Entry State

This file preserves the critical inherited instruction that governed rc2.

At the start of the work represented by this branch:

```text
Stage 02 = PARTIAL / NOT EXITED
```

The next agent was forbidden to move to Stage 03. Its first required task was:

```text
Production Sandbox Backend
+ actual filesystem/network attack probe
```

Mandatory workflow was: inspect current implementation; reproduce tests/known failures; freeze Stage 02 contract; implement only Stage 02; add unit/adversarial/integration tests; run full regression; logic/security re-review; save raw evidence; write detailed report; mark PASS/PARTIAL/FAIL; stop on PARTIAL.

Forbidden: feature expansion into RAG/Skill/Subagent, README-only verification, mock/fake sandbox attestations as production proof, LLM self-verification as final truth, deleting failed evidence, or proceeding to the next stage while Stage 02 remained PARTIAL.

This historical instruction has now been satisfied by the rc2 implementation/evidence. Do not reinterpret it as saying current Stage 02 is still PARTIAL; see `02_CURRENT_STATUS.md` and the rc2 exit evidence.
