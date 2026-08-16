# Stage 08 — Retrieval / Memory Gateway

Status: **CONTRACT FROZEN / PREREQUISITE HARDENING REQUIRED**  
Target release: `v0.9.0` only after PASS.

## Entry result

Stage 07 `v0.8.0` is PASS / EXITED. Stage-08 preflight found that the repository already contains a prototype `MemoryStore`, but it is not safe to treat as the Stage-08 architecture: search mutates recall state, authority is free text, overwrite/supersession is uncontrolled, and equal-score ordering has no explicit total tie-break.

A second prerequisite defect is shared artifact integrity handling. Stage 04 and Stage 06 independently implement content-address validation instead of delegating to one ArtifactStore verified-read primitive.

## Current sequence

```text
Stage-08 preflight review            COMPLETE
Retrieval/Memory Admission Contract  FROZEN
shared ArtifactStore verified read   NEXT (`v0.8.1` hardening)
full Stage 03-07 regression          required
Stage-08 feature implementation      BLOCKED until hardening PASS
```

## Core rule

Retrieved or remembered material remains `untrusted_retrieval` with `instruction_authority=none`. Retrieval admission never writes verified facts or completion state. Promotion can only occur by proposal + Stage-04 verification + Kernel commit.

## Initial provider direction

After the prerequisite is closed, the first provider should be deterministic/local/inspectable rather than embedding/vector based. This allows source identity, content integrity, ordering, tie-breaking, deduplication, persistence, and resume semantics to be proven before retrieval-quality optimization.

See:

- `../../STAGE8_PREFLIGHT_REREVIEW.md`
- `CONTRACT.md`
- `../../handoff/03_NEXT_STAGE_TASK.md`
