# Stage 03 — Persistence / Resume / Reproducibility

Status: **NEXT / NOT STARTED**.

Entry condition: Stage 02 PASS with direct runtime evidence — satisfied by the rc2 evidence set.

Primary goal: prove forced interruption can resume without replaying already committed side effects, with checkpoint/event consistency, corruption handling, canonical replay state hash, and provenance manifest.

Do not treat checkpoint-save existence as resume correctness. Full criteria are in `handoff/03_NEXT_STAGE_TASK.md`.
