# Stage 03 — Persistence / Resume / Reproducibility

Status: **PASS / EXITED**.

Version: `v0.4.0`.

## Exit evidence

```text
Stage 03 targeted tests       12 passed
full regression              59 passed
direct resume probe           4 / 4 PASS
duplicate external actions    0
compileall                    PASS
Stage 02 security regression PASS
```

Canonical reports:

- `experimental/verified-state-harness/docs/STAGE3_PREFLIGHT_REREVIEW.md`
- `experimental/verified-state-harness/docs/STAGE3_IMPLEMENTATION_REPORT.md`
- `experimental/verified-state-harness/docs/STAGE3_EVIDENCE_MATRIX.md`
- `experimental/verified-state-harness/docs/STAGE3_FINAL_REREVIEW.md`
- `experimental/verified-state-harness/docs/STAGE3_EXIT_DECISION.md`

Canonical runtime evidence:

- `experimental/verified-state-harness/evidence/stage3_resume_probe.json`
- `experimental/verified-state-harness/evidence/stage3_validation_summary.json`
- `experimental/verified-state-harness/evidence/stage3_full_pytest.txt`
- `experimental/verified-state-harness/evidence/stage3_stage2_regression_attack_probe.json`

## Key semantics

A `COMMITTED` non-idempotent receipt is deduplicated on restart. A `PREPARED`-only receipt is treated as an ambiguous crash window and blocks automatic replay.

This is an at-most-once automatic execution contract, not an unsupported exactly-once claim.

## Next allowed stage

Stage 04 — Semantic Verification.
