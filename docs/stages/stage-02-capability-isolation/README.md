# Stage 02 — Capability Isolation + Sealed Oracle

Historical rc1 status: **PARTIAL / NOT EXITED**.

Current rc2/final status: **PASS / EXITED** for `LinuxNamespaceSandboxBackend` when live `runtime_probe` succeeds.

Required direct evidence: 12/12 attack probes PASS, 4/4 defense-in-depth probes PASS, workspace positive control PASS, 47-test full regression PASS, compileall PASS.

Canonical current reports are mirrored from:
- `experimental/verified-state-harness/docs/STAGE2_RC2_IMPLEMENTATION_REPORT.md`
- `experimental/verified-state-harness/docs/STAGE2_RC2_FINAL_REREVIEW.md`
- `experimental/verified-state-harness/docs/STAGE2_RC2_EXIT_DECISION.md`
- `experimental/verified-state-harness/docs/STAGE2_EVIDENCE_MATRIX.md`

The inherited PARTIAL status is intentionally preserved in `handoff/prompts/GENERAL_CONTINUATION_PROMPT_INHERITED_STAGE02.md` rather than silently rewritten.
